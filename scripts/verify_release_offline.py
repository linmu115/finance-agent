"""Verify a portable ZIP without opening another application HTTP port.

Extract into a fresh Unicode/space path, use bundled runtimes with a system-only
PATH, exercise real stdio MCP and source parsing, then reconnect to check state.
This does not claim HTTP launcher or browser cold-start coverage.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--zip', required=True)
    args = parser.parse_args()
    archive = Path(args.zip).resolve()
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    evidence = ROOT/'dist'/('offline-deployment-'+stamp)
    extraction = evidence/'部署验收 空格'
    evidence.mkdir(parents=True)
    report = {'mode':'offline-stdio', 'external_api_calls':0, 'http_ports_opened':[],
              'archive':archive.name, 'archive_sha256':digest(archive), 'checks':[],
              'not_exercised':['HTTP install/start/stop', 'fresh-package browser', 'live LLM', 'Docker execution']}
    output = evidence/'deployment-verification.json'

    def check(name, passed, detail=None):
        report['checks'].append({'name':name,'passed':bool(passed),'detail':detail})
        output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        if not passed: raise AssertionError(name)
        print('PASS '+name,flush=True)

    try:
        with zipfile.ZipFile(archive) as z:
            manifests = [n for n in z.namelist() if n.count('/')==1 and n.endswith('/INSTALL_MANIFEST.json')]
            if len(manifests)!=1: raise ValueError('Expected one package manifest')
            prefix = manifests[0].split('/')[0]
            manifest = json.loads(z.read(manifests[0]))
            members = {prefix+'/'+r['path']:r for r in manifest['files']}
            check('exact_members',set(z.namelist())==set(members)|{manifests[0]} and len(z.namelist())==len(members)+1)
            for name in z.namelist():
                target=(extraction/name).resolve()
                if not target.is_relative_to(extraction.resolve()) or '\\' in name:
                    raise ValueError('Unsafe archive path')
                target.parent.mkdir(parents=True,exist_ok=True)
                h=hashlib.sha256()
                with z.open(name) as src,target.open('xb') as dst:
                    while block:=src.read(1024*1024):h.update(block);dst.write(block)
                if name in members and (h.hexdigest()!=members[name]['sha256'] or target.stat().st_size!=members[name]['size']):
                    raise AssertionError('Hash/size mismatch: '+name)
            check('all_files_sha256_size_and_crc',True,{'files':len(members)})
        package=extraction/prefix
        release=json.loads((package/'RELEASE.json').read_text())
        metadata=json.loads((package/'package.json').read_text())
        report['version']=metadata['version']
        check('version_matches',release['version']==metadata['version']==manifest['version'])
        check('clean_install_no_credentials_or_data',not (package/'data').exists() and not (package/'.env').exists())
        system=Path(os.environ['SystemRoot'])
        ps=system/'System32/WindowsPowerShell/v1.0/powershell.exe'
        env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','TEMP','TMP','USERPROFILE','LOCALAPPDATA','APPDATA','COMSPEC','PATHEXT','SYSTEMDRIVE','PROGRAMFILES','PROGRAMFILES(X86)','PROGRAMDATA','HOMEDRIVE','HOMEPATH'}}
        env.update(PATH=';'.join(str(p) for p in [system/'System32',system,ps.parent,system/'System32/Wbem']),PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1',PYTHONIOENCODING='utf-8')
        node=package/'runtime/node/node.exe'
        python=package/'runtime/python/python.exe'
        data=package/'data/active'

        def run(name,command,extra=None,timeout=180):
            with (evidence/(name+'.stdout.log')).open('wb') as out,(evidence/(name+'.stderr.log')).open('wb') as err:
                result=subprocess.run(command,cwd=package,env={**env,**(extra or {})},stdout=out,stderr=err,timeout=timeout)
            check(name,result.returncode==0)
            return (evidence/(name+'.stdout.log')).read_text(encoding='utf-8-sig',errors='replace').strip()

        run('bundled_doctor',[str(ps),'-NoProfile','-ExecutionPolicy','Bypass','-File',str(package/'scripts/manage.ps1'),'-Action','doctor','-NoBrowser'])
        run('compiled_node_syntax',[str(node),'--check','server/dist/main.js'])
        script="""
import assert from 'node:assert/strict';
import path from 'node:path';
import {copyFile,mkdir,readFile} from 'node:fs/promises';
import {APP_VERSION,DATA,ROOT,PYTHON} from './server/dist/config.js';
import {FinanceService} from './server/dist/mcp.js';
const project='portable-verification';
assert.equal(APP_VERSION,JSON.parse(await readFile('package.json','utf8')).version);
assert.equal(DATA,path.join(ROOT,'data','active'));
assert.equal(PYTHON,path.join(ROOT,'runtime','python','python.exe'));
await mkdir(path.join(DATA,'uploads',project),{recursive:true});
const fixture=path.join(ROOT,'benchmark/versions/v0.5-holdout/inputs/cnooc_2025_en_whole_tables.pdf');
const file=path.join(DATA,'uploads',project,'完整 报告.pdf');
await copyFile(fixture,file);
let docId,details;
const service=new FinanceService();
try{
 await service.connect();
 await service.call('create_project',{project_id:project,name:'便携部署 核验'});
 const registered=await service.call('register_document',{project_id:project,path:file,original_name:'完整 报告.pdf'});
 docId=registered.data.document_id;
 assert.ok(docId);
 const prepared=await service.call('prepare_document_sources',{project_id:project,document_ids:[docId]});
 details=prepared.data.documents[0];
 assert.ok(details.pages>0 && details.tables>0);
 assert.equal(details.facts_written,0);
 const page=await service.call('get_source_page',{project_id:project,document_id:docId,page:1});
 assert.ok(page.data.text.length>50);
 const catalog=await service.call('get_asset_catalog',{project_id:project});
 assert.ok(catalog.data);
}finally{await service.close();}
const reopened=new FinanceService();
try{
 await reopened.connect();
 const doc=await reopened.call('get_document',{project_id:project,document_id:docId});
 assert.equal(doc.data.original_name,'完整 报告.pdf');
 const page=await reopened.call('get_source_page',{project_id:project,document_id:docId,page:1});
 assert.ok(page.data.text.length>50);
 console.log(JSON.stringify({version:APP_VERSION,pages:details.pages,tables:details.tables,facts_written:details.facts_written,reconnected:true,unicode_preserved:true}));
}finally{await reopened.close();}
"""
        result=run('bundled_stdio_parse_and_reconnect',[str(node),'--input-type=module','-e',script],timeout=240)
        report['stdio_result']=json.loads(result.splitlines()[-1])
        run('packaged_dimension_and_dashboard_regressions',[str(python),'-B','-m','unittest','service.tests.test_script_cleaning','service.tests.test_asset_dashboard','-v'],timeout=240)
        for filename in ['web/dist/index.html','skills/research-ingestion/SKILL.md','docs/START_AND_USE.md','paper/v0.2.0/finance-agent-technical-paper.md','paper/v0.2.0/finance-agent-technical-paper.pdf']:
            check('included_'+filename,(package/filename).is_file() and (package/filename).stat().st_size>0)
        report['status']='passed'
    except BaseException as error:
        report['status']='failed';report['failure']=str(error);raise
    finally:
        report['finished_at']=datetime.now(timezone.utc).isoformat()
        output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print('Evidence: '+str(output),flush=True)


def digest(file):
    with Path(file).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


if __name__=='__main__':main()

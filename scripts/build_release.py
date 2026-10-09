"""Build a relocatable Windows x64 release from locked, installed dependencies.

Only reviewed source inputs are collected. User data, credentials, VM disks and
development caches never enter the archive. Runtime provenance and every file
are recorded by SHA-256. Use --plan before --stage / --archive.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = json.loads((ROOT/'package.json').read_text(encoding='utf-8'))['version']
PACKAGE = f'finance-agent-{VERSION}-windows-x64'
# A runnable product release is not a research handoff. Keep an explicit,
# reviewed allowlist; never recurse over historical evidence or sample folders.
EXTRA_FILES = {
    'README.md', 'README.txt', 'THIRD_PARTY_NOTICES.md', '.gitattributes',
    'install.cmd', 'stop-finance.cmd', 'check-install.cmd', 'start-finance.cmd',
    'package.json', 'package-lock.json', 'requirements.lock.txt', '.env.example',
    '.gitignore', 'tsconfig.tools.json', 'docs/START_AND_USE.md',
    f'docs/RELEASE-{VERSION}.md',
    'scripts/manage.ps1', 'scripts/runtime.ps1', 'scripts/fix_dependency.mjs',
    'scripts/build_release.py', 'scripts/verify_release.py',
    'scripts/scan_release.py',
    'scripts/verify_release_offline.py', 'scripts/package_handoff.py',
    'scripts/package_delivery.py',
    # The offline verifier runs these synthetic regressions in its extracted
    # copy. Include only their explicit fixture dependency, no evaluation data.
    'service/tests/test_script_cleaning.py',
    'service/tests/test_asset_dashboard.py',
    'service/tests/test_document_library.py',
    'service/tests/test_research_ingestion.py',
    'benchmark/versions/v0.5-holdout/inputs/cnooc_2025_en_whole_tables.pdf',
}
EXTRA_ROOTS = {'licenses', 'skills'}
spec = importlib.util.spec_from_file_location('handoff', ROOT/'scripts/package_handoff.py')
handoff = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(handoff)

def sha256(file):
    with Path(file).open('rb') as stream: return hashlib.file_digest(stream,'sha256').hexdigest()

def collect():
    downloads = handoff.application_downloads(ROOT)
    def product_source(name):
        parts = Path(name).parts
        if name in EXTRA_FILES or parts[0] in EXTRA_ROOTS or parts[0] == 'vendor':
            return True
        if parts[0] in {'server', 'service', 'sandbox'}:
            return not any(p in {'tests', 'runs', 'results', 'fixtures', 'evidence'} for p in parts[1:]) and not Path(name).name.startswith('test_')
        if parts[0] == 'web':
            return len(parts) == 2 or parts[1] in {'src', 'public'}
        return False
    selected = {name: file for name,file,_ in handoff.collect_inputs(ROOT,set(),downloads)
                if product_source(name)}
    for name in EXTRA_FILES:
        file = ROOT/name
        if file.is_file(): selected[name] = file
    for folder in EXTRA_ROOTS:
        for file in (ROOT/folder).rglob('*'):
            if file.is_file() and not file.is_symlink() and not handoff.blocked(file.relative_to(ROOT).as_posix()):
                selected[file.relative_to(ROOT).as_posix()] = file
    required = {'README.md','scripts/manage.ps1','server/main.ts','service/server.py','web/src/App.tsx','skills/financial-modeling/SKILL.md'}
    missing = required - selected.keys()
    if missing: raise ValueError('Required sources missing: '+','.join(sorted(missing)))
    return dict(sorted(selected.items()))

def source_plan(output: Path):
    selected = collect(); rows=[]; findings=[]; blocked=[]
    budget={'expanded_bytes':0,'members':0}
    for name,file in selected.items():
        raw=file.read_bytes(); scan=handoff.scan_contents(name,raw,budget=budget)
        findings.extend(scan['findings']); blocked.extend(scan['forbidden_members'])
        rows.append({'path':name,'size':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
    plan={'version':VERSION,'source_files':rows,'source_count':len(rows),'bytes':sum(r['size'] for r in rows),'privacy_findings':findings,'forbidden_archive_members':blocked,'nested_members_scanned':budget['members']}
    output.mkdir(parents=True,exist_ok=True)
    (output/'source-plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2),encoding='utf-8')
    (output/'git-files.nul').write_bytes(b''.join(name.encode('utf-8')+b'\0' for name in selected))
    if findings or blocked:
        print(json.dumps({'privacy_findings':findings,'forbidden_archive_members':blocked},ensure_ascii=True))
        raise ValueError('Release source privacy scan failed; matched values were not printed')
    print(f'Source scan: {len(rows)} files, {sum(r["size"] for r in rows)/1024/1024:.1f} MiB, no unreviewed credential matches',flush=True)
    return selected,plan

def copy_tree(source: Path,target: Path,*,python=False):
    def ignore(folder,names):
        return [n for n in names if n in {'__pycache__','.git','.pytest_cache','.mypy_cache'} or n.endswith(('.pyc','.pyo')) or (python and n in {'_virtualenv.pth','_virtualenv.py','pyvenv.cfg','direct_url.json'})]
    shutil.copytree(source,target,ignore=ignore,dirs_exist_ok=True)

def stage(output: Path,node: Path,python_home: Path,site_packages: Path):
    selected,plan=source_plan(output)
    target=output/PACKAGE
    if target.exists(): raise ValueError('Stage already exists; use a new output directory instead of overwriting: '+str(target))
    if json.loads((ROOT/'package.json').read_text())['version'] != VERSION: raise ValueError('Package version mismatch')
    for relative in ['server/dist/main.js','web/dist/index.html']:
        if not (ROOT/relative).is_file(): raise ValueError('Run npm run build before staging')
    for name,file in selected.items():
        dest=target/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(file,dest)
    copy_tree(ROOT/'server/dist',target/'server/dist')
    copy_tree(ROOT/'web/dist',target/'web/dist')
    (target/'runtime/node').mkdir(parents=True)
    shutil.copy2(node,target/'runtime/node/node.exe')
    shutil.copy2(ROOT/'licenses/Node.js-24.7.0-LICENSE.txt',target/'runtime/node/LICENSE.txt')
    copy_tree(python_home,target/'runtime/python',python=True)
    copy_tree(site_packages,target/'runtime/python/Lib/site-packages',python=True)
    # Production-only npm installation. tsx remains a runtime dependency for benchmark runners.
    npm=shutil.which('npm.cmd')
    if not npm: raise ValueError('npm.cmd is required on the build machine')
    result=subprocess.run([npm,'ci','--omit=dev','--no-audit','--no-fund'],cwd=target)
    if result.returncode: raise ValueError('Production dependency installation failed')
    node_version=subprocess.check_output([str(node),'--version'],text=True).strip()
    python_version=subprocess.check_output([str(target/'runtime/python/python.exe'),'--version'],text=True).strip()
    source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    provenance={'version':VERSION,'source_commit':source_commit,'platform':'win32-x64','created_at':datetime.now(timezone.utc).isoformat(),'node':node_version,'node_sha256':sha256(node),'python':python_version,'python_sha256':sha256(target/'runtime/python/python.exe'),'package_lock_sha256':sha256(target/'package-lock.json'),'requirements_lock_sha256':sha256(target/'requirements.lock.txt'),'contains_user_data':False,'requires_system_node_or_python':False,'optional_docker_image':'finance-analysis:0.1'}
    (target/'RELEASE.json').write_text(json.dumps(provenance,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Stage prepared: '+str(target),flush=True)
    return target

def archive(output: Path):
    target=output/PACKAGE
    if not (target/'RELEASE.json').is_file(): raise ValueError('A completed stage is required')
    if (target/'data').exists(): raise ValueError('Runtime data found in stage; test a separate extracted copy')
    package=output/(PACKAGE+'.zip')
    if package.exists(): raise ValueError('Archive already exists; refuse to overwrite a published package')
    manifest_path=target/'INSTALL_MANIFEST.json'
    files=[]
    for file in sorted(target.rglob('*')):
        if file.is_symlink(): raise ValueError('Release links are not supported: '+str(file.relative_to(target)))
        if not file.is_file() or file==manifest_path: continue
        name=file.relative_to(target).as_posix()
        if name.startswith(('data/','dist/','.venv/')) or name == '.env' or '/__pycache__/' in name or name.endswith('.pyc'): raise ValueError('Runtime state was written to stage: '+name)
        files.append((name,file))
    print(f'Hashing {len(files)} release files...',flush=True)
    def manifest_row(item):
        name,file=item
        return {'path':name,'size':file.stat().st_size,'sha256':sha256(file)}
    with ThreadPoolExecutor(max_workers=8) as pool:
        rows=list(pool.map(manifest_row,files))
    manifest={'version':VERSION,'files':rows,'count':len(rows),'bytes':sum(r['size'] for r in rows)}
    manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Creating and verifying ZIP...',flush=True)
    with zipfile.ZipFile(package,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for row in rows:z.write(target/row['path'],PACKAGE+'/'+row['path'])
        z.write(manifest_path,PACKAGE+'/INSTALL_MANIFEST.json')
    verify_archive(package,manifest)
    checksum=sha256(package)
    (output/'SHA256SUMS.txt').write_text(checksum+'  '+package.name+'\n',encoding='ascii')
    print(json.dumps({'package':str(package),'bytes':package.stat().st_size,'sha256':checksum,'files':len(rows),'verification':'CRC and every file SHA-256 passed'}),flush=True)

def verify_archive(package: Path,manifest=None):
    with zipfile.ZipFile(package) as z:
        if z.testzip() is not None: raise ValueError('ZIP CRC verification failed')
        if manifest is None: manifest=json.loads(z.read(PACKAGE+'/INSTALL_MANIFEST.json'))
        expected={PACKAGE+'/'+r['path'] for r in manifest['files']}|{PACKAGE+'/INSTALL_MANIFEST.json'}
        if len(z.namelist())!=len(expected) or set(z.namelist())!=expected: raise ValueError('Unexpected archive members')
        for row in manifest['files']:
            with z.open(PACKAGE+'/'+row['path']) as stream:
                if hashlib.file_digest(stream,'sha256').hexdigest()!=row['sha256']: raise ValueError('File checksum mismatch: '+row['path'])

def main():
    parser=argparse.ArgumentParser();mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--plan',action='store_true');mode.add_argument('--stage',action='store_true');mode.add_argument('--archive',action='store_true')
    parser.add_argument('--output',default=f'dist/release-{VERSION}')
    parser.add_argument('--node',default=shutil.which('node.exe'))
    parser.add_argument('--python-home',default=sys.base_prefix)
    parser.add_argument('--site-packages',default=str(ROOT/'.venv/Lib/site-packages'))
    args=parser.parse_args();output=Path(args.output).resolve()
    if not output.is_relative_to(ROOT/'dist'):raise ValueError('Release output must be inside this workspace dist directory')
    if args.plan:source_plan(output)
    if args.stage:stage(output,Path(args.node),Path(args.python_home),Path(args.site_packages))
    if args.archive:archive(output)

if __name__=='__main__':main()

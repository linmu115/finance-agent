"""Exercise an actual release ZIP in a fresh Unicode/space path without API keys.

Uses the packaged runtimes with a system-only PATH. The optional UI check uses
the development checkout's Playwright/Edge, never the user's existing tab.
Leaves evidence and synthetic test data under dist; cleans up only its own app.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import time
import urllib.error
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = 'finance-agent-0.1-windows-x64'
http = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def request(base, route, payload=None):
    body = None if payload is None else json.dumps(payload).encode('utf-8')
    headers = {} if body is None else {'Content-Type': 'application/json'}
    with http.open(urllib.request.Request(base+route, data=body, headers=headers), timeout=20) as response:
        return json.loads(response.read())


def available(port):
    with socket.socket() as sock:
        return sock.connect_ex(('127.0.0.1', port)) != 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--zip', required=True)
    parser.add_argument('--port', type=int, default=3011)
    parser.add_argument('--browser', action='store_true')
    args = parser.parse_args()
    if not available(args.port) or not available(args.port+1):
        raise RuntimeError('Choose two unused adjacent ports; no existing service will be stopped')
    archive = Path(args.zip).resolve()
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    evidence = ROOT/'dist'/('deployment-check-'+stamp)
    extraction = evidence/'部署验收 空格'
    package = extraction/PACKAGE
    evidence.mkdir(parents=True)
    with archive.open('rb') as archive_stream:
        archive_sha256 = hashlib.file_digest(archive_stream, 'sha256').hexdigest()
    report = {'version': '0.1.0', 'archive': archive.name,
              'archive_sha256': archive_sha256,
              'created_at': datetime.now(timezone.utc).isoformat(), 'checks': [],
              'external_api_calls': 0, 'docker_started': False}
    result_path = evidence/'deployment-verification.json'

    def check(name, passed, detail=None):
        report['checks'].append({'name': name, 'passed': bool(passed), 'detail': detail})
        result_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        if not passed:
            raise AssertionError(name)
        print('PASS '+name, flush=True)

    # Validate member names and the content manifest before any executable runs.
    with zipfile.ZipFile(archive) as z:
        manifest_bytes = z.read(PACKAGE+'/INSTALL_MANIFEST.json')
        manifest = json.loads(manifest_bytes)
        members = {PACKAGE+'/'+r['path']: r for r in manifest['files']}
        check('archive_exact_members', set(z.namelist()) == set(members)|{PACKAGE+'/INSTALL_MANIFEST.json'} and len(z.namelist()) == len(members)+1)
        for name in z.namelist():
            dest = (extraction/name).resolve()
            if not dest.is_relative_to(extraction.resolve()):
                raise ValueError('Archive member escapes extraction folder')
        # ZipExtFile verifies CRC when consumed to EOF. Verify hashes during
        # extraction as well, avoiding three full reads of the large archive.
        for name, row in members.items():
            dest = extraction/name
            dest.parent.mkdir(parents=True, exist_ok=True)
            digest = hashlib.sha256()
            with z.open(name) as stream, dest.open('xb') as output:
                while chunk := stream.read(1024*1024):
                    digest.update(chunk)
                    output.write(chunk)
            if digest.hexdigest() != row['sha256']:
                raise AssertionError('Archive hash: '+name)
        (package/'INSTALL_MANIFEST.json').write_bytes(manifest_bytes)
        check('archive_crc', True)
        check('archive_file_hashes', True, {'files': len(members)})
    check('fresh_install_has_no_user_data', not (package/'data').exists() and not (package/'.env').exists())
    base = f'http://127.0.0.1:{args.port}'
    data = package/'data'
    system = Path(os.environ['SystemRoot'])
    powershell = system/'System32/WindowsPowerShell/v1.0/powershell.exe'
    env = {k: v for k, v in os.environ.items() if k.upper() in {
        'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'USERPROFILE', 'LOCALAPPDATA', 'APPDATA',
        'COMSPEC', 'PATHEXT', 'SYSTEMDRIVE', 'PROGRAMFILES', 'PROGRAMFILES(X86)', 'PROGRAMDATA', 'HOMEDRIVE', 'HOMEPATH'}}
    env['PATH'] = ';'.join(str(p) for p in [system/'System32', system, powershell.parent, system/'System32/Wbem'])
    env['PYTHONNOUSERSITE'] = '1'
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    env['PYTHONIOENCODING'] = 'utf-8'
    run_count = 0

    def launch(action, *extra, success=True, port=None):
        nonlocal run_count
        run_count += 1
        command = [str(powershell), '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                   str(package/'scripts/manage.ps1'), '-Action', action, '-Port', str(port or args.port), '-NoBrowser', *map(str, extra)]
        # Windows PowerShell 5.1 may pass unused pipe handles to detached children.
        # Capture to files so a healthy background server cannot hold communicate()
        # open after the launcher itself has already exited.
        stdout_path = evidence/f'{run_count:02}-{action}.stdout.log'
        stderr_path = evidence/f'{run_count:02}-{action}.stderr.log'
        with stdout_path.open('wb') as stdout, stderr_path.open('wb') as stderr:
            result = subprocess.run(command, cwd=package, env=env, stdout=stdout, stderr=stderr, timeout=300)
        result.stdout = stdout_path.read_bytes()
        result.stderr = stderr_path.read_bytes()
        if (result.returncode == 0) != success:
            raise RuntimeError(f'Unexpected {action} exit {result.returncode}; see evidence log {run_count}')
        return result

    def record():
        return json.loads((data/f'runtime/launcher-{args.port}.json').read_text(encoding='utf-8-sig'))

    try:
        launch('install', '-ShortcutDirectory', evidence/'快捷方式')
        check('install_and_shortcuts', all((evidence/'快捷方式'/name).is_file() for name in ['Finance Agent 0.1.lnk', 'Stop Finance Agent 0.1.lnk']))
        ready = request(base, '/api/health')
        check('fresh_health_and_no_model_credentials', ready == {'ok': True, 'version': '0.1.0', 'service': 'connected', 'modelConfigured': False})
        owner = record()
        check('bundled_node_selected', Path(owner['node']).resolve() == (package/'runtime/node/node.exe').resolve())
        launch('doctor')
        check('bundled_python_document_dependencies', True)
        launch('start')
        check('repeated_start_reuses_process', record()['processId'] == owner['processId'])
        conflict = launch('start', '-DataDirectory', evidence/'端口冲突 数据', success=False)
        check('port_conflict_keeps_owner', record()['processId'] == owner['processId'] and request(base, '/api/health')['ok'] and b'used by another' in conflict.stderr)
        launch('start', success=False, port=args.port+1)
        check('same_data_second_port_rejected', available(args.port+1) and request(base, '/api/health')['ok'])
        project = request(base, '/api/projects', {'name': '部署验收 项目'})
        chat = request(base, f'/api/projects/{project["id"]}/conversations', {})
        resources = request(base, f'/api/projects/{project["id"]}/resources')
        check('project_rules_and_skills_available', bool(resources.get('skills')))
        fixture = package/'benchmark/versions/v0.5-holdout/inputs/cnooc_2025_en_whole_tables.pdf'
        raw = fixture.read_bytes()
        boundary = 'FinanceReleaseBoundary'+stamp
        body = (f'--{boundary}\r\nContent-Disposition: form-data; name="files"; filename="deployment-report.pdf"\r\nContent-Type: application/pdf\r\n\r\n'.encode() + raw + f'\r\n--{boundary}--\r\n'.encode())
        upload = urllib.request.Request(base+f'/api/projects/{project["id"]}/uploads', data=body, headers={'Content-Type': 'multipart/form-data; boundary='+boundary})
        with http.open(upload, timeout=30) as response:
            document = json.loads(response.read())['documents'][0]
        with http.open(base+f'/api/projects/{project["id"]}/documents/{document["id"]}/file', timeout=20) as response:
            downloaded = response.read()
        check('pdf_upload_and_original_download', downloaded == raw and downloaded.startswith(b'%PDF'))
        launch('stop')
        check('stop_releases_http_port', available(args.port))
        # While the application is stopped, use its production MCP client and
        # packaged Python to prepare deterministic sources in the isolated data.
        script = """
import {FinanceService} from './server/dist/mcp.js';
const service=new FinanceService();
try {
 await service.connect();
 const parsed=await service.call('prepare_document_sources',{project_id:process.env.VERIFY_PROJECT,document_ids:[process.env.VERIFY_DOCUMENT]});
 const page=await service.call('get_source_page',{project_id:process.env.VERIFY_PROJECT,document_id:process.env.VERIFY_DOCUMENT,page:1});
 console.log(JSON.stringify({parsed:parsed.data,page:page.data}));
} finally { await service.close(); }
"""
        parse_env = {**env, 'FINANCE_DATA_DIR': str(data), 'VERIFY_PROJECT': project['id'], 'VERIFY_DOCUMENT': document['id']}
        parse = subprocess.run([str(package/'runtime/node/node.exe'), '--input-type=module', '-e', script], cwd=package,
                               env=parse_env, capture_output=True, timeout=120)
        (evidence/'parse.stderr.log').write_bytes(parse.stderr)
        if parse.returncode:
            raise RuntimeError('Packaged MCP parsing failed; see parse.stderr.log')
        parsed = json.loads(parse.stdout)
        details = parsed['parsed']['documents'][0]
        check('bundled_mcp_native_pdf_parse', details['pages'] == 3 and details['tables'] > 0, {'pages': details['pages'], 'tables': details['tables'], 'facts_written': details['facts_written']})
        launch('start')
        projects = request(base, '/api/projects')['projects']
        restored_chat = request(base, '/api/conversations/'+chat['id'])
        check('restart_preserves_projects_and_conversations', any(p['id'] == project['id'] for p in projects) and restored_chat['id'] == chat['id'])
        page = request(base, f'/api/projects/{project["id"]}/documents/{document["id"]}/pages/1')
        check('source_page_after_restart', len(page.get('text', '')) > 50)
        if page.get('imageUrl'):
            with http.open(base+page['imageUrl'], timeout=20) as response:
                image = response.read()
            check('source_image_after_restart', image.startswith(b'\x89PNG') or image.startswith(b'\xff\xd8'))
        if args.browser:
            browser_env = {**os.environ, 'RELEASE_URL': base, 'RELEASE_EVIDENCE': str(evidence), 'RELEASE_PROJECT_ID': project['id']}
            ui = subprocess.run(['node', 'web/tests/release-deployment.cjs'], cwd=ROOT, env=browser_env, capture_output=True, timeout=75)
            (evidence/'browser.stdout.log').write_bytes(ui.stdout)
            (evidence/'browser.stderr.log').write_bytes(ui.stderr)
            check('compiled_ui_in_fresh_browser', ui.returncode == 0)
        launch('stop')
        check('final_stop_and_data_preserved', available(args.port) and data.is_dir())
        report['status'] = 'passed'
    except BaseException as error:
        report['status'] = 'failed'
        report['failure'] = str(error)
        raise
    finally:
        if (data/f'runtime/launcher-{args.port}.json').exists():
            try:
                launch('stop')
            except Exception as error:
                report['cleanup_error'] = str(error)
        report['port_closed_at_end'] = available(args.port)
        report['finished_at'] = datetime.now(timezone.utc).isoformat()
        result_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print('Evidence: '+str(result_path), flush=True)


if __name__ == '__main__':
    main()

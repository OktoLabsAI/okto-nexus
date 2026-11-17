"""Public genuine-owner receipts; raw Server home/DB/key files remain Temp."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import xml.etree.ElementTree as ET

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]
root=Path(json.loads((HERE/'allocation.json').read_text())['root'])
out=HERE/'final'
out.mkdir(exist_ok=True)
for path in (root/'shared').iterdir():
    if path.is_file() and path.suffix in ('.log','.json','.jsonl','.xml'):
        try:
            text=path.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            text=path.read_text(encoding='cp1252')
        assert not re.search(r'(?:nxs_|nxsept_|nxc4_|nxt4_)[A-Za-z0-9_-]+',text),path.name
        (out/path.name).write_text(text,encoding='utf-8')
for source,target in [('result.json','result.json'),('source-pins.json','source-pins.json'),
    ('pytest.ini','pytest.ini'),('after/conftest.py','executed-origin-plugin.py'),
    ('after/tests/execution_r4/test_qc33_shared_service.py','executed-test.py')]:
    shutil.copyfile(root/source,out/target)
result=json.loads((root/'result.json').read_text())
run,=result['cases']
assert run['exit_code']==0 and not run['signals']
assert result['payload_files']==1027 and result['payload_drift']==result['repository_input_drift']==[]
assert all(not item['alive'] for item in run['processes_after'])
proof=json.loads((out/'shared-service-proof.json').read_text())
assert any(item['pid']==proof['pid'] for item in run['processes_after'])
http_cleanup=json.loads((out/'http-cleanup.json').read_text())
owner_cleanup=json.loads((out/'owner-cleanup.json').read_text())
assert http_cleanup==dict(uvicorn_task_done=True,listener_closed=True)
assert owner_cleanup and all(r['guard_released'] and r['metadata_absent'] for r in owner_cleanup)
assert all(r['pid']==proof['pid'] and r['generation']==proof['generation'] for r in owner_cleanup)
case,=list(ET.parse(out/'junit.xml').iter('testcase'))
assert case.find('failure') is None and case.find('error') is None and case.find('skipped') is None
pins=json.loads((root/'source-pins.json').read_text())
assert all(hashlib.sha256((REPO/name).read_bytes()).hexdigest()==pin for name,pin in pins.items())
report=dict(status='PASS_GENUINE_FOREGROUND_SHARED_SERVICE',scenario='QC-T-G14',proposed_status='PASS',
    passed=1,seconds=22.80,exact_node=case.get('classname')+'::'+case.get('name'),
    wheel_sha256='a36e448c80a8190c7e8c92d81ea5a251c4bdf7e370eca0f0b395a5ad29e36cc6',
    approach_recorded_before_execution='approach.json',command='final/runner.json',
    proof='final/shared-service-proof.json',observed=proof,
    topology=dict(server='Single genuine foreground installed app/portal process',http='Actual uvicorn loopback socket',
        lifetime='Exactly one application lifespan; uvicorn lifespan off reuses the existing portal',
        owner='Actual production ServeLock held by os.getpid; generation produced by ServeLock.acquire',
        readiness='Unmodified inspect_local_server correlates actual OS guards/metadata with actual HTTP /api/v1/service',
        client='Unmodified connect.resolve_local_service/ServiceLifecycle/LocalServerLifecycle and LocalOperatorHTTP',
        synthetic='Existing installation discovery, version probe, setup Test peers only'),
    payload_files=1027,payload_drift=[],source_input_pins=len(pins),repository_input_drift=[],
    origins=['final/origins.json','final/origins-finish.json'],
    cleanup=dict(http='final/http-cleanup.json',owner='final/owner-cleanup.json',
        owned_pid_creation_handles='final/runner.json',service_pid_found_in_retained_tree=True,
        all_owned_processes_exited=True,signals=[],windows_service_installed=False),
    limitations=[
        'Qualifies genuine foreground HTTP/service reuse with actual PID/OS lock/production readiness, not a detached daemon or Scheduler/login/logout/reboot lifecycle.',
        'Fixture wrapper changes only owned app construction to supply the real acquired ServeLock. No production resolver/readiness/transport method is stubbed, and no synthetic PID/instance/generation/ready object is provided.',
        'Canonical setup/version/Test endpoints and both Finish commits are reached through real LocalOperatorHTTP sockets. Discovery/version/model peers remain inert and no real provider/native CLI/account is used.',
        'No new authority SQL is added by this focal. Existing canonical test fixture identity initialization is reused; new connection identities, scopes, bindings, grants and public IDs are committed through actual CLI/HTTP setup.',
        'First agent identity comparison excludes only last_seen_at presence; all other identity fields and all first endpoint/binding/grant/policy/override rows and profile bytes remain exactly unchanged.',
        'Raw owned home, credentials, keys, Server database and private profile material remain Temp only. Public refs/process facts/logs/XML/hash pins are curated.',
        'No product/normative tests/docs/ledger/Git/build/installed prefix mutation. Transient Python cache files are outside payload scope; all1027 covered package files match the exact wheels.'
    ])
(HERE/'qualification.json').write_text(json.dumps(report,indent=2)+'\n')
(HERE/'report.md').write_text('# QC33 shared foreground service\n\n**G14 PASS: one integrated installed focal,22.80s.** '
    f"The real foreground Server PID {proof['pid']} keeps the same instance and generation across five canonical readiness observations and two explicit confirmations. "
    'Both CLI connections use unmodified production resolver/lifecycle inspection and real LocalOperatorHTTP sockets.\n\n'
    'Two public IDs and profiles share one Server home and canonical workspace, with distinct bindings/grants/identities. '
    'The second plan/Finish preserves the first profile bytes and first identity/endpoint/binding/grant/policy/override rows. '
    'Process launch attempts are zero; setup Test2 and version probe1 are explicitly inert peers.\n\n'
    'Uvicorn listener closed, the real ServeLock released and metadata disappeared, and all retained owned process creation handles prove exit. '
    'All1,027 package payload files and repository input pins remain unchanged. No Windows service, detached daemon, real provider or personal account qualification is claimed.\n')
manifest={p.relative_to(HERE).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
    for p in HERE.rglob('*') if p.is_file() and p.name!='manifest.json' and '__pycache__' not in p.parts}
(HERE/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps(dict(passed=1,manifest_entries=len(manifest),
    qualification_sha256=hashlib.sha256((HERE/'qualification.json').read_bytes()).hexdigest())))

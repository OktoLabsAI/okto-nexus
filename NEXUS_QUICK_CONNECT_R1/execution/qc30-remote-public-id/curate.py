"""Only public test receipts; no operator cookies/vault/password/profile copied."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import xml.etree.ElementTree as ET

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]
TEMP=Path('C:/Users/jpamb/AppData/Local/Temp')
specs=[('nexus-qc30-remote-id-lb9li7uo','route-oracle-antecedent'),
       ('nexus-qc30-remote-id-l30t1ndc','configuration-oracle-antecedent'),
       ('nexus-qc30-remote-id-swftyxe_','omission-oracle-antecedent'),
       ('nexus-qc30-remote-id-x7j_a9h5','final')]
cuts=[]
for name,label in specs:
    root=TEMP/name
    out=HERE/label
    out.mkdir(exist_ok=True)
    for path in (root/'remote').iterdir():
        if path.is_file() and path.suffix in ('.log','.json','.jsonl','.xml'):
            try:
                value=path.read_text(encoding='utf-8')
            except UnicodeDecodeError:
                value=path.read_text(encoding='cp1252')
            assert not re.search(r'(?:nxs_|nxsept_|nxc4_|nxt4_)[A-Za-z0-9_-]+',value),path.name
            (out/path.name).write_text(value,encoding='utf-8')
    for source,target in [('source-pins.json','source-pins.json'),('result.json','result.json'),
        ('pytest.ini','pytest.ini'),('after/conftest.py','executed-origin-plugin.py'),
        ('after/tests/execution_r4/test_qc30_remote_public_id.py','executed-test.py')]:
        shutil.copyfile(root/source,out/target)
    result=json.loads((root/'result.json').read_text())
    run=result['cases'][0]
    assert result['payload_files']==1027 and result['payload_drift']==result['repository_input_drift']==[]
    assert not run['signals'] and all(not item['alive'] for item in run['processes_after'])
    case,=list(ET.parse(root/'remote/junit.xml').iter('testcase'))
    cuts.append(dict(root=str(root),evidence=label,exit_code=run['exit_code'],
        status='FAIL' if case.find('failure') is not None or case.find('error') is not None else 'PASS',
        node=case.get('classname')+'::'+case.get('name'),payload_files=1027,payload_drift=[],
        repository_input_drift=[],owned_processes_absent=True,signals=[]))
assert cuts[-1]['status']=='PASS' and cuts[-1]['exit_code']==0
allocation=json.loads((HERE/'allocation.json').read_text())
final=TEMP/'nexus-qc30-remote-id-x7j_a9h5'
for name,pin in allocation['fixture_pins'].items():
    assert hashlib.sha256((REPO/name).read_bytes()).hexdigest()==pin
    assert (REPO/name).read_bytes()==(final/'after'/name).read_bytes()
observed=json.loads((HERE/'final/remote-proof.json').read_text())
assert observed['tables_unchanged'] and set(observed['http_methods'])=={'GET'}
assert observed['native_opens']==observed['new_reservations']==observed['new_tests']==observed['new_grants']==observed['new_operations']==observed['new_sessions']==0
report=dict(status='PASS_SCOPED_INSTALLED_REMOTE_PUBLIC_ID',scenario='QC-T-I03',proposed_status='PASS',
    passed=1,seconds=21.06,exact_node=cuts[-1]['node'],cuts=cuts,proof='final/remote-proof.json',
    command='final/runner.json',fixture_pins=allocation['fixture_pins'],fixture_files_byte_identical=True,
    wheel_sha256='a36e448c80a8190c7e8c92d81ea5a251c4bdf7e370eca0f0b395a5ad29e36cc6',
    asserted_facts=observed,
    oracles_preserved=[
        'First external test used a nonexistent setup query route. Correct existing route is /connections/setup/{agent_id}?binding_id=...',
        'Second expected a standalone execution_location member in setup configuration; current DTO has no such member. Final assertion compares the entire canonical configuration unchanged and proves executor kind embedded from SQLite.',
        'Third expected top-level project_root:null. QuickConnectOutcome.to_dict intentionally omits None optional members. Final requires project_root absent, while nested cwd_resolution retains project_root:null/source:remote.'
    ],limitations=[
        'Remote means human operator HTTP topology over an owned Server app. The actual executor is Server-embedded; two physical computers or a live Connector transport are not claimed.',
        'MemoryVault and HTTPBridge are the existing byte-identical synthetic fixture. Server operator authentication/session, approved binding, grants, public-ID association, metadata and HTTP handlers/SQLite remain canonical.',
        'One deliberate metadata-only public-ID association uses exact catalog binding revision and seven refs before the observation baseline. Only connection_public_ids changes in the compared tables at that stage.',
        'CLI main connect then performs23GETs only; no operator CWD is sent in URL/body. Local Server/Git/input/Test are forbidden and twelve authority/registry tables remain byte-equivalent as rows.',
        'The operator profile and shortcut are owned temporary files; no password/cookie/token/vault/DB/client profile content is copied to evidence.',
        'Initial fixture binding/grant qualification and native factory are synthetic peers. No provider/model/real native CLI/personal account or daemon start is used.',
        'All four cuts preserve installed origins at start/finish,1027 exact wheel payloads, unchanged src/tests/docs pins, own PID handle exit and zero stop signals.',
        'No product/normative tests/docs/ledger/Git/build/installed prefix mutation. No new runtime or cleanup marker is pending.'
    ])
(HERE/'qualification.json').write_text(json.dumps(report,indent=2)+'\n')
(HERE/'report.md').write_text('# QC30 remote public ID\n\n**I03 scoped PASS —1 focal,21.06s.** '
    'A canonical metadata association binds the public ID to the exact reviewed seven-field reference. '
    'The installed main/connect resumes by operator profile, workspace and ID from a distinct operator CWD. '
    'The same reference and entire canonical execution configuration are retained; local Server/Git resolution is forbidden.\n\n'
    'After association, CLI observation uses23GETs only. Twelve authority/registry tables remain unchanged; there are zero new reservations, Test, grants, operations or sessions. '
    'No operator CWD is transferred in HTTP.\n\n'
    'This is a remote human operator viewing one Server-embedded executor, not two physical computers. '
    'MemoryVault/HTTPBridge and native peers are synthetic; no personal authentication or provider is used. '
    'Three incorrect external oracles remain preserved; no product was changed to satisfy them.\n\n'
    'All cuts exited naturally with1027 exact payload files, installed origins and zero source drift.\n')
manifest={p.relative_to(HERE).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
    for p in HERE.rglob('*') if p.is_file() and p.name!='manifest.json' and '__pycache__' not in p.parts}
(HERE/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps(dict(passed=1,manifest_entries=len(manifest),
    qualification_sha256=hashlib.sha256((HERE/'qualification.json').read_bytes()).hexdigest())))

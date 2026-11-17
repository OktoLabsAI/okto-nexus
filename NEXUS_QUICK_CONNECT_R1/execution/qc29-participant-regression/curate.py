"""Public participant regression receipts; no owned credentials or DB copied."""
import ast
import hashlib
import json
from pathlib import Path
import re
import shutil
import xml.etree.ElementTree as ET

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]
allocation=json.loads((HERE/'allocation.json').read_text())
root=Path(allocation['root'])
result=json.loads((root/'result.json').read_text())
assert result['payload_files']==1027 and result['payload_drift']==result['repository_input_drift']==[]
for name in ('source-pins.json','result.json','pytest.ini'):
    shutil.copyfile(root/name,HERE/name)
shutil.copyfile(root/'after/conftest.py',HERE/'executed-origin-plugin.py')
cases=[]
for run in result['cases']:
    assert run['exit_code']==0 and run['signals']==[]
    assert all(not item['alive'] for item in run['processes_after'])
    label=run['label']
    out=HERE/label
    out.mkdir(exist_ok=True)
    for path in (root/label).iterdir():
        if path.is_file() and path.suffix in ('.log','.json','.jsonl','.xml'):
            try:
                text=path.read_text(encoding='utf-8')
            except UnicodeDecodeError:
                text=path.read_text(encoding='cp1252')
            assert not re.search(r'(?:nxs_|nxsept_|nxc4_|nxt4_)[A-Za-z0-9_-]+',text),path.name
            (out/path.name).write_text(text,encoding='utf-8')
    for case in ET.parse(root/label/'junit.xml').iter('testcase'):
        assert case.find('failure') is None and case.find('error') is None and case.find('skipped') is None
        cases.append(dict(node=case.get('classname')+'::'+case.get('name'),status='PASS',
            evidence=label+'/junit.xml',seconds=float(case.get('time'))))
assert len([c for c in cases if c['evidence']=='init/junit.xml'])==21
assert len([c for c in cases if c['evidence']=='launch/junit.xml'])==4
for name,pin in allocation['fixtures'].items():
    original=REPO/'tests/execution_r4'/name
    executed=root/'after/tests/execution_r4'/name
    assert hashlib.sha256(original.read_bytes()).hexdigest()==pin
    assert original.read_bytes()==executed.read_bytes()
    shutil.copyfile(executed,HERE/('executed-'+name+'.txt'))
launch_source=(REPO/'tests/execution_r4/test_participant_launch.py').read_text()
selected={'test_client_configuration_selection_preserves_daemon_and_file_boundary',
          'test_cli_saved_plan_is_passive_and_replay_does_not_launch'}
not_requested=[n.name for n in ast.parse(launch_source).body if isinstance(n,ast.FunctionDef)
    and n.name.startswith('test_') and n.name not in selected]
report=dict(status='PASS_SCOPED_INSTALLED_PARTICIPANT_REGRESSION',scenario='QC-T-I05',proposed_status='PASS',
    passed=25,init_passed=21,launch_focal_passed=4,cases=cases,
    wheel_sha256='a36e448c80a8190c7e8c92d81ea5a251c4bdf7e370eca0f0b395a5ad29e36cc6',
    fixture_hashes=allocation['fixtures'],fixtures_byte_identical_before_after=True,
    input_pins='source-pins.json',payload_files=1027,payload_drift=[],repository_input_drift=[],
    commands=[dict(label=run['label'],argv=run['argv'],cwd=run['cwd'],
        deadline_seconds=run['deadline_seconds'],exit_code=0,signals=[],
        origins=[run['label']+'/origins.json',run['label']+'/origins-finish.json'],
        owned_processes_absent=True) for run in result['cases']],
    safety_inspection=[
        'test_participant_init.setup creates MemoryVault and replaces participant_client.open_backend before TerminalParticipant operations; successful vault write count assertions prove the synthetic vault path.',
        'HTTPBridge replaces urllib opener and forwards only participant-context GETs to the owned real TestClient, with own synthetic agent key. It does not reach the named external origin.',
        'The explicit redirect negative uses a real127.0.0.1 temporary HTTPServer, a hardcoded synthetic bearer, and finally shutdown/join/server_close; no provider or personal endpoint.',
        'Selected launch configuration tests call review only; the passive replay launch fixture replaces participant_process.spawn with a pid1234/wait0 inert object. No provider executable is launched.',
        'Client config paths, participant home, backups and protected files are all under owned temporary directories. System credential backends are never selected by these fixture paths.',
        'Outer environment allowlist uses own HOME/USERPROFILE/APPDATA/LOCALAPPDATA/TEMP/TMP; inherited provider secrets/proxies/OKTO/NEXUS config and real CLI paths are not copied.'
    ],unsafe_exclusions=[],launch_not_requested=not_requested,
    asserted_behavior=[
        'init and connect --mode participant share canonical review/apply/checkpoints for claude,codex,generic; synthetic keys are absent from client configuration/profile/public JSON and vault writes remain1 on replay.',
        'Identity/workspace authentication, policy/review/file drift, lost checkpoint recovery, vault failure, uncertain later edits and redirect refusal preserve canonical server snapshots.',
        'Codex default config selection keeps --no-daemon; a selected arbitrary Codex config is refused before launch; Claude explicit config retains exact --mcp-config path.',
        'Saved launch plan does not reread vault; explicit apply uses synthetic spawn1 and replay does not launch again; new review requires explicit --new.'
    ],limitations=[
        'Installed application + real ASGI HTTP/auth/SQLite, real owned files/ACL/backup behavior and loopback redirect; input, vault, service/harness verification and launch peer boundaries are synthetic.',
        'No Windows Credential Manager, personal config, real Codex/Claude CLI, provider/model, daemon startup, native MCP readiness or human acceptance is claimed.',
        'Full participant_launch.py was not run. Only two requested test functions, four expanded cases, executed; remaining functions are listed as not requested, not falsely unsafe or PASS.',
        'No expectations or test fixtures were modified. No product/normative tests/docs/ledger/Git/build/prefix mutation; only reviewable scripts/hashes/XML/logs are curated.',
        'Both finite cuts ended naturally. All retained exact own PID handles report exit, no termination signals,1027 exact wheel payload files and source pins unchanged.'
    ])
(HERE/'qualification.json').write_text(json.dumps(report,indent=2)+'\n')
(HERE/'report.md').write_text('# QC29 participant regression\n\n**25 PASS:** entire participant_init file (21), plus configuration selection and passive replay launch focals (4). '
    'Fixtures remained byte-identical; installed application origins and all1,027 payload files are unchanged.\n\n'
    'I05 is covered at CLI/HTTP/SQLite with MemoryVault, HTTPBridge and inert launch peers. '
    'The main init/connect participant paths share review/checkpoints; replay remains passive and protected client file/config selection is preserved. '
    'No personal vault/config or Codex/Claude provider process was accessed.\n\n'
    'Other participant launch tests were outside this requested cut. No native readiness, live MCP, provider or human acceptance claim is made. '
    'Both cuts exited naturally, without cleanup signals or source changes.\n')
manifest={p.relative_to(HERE).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
    for p in HERE.rglob('*') if p.is_file() and p.name!='manifest.json' and '__pycache__' not in p.parts}
(HERE/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps(dict(passed=25,manifest_entries=len(manifest),
    qualification_sha256=hashlib.sha256((HERE/'qualification.json').read_bytes()).hexdigest())))

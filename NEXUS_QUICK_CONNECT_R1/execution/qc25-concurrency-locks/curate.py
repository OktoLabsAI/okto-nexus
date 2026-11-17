"""Preserve each executed cut, including failed fixture preconditions."""
import ast
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]
TEMP=Path('C:/Users/jpamb/AppData/Local/Temp')
specs=[('nexus-qc25-concurrency-gzdtkvj5','initial-observer-antecedent'),
       ('nexus-qc25-concurrency-w3zpa0tw','locks-final-race-antecedent'),
       ('nexus-qc25-concurrency-ymdhelgk','inventory-revision-antecedent'),
       ('nexus-qc25-concurrency-2xaguvpm','raw-inventory-route-antecedent'),
       ('nexus-qc25-concurrency-iq_ho7im','race-final')]
reports=[]
for name,label in specs:
    root=TEMP/name
    out=HERE/label
    out.mkdir(exist_ok=True)
    result=json.loads((root/'result.json').read_text())
    for name in ('result.json','source-pins.json','pytest.ini'):
        shutil.copyfile(root/name,out/name)
    shutil.copyfile(root/'after/conftest.py',out/'executed-origin-plugin.py')
    shutil.copyfile(root/'after/tests/quick_connect/test_qc25_concurrency_locks.py',out/'executed-test.py')
    for run in result['cases']:
        folder=root/run['label']
        dest=out/run['label']
        dest.mkdir(exist_ok=True)
        for path in folder.iterdir():
            if path.is_file() and path.suffix in ('.json','.jsonl','.log','.xml'):
                try:
                    value=path.read_text(encoding='utf-8')
                except UnicodeDecodeError:
                    value=path.read_text(encoding='cp1252')
                assert not re.search(r'(?:nxs_|nxsept_|nxc4_|nxt4_)[A-Za-z0-9_-]+',value),path.name
                (dest/path.name).write_text(value,encoding='utf-8')
        assert not run['signals'] and all(not p['alive'] for p in run['processes_after'])
    assert result['payload_files']==1027 and result['payload_drift']==result['repository_input_drift']==[]
    reports.append(dict(evidence=label,root=str(root),cases=[dict(label=r['label'],exit_code=r['exit_code'],
        command=r['argv'],cwd=r['cwd'],signals=[],owned_processes_absent=True) for r in result['cases']],
        payload_files=1027,payload_drift=[],repository_input_drift=[]))

locks=HERE/'locks-final-race-antecedent'
race=HERE/'race-final/race'
expected=[]
for path in (locks/'busy/junit.xml',locks/'input/junit.xml',race/'junit.xml'):
    case,=list(ET.parse(path).iter('testcase'))
    assert case.find('failure') is None and case.find('error') is None and case.find('skipped') is None
    expected.append(dict(node=case.get('classname')+'::'+case.get('name'),evidence=path.relative_to(HERE).as_posix(),status='PASS'))
def function(path,name):
    text=path.read_text(encoding='utf-8')
    node=next(n for n in ast.parse(text).body if isinstance(n,ast.FunctionDef) and n.name==name)
    return '\n'.join(text.splitlines()[node.lineno-1:node.end_lineno])
for name in ('test_g12_profile_guard_busy_fails_fast_then_same_review_recovers',
             'test_g12_catalog_lock_free_during_input_and_old_profile_released_after_customize'):
    assert function(locks/'executed-test.py',name)==function(HERE/'test_concurrency_locks.py',name)
race_proof=json.loads((race/'race-proof.json').read_text())
busy_proof=json.loads((locks/'busy/busy-proof.json').read_text())
input_proof=json.loads((locks/'input/input-lock-proof.json').read_text())
assert set(race_proof['counts'].values())=={1} and race_proof['tests']==1
assert all(item['exit_code']==0 for item in input_proof['subprocesses'])
probe_pids=sorted({pid for item in input_proof['subprocesses'] for pid in (item['pid'],item['launcher_pid'])})
filter_query='('+ ' OR '.join('ProcessId='+str(pid) for pid in probe_pids)+") AND CommandLine LIKE '%nexus-qc25-concurrency-%'"
script="Get-CimInstance Win32_Process -Filter \""+filter_query+"\" | Select-Object ProcessId,ParentProcessId,CreationDate,ExecutablePath | ConvertTo-Json -Depth 3"
(HERE/'probe-cleanup.ps1').write_text(script+'\n')
cleanup=subprocess.run([shutil.which('rtk'),'proxy','powershell','-NoProfile','-File',str(HERE/'probe-cleanup.ps1')],
    capture_output=True,text=True,timeout=20,check=True)
observed=json.loads(cleanup.stdout) if cleanup.stdout.strip() else []
assert not observed,observed
(HERE/'probe-cleanup.json').write_text(json.dumps(dict(probe_pids=probe_pids,
    owned_namespace_readers=[],subprocess_exit_codes=[p['exit_code'] for p in input_proof['subprocesses']],
    process_termination_issued=False),indent=2)+'\n')
report=dict(status='THREE_SCOPED_FOCALS_PASS_WITH_PRECONDITION_ANTECEDENTS',passed=3,
    wheel_sha256='a36e448c80a8190c7e8c92d81ea5a251c4bdf7e370eca0f0b395a5ad29e36cc6',
    cases=expected,cuts=reports,
    scenarios=[dict(ids=['QC-T-C18','QC-T-G15'],proposed_status='PASS',evidence='race-final/race/race-proof.json',
        scope='Two first JSON reviews, exact approvals in threads, Barrier at actual canonical reserve, one winner Finish and one refused before second Test'),
        dict(ids=['QC-T-G12'],proposed_status='PASS',evidence=[
            'locks-final-race-antecedent/busy/busy-proof.json','locks-final-race-antecedent/input/input-lock-proof.json'],
            scope='Real profile lock busy/release/recovery, real subprocess acquisition of global catalog guard during input and old profile guard after customization restart')],
    race=race_proof,busy=busy_proof,input_locks=input_proof,probe_cleanup='probe-cleanup.json',
    antecedents=[
        'Initial attempt overlapped two unqualified version checks: real canonical single-flight denied one before reserve, so Barrier did not have two arrivals. stdout routing restoration also caused teardown observation error; not a completed namespace race.',
        'Corrected observation still showed legitimate version-check single-flight. Busy and input lock tests passed in that same three-cut campaign and were not repeated.',
        'Staggering launch until A reached reserve removed overlap but B correctly rejected stale inventory revision from its earlier review; still not the desired namespace-race given.',
        'First precheck setup requested raw inventory through dashboard management surface, which does not expose that route; fixture failed before concurrency.',
        'Final given performs one real authorized installation:check with inert version peer before both first reviews. Both canonical reviews explicitly require no additional version check; root remains unmapped and authority tables empty. Both real approvals can then rendezvous at reserve without bypassing version/inventory fences.'
    ],limitations=[
        'Installed CLI function entry + canonical real ASGI HTTP/SQLite + real OS file locks/subprocesses. Service lifecycle, discovery/version/model Test peers are explicitly synthetic; no real provider/native harness/personal auth/daemon.',
        'Version precheck1 is a legitimate separately authorized setup effect with runtime_authorized false, not a Test/admission/grant. It precedes the two reviews; the final race produces exactly one synthetic Test and one canonical Finish.',
        'No input, cwd, env mutation in race threads. A parent-installed stdout router preserves each actual JSON document and is restored before pytest teardown.',
        'Lock probes are installed -I-B child interpreters, stdin closed, five-second bounds, explicit three-module origins/PIDs/zero exit codes. Subsequent own-namespace process query is empty; no stop was issued.',
        'Each cut has1027 exact package payload files and unchanged src/tests/docs pins, installed origins at session start/finish, own retained PID handles physically exited and zero termination signals.',
        'G12 evidence remains on its exact earlier executed module bytes; only race was subsequently rerun. No claim of one combined3PASS run.',
        'No product/normative tests/docs/ledger/Git/build/prefix mutation; raw DB/vault/keys stay outside repository.'
    ])
(HERE/'qualification.json').write_text(json.dumps(report,indent=2)+'\n')
(HERE/'report.md').write_text('# QC25 concurrency and locks\n\n**Three scoped focals PASS across separate cuts.**\n\n'
    'C18/G15: two first JSON reviews for distinct profiles over the same unmapped root were approved with exact hashes in threads. '
    'Both actual canonical reservation POSTs rendezvoused at the Barrier. One finished; the other received CONNECT_ID_PENDING before a second Test. '
    'Workspace, project draft, public ID, binding, grant and receipt counts are exactly one each; the directory recognizes the winning workspace.\n\n'
    'A legitimate inert installation version check is completed before both reviews. Earlier attempts did not reach the namespace-race given because real version single-flight or inventory-revision fences correctly refused one participant; those attempts remain preserved.\n\n'
    'G12: PROFILE_BUSY is bounded under five seconds without changing review bytes or authority tables; after releasing the exact guard the same review is recoverable. '
    'Installed child interpreters also acquire/release catalog.guard during input, and old profile.guard after customization restarts. The new review stays unapproved. '
    'Probe PIDs, origins, zero exits and subsequent absence are recorded.\n\n'
    'No provider or personal login was used. Package payloads1027 and source inputs have zero drift, own processes exited without signals. No product or ledger changes.\n')
manifest={p.relative_to(HERE).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
    for p in HERE.rglob('*') if p.is_file() and p.name!='manifest.json' and '__pycache__' not in p.parts}
(HERE/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps(dict(passed=3,manifest_entries=len(manifest),
    qualification_sha256=hashlib.sha256((HERE/'qualification.json').read_bytes()).hexdigest())))

"""Copy only reviewable public receipts; owned DB/vault/profile files stay Temp."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import xml.etree.ElementTree as ET
import zipfile

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
TEMP = Path('C:/Users/jpamb/AppData/Local/Temp')
roots = ['nexus-qc15-choice-wr5oy5i4', 'nexus-qc15-choice-4emspy8s',
         'nexus-qc15-choice-p_i2pnii', 'nexus-qc15-choice-b1fr23qm']
records = []
for number, name in enumerate(roots):
    root = TEMP / name
    destination = HERE / ('final' if number == 3 else 'antecedent-' + str(number + 1))
    destination.mkdir(exist_ok=True)
    for source, target in [('choices/raw.log', 'pytest.log'), ('choices/junit.xml', 'junit.xml'),
            ('choices/reports.jsonl', 'reports.jsonl'), ('choices/runner.json', 'runner.json'),
            ('choices/origins.json', 'origins.json'), ('choices/origins-finish.json', 'origins-finish.json'),
            ('choices/failed-call.json', 'failed-call.json'), ('result.json', 'result.json'),
            ('source-pins.json', 'source-pins.json'),
            ('after/tests/execution_r4/test_qc15_cli_choices.py', 'executed-test.py'),
            ('after/conftest.py', 'executed-origin-plugin.py'), ('pytest.ini', 'pytest.ini')]:
        path = root / source
        if path.exists():
            try:
                content = path.read_text(encoding='utf-8')
            except UnicodeDecodeError:
                # Windows redirected pytest stdout used the system code page.
                content = path.read_text(encoding='cp1252')
            assert not re.search(r'(?:nxs_|nxsept_|nxc4_|nxt4_)[A-Za-z0-9_-]+', content), target
            (destination / target).write_text(content, encoding='utf-8')
    result = json.loads((root / 'result.json').read_text())
    xml = ET.parse(root / 'choices/junit.xml')
    cases = [dict(name=case.get('name'), classname=case.get('classname'),
        status='FAIL' if case.find('failure') is not None or case.find('error') is not None else
               'SKIP' if case.find('skipped') is not None else 'PASS') for case in xml.iter('testcase')]
    assert all(not process['alive'] for item in result['cases'] for process in item['processes_after'])
    records.append(dict(root=str(root), evidence=destination.name, cases=cases,
        exit_code=result['cases'][0]['exit_code'], signals=result['cases'][0]['signals'],
        payload_files=result['payload_files'], payload_drift=result['payload_drift'],
        repository_input_drift=result['repository_input_drift'], owned_processes_absent=True))

package = TEMP / 'nexus-qc-r1-package-t24_dnfc'
payload = {}
for module, wheel in [('okto_nexus', package/'artifacts/okto_nexus-0.3.6-py3-none-any.whl'),
        ('nexus_connector_core', REPO/'vendor/wheels/okto_nexus_connector_core-0.0.14-py3-none-any.whl'),
        ('okto_nexus_connector', REPO/'vendor/ci/okto_nexus_connector-0.0.13-py3-none-any.whl')]:
    with zipfile.ZipFile(wheel) as archive:
        for name in archive.namelist():
            if name.startswith(module+'/') and not name.endswith('/'):
                data = (package/'venv/Lib/site-packages'/name).read_bytes()
                assert data == archive.read(name), name
                payload[name] = hashlib.sha256(data).hexdigest()
assert len(payload) == 1027
(HERE/'payload-after.json').write_text(json.dumps(payload, indent=2)+'\n', encoding='utf-8')
final = records[-1]
assert len(final['cases']) == 8 and all(case['status'] == 'PASS' for case in final['cases'])
ledger = json.loads((REPO/'NEXUS_QUICK_CONNECT_R1/NEXUS_QUICK_CONNECT_LEDGER_R1.json').read_text(encoding='utf-8'))
ids = ['QC-T-A03','QC-T-B03','QC-T-B05','QC-T-B06','QC-T-B07','QC-T-B08','QC-T-B09']
literal = {item['id']: {key:item.get(key) for key in ('title','given','when','then','layers')}
           for item in ledger['tests'] if item['id'] in ids}
mapping = [
    dict(id='QC-T-A03', proposed_status='PASS', nodes=[final['cases'][0]['name'],final['cases'][1]['name']],
         proof='Bare main.main connect without positional/provider-home reaches authorized two-family wizard, explicit choose/cancel, no argument error.'),
    dict(id='QC-T-B03', proposed_status='PASS', nodes=[case['name'] for case in final['cases'][:3]],
         proof='Both observed families listed with cancellation; explicit second choice reaches Claude-only home requirement; cancel and noninteractive refusal have no effects.'),
    dict(id='QC-T-B05', proposed_status='PASS', nodes=[final['cases'][7]['name']],
         proof='Production publisher accepts actual stale-age publication; runtime-options remains populated but STALE; CLI refuses INVENTORY_UNCONFIRMED, no fallback/missing interpretation.'),
    dict(id='QC-T-B06', proposed_status='PASS', nodes=[final['cases'][3]['name'],final['cases'][4]['name']],
         proof='Two actual candidate refs from runtime-options; answer2 survives selection and canonical review_request.candidate_ref; JSON refuses default-first.'),
    dict(id='QC-T-B07', proposed_status='NOT_RUN', nodes=[],
         proof='No new canonical method-denial mutation/API established for this fixture. Existing helper/unit policy proof is antecedent; no ACL or DTO denial invented.'),
    dict(id='QC-T-B08', proposed_status='PASS', nodes=[final['cases'][5]['name']],
         proof='Shell-like unsupported token enters installed CLI with Popen forbidden, returns authorized alternatives/CLIENT_SELECTION_REQUIRED; no Test/version or canonical table effects.'),
    dict(id='QC-T-B09', proposed_status='PASS', nodes=[final['cases'][6]['name']],
         proof='CoDeX normalizes through installed main to codex selection and codex_app_server canonical review.'),
]
report = dict(version=1, at=datetime.now(timezone.utc).isoformat(), status='PASS_SCOPED',
    final_counts=dict(passed=8,failed=0,skipped=0), cuts=records,
    installed_python=str(package/'venv/Scripts/python.exe'),
    wheel_sha256=hashlib.sha256((package/'artifacts/okto_nexus-0.3.6-py3-none-any.whl').read_bytes()).hexdigest(),
    command_evidence='final/runner.json', exact_nodes='final/junit.xml',
    source_pins='final/source-pins.json', payload_files=1027, payload_after='payload-after.json',
    origins=['final/origins.json','final/origins-finish.json'],
    scenarios=[dict(**row,literal=literal.get(row['id'])) for row in mapping],
    antecedent_oracles=[
        'Cut1 wrongly expected bare Claude review without required provider-home; actual explicit second choice safely refused PROVIDER_HOME_REQUIRED.',
        'Cut2 wrongly expected cancellation exit3/code; current installed contract returns exit0/state canceled.',
        'Cut3 looked for candidate_ref inside configuration; actual canonical SetupRequest keeps candidate_ref at its top level.'
    ], limitations=[
        'Actual installed Python CLI function entry + real ASGI HTTP/SQLite; interactive stdin/isatty are fixture-controlled, not native Windows PTY.',
        'Service lifecycle, discovery candidates, build/version checks and provider Test peers are explicitly inert/synthetic; no provider or credential access.',
        'Bare explicit Claude choice proves picker and safe required-home refusal, not full Claude onboarding/Test/Finish.',
        'B07 remains NOT_RUN in this increment; no novel authorization rule was added.',
        'No repository product/tests/docs/ledger/Git/build/install changes. Old source/R3 qualifications are not requalified.',
        'Raw owned homes/SQLite/vault/keys remain only in Temp; reviewable logs/scripts/XML/pins copied. All retained child PID creation handles report physical exit.',
        'Transient installed Python caches are not wheel payloads; all1027 covered package files matched their three wheels before/after each cut and at curation.'
    ])
(HERE/'qualification.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
lines = ['# QC15: installed CLI choice scenarios','',
    'Final cut: **8 PASS**, canonical HTTP/SQLite, installed application imports only. No provider or service process execution.',
    '', '| Scenario | Proposed status | Exact proof |','|---|---|---|']
for row in mapping:
    lines.append('| '+row['id']+' | '+row['proposed_status']+' | '+row['proof']+' |')
lines += ['', 'Exact commands, JUnit nodes and process birth/exit proofs: [final/runner.json](final/runner.json), [final/junit.xml](final/junit.xml).',
    '', 'Three failed oracle antecedents are retained individually; none is relabeled green. Their causes are recorded in [qualification.json](qualification.json).',
    '', 'Interactive input is controlled in the fixture. Native PTY, real provider/version/lifecycle, and completed Claude onboarding are outside these assertions. B07 remains unexecuted.',
    '', 'The 1,027 wheel payload files and source-input hashes had no drift; both session-boundary origin checks use installed site-packages. Owned processes exited naturally; no containment signals were sent.']
(HERE/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
manifest = {p.relative_to(HERE).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
            for p in HERE.rglob('*') if p.is_file() and p.name != 'manifest.json' and '__pycache__' not in p.parts}
(HERE/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
print(json.dumps(dict(status=report['status'],passed=8,manifest_files=len(manifest),
    qualification_sha256=hashlib.sha256((HERE/'qualification.json').read_bytes()).hexdigest())))

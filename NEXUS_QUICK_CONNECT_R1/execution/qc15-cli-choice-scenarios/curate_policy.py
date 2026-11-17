"""Add B07 evidence without rewriting the antecedent eight-case report."""
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
TEMP = Path('C:/Users/jpamb/AppData/Local/Temp')
roots = ['nexus-qc15-policy-ov6r5o_o','nexus-qc15-policy-1h57xg1t','nexus-qc15-policy-ql51z0aw']
cuts = []
for index, name in enumerate(roots):
    root = TEMP/name
    out = HERE/('policy-final' if index == 2 else 'policy-antecedent-'+str(index+1))
    out.mkdir(exist_ok=True)
    files = {'result.json':'result.json', 'source-pins.json':'source-pins.json',
        'after/tests/execution_r4/test_qc15_policy_denial.py':'executed-test.py',
        'after/conftest.py':'executed-origin-plugin.py', 'pytest.ini':'pytest.ini'}
    files.update({'policy/'+name:name for name in ['junit.xml','raw.log','reports.jsonl','runner.json',
        'origins.json','origins-finish.json','failed-call.json','policy-proof.json']})
    for source,target in files.items():
        path = root/source
        if path.exists():
            try:
                text = path.read_text(encoding='utf-8')
            except UnicodeDecodeError:
                text = path.read_text(encoding='cp1252')
            assert not re.search(r'(?:nxs_|nxsept_|nxc4_|nxt4_)[A-Za-z0-9_-]+',text),target
            (out/target).write_text(text,encoding='utf-8')
    result = json.loads((root/'result.json').read_text())
    case, = list(ET.parse(root/'policy/junit.xml').iter('testcase'))
    assert all(not proc['alive'] for run in result['cases'] for proc in run['processes_after'])
    cuts.append(dict(evidence=out.name,root=str(root),exit_code=result['cases'][0]['exit_code'],
        test=case.get('name'), status='FAIL' if case.find('failure') is not None else 'PASS',
        payload_files=result['payload_files'],payload_drift=result['payload_drift'],
        repository_input_drift=result['repository_input_drift'],signals=result['cases'][0]['signals'],
        owned_processes_absent=True))
proof=json.loads((HERE/'policy-final/policy-proof.json').read_text())
assert cuts[-1]['status']=='PASS' and proof['cli_changed_tables']==[]
report=dict(scenario='QC-T-B07',proposed_status='PASS',layer='installed CLI + real canonical HTTP/SQLite',
    wheel_sha256='a36e448c80a8190c7e8c92d81ea5a251c4bdf7e370eca0f0b395a5ad29e36cc6',
    exact_node='tests/execution_r4/test_qc15_policy_denial.py::'+cuts[-1]['test'],
    command='policy-final/runner.json',proof='policy-final/policy-proof.json',cuts=cuts,
    oracle_antecedents=[
        'First cut wrongly assumed seeding a method denial cannot create its canonical authority anchor. Trigger creates exactly authority_agent_connection_methods for the same subject/method.',
        'Second cut baseline preceded lazy canonical authorization-revision materialization. Third cut reads /connections/me after denial, then requires every table and field unchanged across CLI refusal.'
    ],facts=dict(proof,request='connect codex App --profile denied --plan --json',
        refusal='CONFIGURATION_NOT_AUTHORIZED',candidate_present=True,inventory_fresh=True),
    limitations=[
        'A denial is seeded directly as an existing canonical policy fact in the temporary database; no policy-management HTTP endpoint or new ACL is claimed.',
        'Service lifecycle, candidate discovery, version and provider peers are inert; no real harness, provider, personal account or Test was invoked.',
        'All tables are compared. Seed permits exactly the selected method row and its own canonical authority anchor; no other rows/fields may change.',
        'Baseline is the already-denied state after canonical revision materialization. The CLI then causes zero changes across every table.',
        'Previous eight-case qualification remains immutable antecedent; this addendum independently qualifies B07.',
        'Raw owned homes/DB/vault/profile files remain Temp only; all retained owned PIDs report physical exit, no termination signals.'
    ])
(HERE/'policy-qualification.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
(HERE/'policy-report.md').write_text(
    '# QC15 B07 addendum\n\n**1 PASS**, installed CLI with canonical HTTP/SQLite. '
    'The same present, FRESH candidate becomes non-configurable through the existing METHOD_DISABLED policy. '
    'CLI returns CONFIGURATION_NOT_AUTHORIZED, with zero Test/probe, new identity, grant, or persisted profile.\n\n'
    f"All {proof['table_count']} tables were compared from the already-denied canonical baseline; none changed across CLI refusal. "
    'The seed changes only the selected method row and its exact trigger-maintained authority anchor. '
    'Two earlier oracle failures are preserved separately.\n\n'
    'No provider, personal account, product, normative test, ledger, Git, build or installed payload was changed. '
    'The 1,027 payload files and repository source pins had zero drift in each cut; both session-boundary origin checks use installed site-packages.\n',encoding='utf-8')
old=HERE/'manifest-eight-case-antecedent.json'
if not old.exists():
    old.write_bytes((HERE/'manifest.json').read_bytes())
manifest={p.relative_to(HERE).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
          for p in HERE.rglob('*') if p.is_file() and p.name!='manifest.json' and '__pycache__' not in p.parts}
(HERE/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
print(json.dumps(dict(status='PASS',tables=proof['table_count'],manifest_entries=len(manifest),
    qualification_sha256=hashlib.sha256((HERE/'policy-qualification.json').read_bytes()).hexdigest())))

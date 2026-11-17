"""Namespace evidence only; no source, ledger, package or Git mutations."""
import ast
import hashlib
import json
from pathlib import Path
import re
import shutil
import xml.etree.ElementTree as ET

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]
TEMP=Path('C:/Users/jpamb/AppData/Local/Temp')
cuts=[]
for name,partition,label in [
    ('nexus-qc24-namespace-h8li_lxe','namespace','namespace-final'),
    ('nexus-qc24-executor-zbu50jrd','executor','executor-oracle-1'),
    ('nexus-qc24-executor-n6nvv6bh','executor','executor-oracle-2'),
    ('nexus-qc24-executor-v3vlwb8y','executor','executor-final')]:
    root=TEMP/name
    dest=HERE/label
    dest.mkdir(exist_ok=True)
    for path in (root/partition).iterdir():
        if path.is_file() and path.suffix in ('.json','.jsonl','.xml','.log'):
            try:
                value=path.read_text(encoding='utf-8')
            except UnicodeDecodeError:
                value=path.read_text(encoding='cp1252')
            assert not re.search(r'(?:nxs_|nxsept_|nxc4_|nxt4_)[A-Za-z0-9_-]+',value),path.name
            (dest/path.name).write_text(value,encoding='utf-8')
    for source,target in [('source-pins.json','source-pins.json'),('result.json','result.json'),
        ('after/conftest.py','executed-origin-plugin.py'),('pytest.ini','pytest.ini'),
        ('after/tests/execution_r4/test_qc24_namespace_http.py','executed-namespace-test.py'),
        ('after/tests/execution_r4/test_qc24_namespace_executor_http.py','executed-executor-test.py')]:
        if (root/source).exists():
            shutil.copyfile(root/source,dest/target)
    result=json.loads((root/'result.json').read_text())
    run=result['cases'][0]
    assert result['payload_files']==1027 and result['payload_drift']==result['repository_input_drift']==[]
    assert not run['signals'] and all(not process['alive'] for process in run['processes_after'])
    cases=[dict(name=c.get('name'),classname=c.get('classname'),
        status='FAIL' if c.find('failure') is not None or c.find('error') is not None else 'PASS')
        for c in ET.parse(root/partition/'junit.xml').iter('testcase')]
    cuts.append(dict(evidence=label,root=str(root),exit_code=run['exit_code'],cases=cases,
        payload_files=1027,payload_drift=[],repository_input_drift=[],owned_processes_absent=True,signals=[]))
assert all(c['status']=='PASS' for c in cuts[0]['cases']+cuts[-1]['cases'])

# E08 is a read-only reconciliation of an already executed exact node. The
# original source pins qualify the helper and test body, rather than a label.
oldbase=REPO/'NEXUS_QUICK_CONNECT_R1/execution/qc09-qc-installed/shard1'
oldpins=json.loads((oldbase/'input-before.json').read_text())
sources=['tests/execution_r4/test_public_connection_ids.py','tests/execution_r4/test_embedded_inventory.py']
assert all(hashlib.sha256((REPO/path).read_bytes()).hexdigest()==oldpins[path] for path in sources)
node='test_two_servers_same_workspace_ids_do_not_share_namespace'
cases=[case for case in ET.parse(oldbase/'tests.xml').iter('testcase') if case.get('name')==node]
case,=cases
assert case.find('failure') is None and case.find('error') is None and case.find('skipped') is None
def body(path,name):
    text=(REPO/path).read_text(encoding='utf-8')
    parsed=ast.parse(text)
    match=next(n for n in parsed.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name==name)
    return '\n'.join(text.splitlines()[match.lineno-1:match.end_lineno])+'\n'
e08=dict(scenario='QC-T-E08',proposed_status='PASS',newly_executed=False,
    layer='Previously executed installed application + two real owned SQLite databases',
    exact_node=case.get('classname')+'::'+node,xml=str((oldbase/'tests.xml').relative_to(REPO)),
    xml_sha256=hashlib.sha256((oldbase/'tests.xml').read_bytes()).hexdigest(),
    original_wheel_sha256='01eb1ce064f62b09630c24b5ad339814b9e46c429a7c4e7ebf7561eae23cfff6',
    source_file_pins={path:oldpins[path] for path in sources},source_files_match_executed_pins=True,
    reasoning=[
        'local_setup constructs first application/factory at its owned home; app_for(tmp_path/second-server) bootstraps a second independent factory/home.',
        'bootstrap passes distinct --home values; config.db_path defaults to home_dir/nexus.db and ConnectionFactory opens config.db_path. These are distinct physical database paths, not two mocked DTOs.',
        'ensure_execution_installation persists the second Server installation; both databases receive the same literal workspace ID, same display label and same public Harness ID.',
        'reserve/list execute against each distinct connection factory; test asserts one occupant in each and different ServerIDs.',
        'No daemon or native harness is required to demonstrate Server/workspace namespace isolation at this unit+SQLite level.'
    ],limits=['Covers reserved registry occupants and namespace isolation, not two bound native runtime sessions or real hosts. No new E08 execution on a36 is claimed.'])
(HERE/'e08-reconciliation.json').write_text(json.dumps(e08,indent=2)+'\n')
(HERE/'e08-executed-test-and-helper.py.txt').write_text(body(sources[0],node)+'\n'+body(sources[1],'app_for'),encoding='utf-8')
ET.ElementTree(case).write(HERE/'e08-antecedent-testcase.xml',encoding='utf-8',xml_declaration=True)
proofs={name:json.loads((HERE/directory/name).read_text()) for directory,names in [
    ('namespace-final',['e07-proof.json','e09-proof.json']),('executor-final',['e06-proof.json'])] for name in names}
report=dict(status='THREE_NEW_FOCALS_PASS_PLUS_E08_ANTECEDENT_RECONCILIATION',new_tests_passed=3,
    wheel_sha256='a36e448c80a8190c7e8c92d81ea5a251c4bdf7e370eca0f0b395a5ad29e36cc6',
    cuts=cuts,proofs=proofs,
    proposed_scenarios=[dict(id='QC-T-E09',status='PASS',evidence='namespace-final/e09-proof.json'),
        dict(id='QC-T-E07',status='PASS',evidence='namespace-final/e07-proof.json'),
        dict(id='QC-T-E06',status='PASS',evidence='executor-final/e06-proof.json'),
        dict(id='QC-T-E08',status='PASS',evidence='e08-reconciliation.json',newly_executed=False)],
    oracle_antecedents=[
        'E06 first variant sent null configuration root/candidate fields; SetupRequest rejected malformed request before namespace collision.',
        'E06 second variant retained required root string but still sent candidate_ref/inventory_revision null; API requires omitted/default strings. Final fixture omits these fields and prohibits local directory_identity on remote proof.'
    ],limitations=[
        'All new tests use installed application origins, canonical real ASGI HTTP/SQLite, own temporary home and synthetic exact Test-verification peer; no provider, native model, service daemon or personal auth.',
        'E07 workspaces are both created by actual HTTP Finish; public IDs bound with distinct workspace/binding/endpoint/workspace-binding refs and two distinct scoped grants. Same Server/executor/agent fields intentionally remain the same.',
        'E06 second executor is genuinely subject-authorized via registration API. It is not connected to a physical host and no inventory/remote transport/handshake authority is fabricated. Namespace uniqueness across executors is the asserted behavior.',
        'E09 starts with an actual Finish-created existing workspace, then exercises HTTP case normalization, fresh-intent collision and three case-variant queries of the same reserved occupant.',
        'All1027 installed wheel payload files and src/tests/docs pins had zero drift per cut. Own retained PID creation handles all report exit, with no termination signals.',
        'E08 remains tied to the older exact executed source/payload cut. No new provider/host/lifecycle or generalized qualification is inherited.',
        'No product/normative tests/docs/ledger/Git/build/prefix mutations. Only public scripts/logs/XML/hashes/receipts were copied; raw DB/vault/keys remain Temp.'
    ])
(HERE/'qualification.json').write_text(json.dumps(report,indent=2)+'\n')
(HERE/'report.md').write_text('# QC24 namespace scenarios\n\n**3 new focused tests PASS**, plus read-only E08 reconciliation.\n\n'
    '- E09: HTTP CoDeX normalizes to codex; a new codex intent conflicts, and three case queries return the same occupant.\n'
    '- E07: same ID bound through two HTTP Finishes into distinct, Finish-created workspaces, references and grants.\n'
    '- E06: an actual subject-authorized second executor cannot split the same Server/workspace namespace; no local stat, new grant or remote transport.\n'
    '- E08: existing executed test uses two independent homes/factories/SQLite databases and different ServerIDs with the same workspace ID and public ID. This satisfies namespace isolation at the specified layer; no daemon/provider claim.\n\n'
    'Two malformed-request E06 oracle antecedents remain preserved. All cuts exited naturally, with zero package/source drift and1027 exact payload files. E08 is tied to its older executed cut, not falsely repeated.\n')
manifest={p.relative_to(HERE).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
    for p in HERE.rglob('*') if p.is_file() and p.name!='manifest.json' and '__pycache__' not in p.parts}
(HERE/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps(dict(new_pass=3,e08='PASS_ANTECEDENT_RECONCILIATION',manifest_entries=len(manifest),
    qualification_sha256=hashlib.sha256((HERE/'qualification.json').read_bytes()).hexdigest())))

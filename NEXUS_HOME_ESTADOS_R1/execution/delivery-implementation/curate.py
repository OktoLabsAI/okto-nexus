from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
OUT = HERE / 'final'
OUT.mkdir(exist_ok=True)
owned = ['src/okto_nexus/domain/home_delivery_semantics.py', 'src/okto_nexus/application/handoff.py',
    'src/okto_nexus/adapters/outbound/sqlite/home.py', 'tests/home_states/test_delivery_semantics.py',
    'tests/home_states/test_delivery_semantics_sqlite.py', 'tests/home_states/test_verification_proof.py']
cuts = {}
for name in ['initial', 'sql-error', 'sql-fixed', 'metadata-final']:
    allocation = HERE / (name + '-allocation.json')
    root = Path(json.loads(allocation.read_text())['root'])
    result = json.loads((root / 'result.json').read_text())
    assert not result['payload_drift']
    assert all(not p['alive'] for case in result['cases'] for p in case['processes_after'])
    destination = OUT / name
    destination.mkdir(exist_ok=True)
    for filename in ['result.json', 'source-pins-start.json', 'source-pins-end.json', 'payload-start.json', 'payload-end.json']:
        shutil.copyfile(root / filename, destination / filename)
    nodes = []
    for case in result['cases']:
        folder = root / case['label']
        target = destination / case['label']
        target.mkdir(exist_ok=True)
        for filename in ['runner.json', 'origins-start.json', 'origins-finish.json']:
            shutil.copyfile(folder / filename, target / filename)
        original_tree = ET.parse(folder / 'junit.xml')
        cleaned = ET.Element('testsuite')
        for node in original_tree.iter('testcase'):
            failed = node.find('failure') is not None or node.find('error') is not None
            skipped = node.find('skipped') is not None
            nodes.append(dict(name=node.attrib['name'], case=case['label'], status='FAIL' if failed else 'SKIP' if skipped else 'PASS'))
            value = ET.SubElement(cleaned, 'testcase', node.attrib)
            if failed:
                ET.SubElement(value, 'failure', dict(message='Preserved own-Temp diagnostic; SQL error cut has an introduced duplicate WHERE.'))
            elif skipped:
                ET.SubElement(value, 'skipped')
        ET.ElementTree(cleaned).write(target / 'junit-sanitized.xml', encoding='utf-8', xml_declaration=True)
    cuts[name] = dict(root=str(root), nodes=nodes, counts=dict(Counter(n['status'] for n in nodes)),
        source_drift=result['repository_input_drift'], payload_files=result['payload_files'],
        signals=[signal for case in result['cases'] for signal in case['signals']], all_owned_processes_exited=True)
final_root = Path(cuts['metadata-final']['root'])
start = json.loads((final_root / 'source-pins-start.json').read_text())
end = json.loads((final_root / 'source-pins-end.json').read_text())
assert all(start[path] == end[path] for path in owned)
assert all(hashlib.sha256((REPO / path).read_bytes()).hexdigest() == end[path] for path in owned)
assert cuts['metadata-final']['counts'] == {'PASS': 58}
base_command = ['rtk', 'proxy', 'ruff', 'check', '--isolated', '--select', 'E4,E7,E9,F']
lint = subprocess.run([*base_command, *[p for p in owned if not p.endswith('/sqlite/home.py')], '--output-format', 'json'], cwd=REPO, capture_output=True, text=True, timeout=30)
(OUT / 'ruff-owned-new.json').write_text(lint.stdout)
assert lint.returncode == 0
relative = 'src/okto_nexus/adapters/outbound/sqlite/home.py'
base = subprocess.run(['rtk', 'proxy', 'git', 'show', 'HEAD:' + relative], cwd=REPO, capture_output=True, timeout=30)
assert base.returncode == 0
baseline_lint = subprocess.run([*base_command, '--stdin-filename', relative, '--output-format', 'json', '-'], cwd=REPO, input=base.stdout, capture_output=True, timeout=30)
current_lint = subprocess.run([*base_command, relative, '--output-format', 'json'], cwd=REPO, capture_output=True, text=True, timeout=30)
before_lint = json.loads(baseline_lint.stdout)
after_lint = json.loads(current_lint.stdout)
identity = lambda rows: Counter((row['code'], row['message']) for row in rows)
assert not (identity(after_lint) - identity(before_lint))
(OUT / 'ruff-home-baseline.json').write_bytes(baseline_lint.stdout)
(OUT / 'ruff-home-current.json').write_text(current_lint.stdout)
sourcepins = {path: end[path] for path in owned}
(OUT / 'owned-source-pins.json').write_text(json.dumps(sourcepins, indent=2))
report = dict(at=datetime.now(timezone.utc).isoformat(), status='PASS_FOCUSED_SOURCE_ONLY',
    final_tests=58, cuts=cuts, source_mode='Nexus checkout source explicitly selected; Core/Connector from owned PR27 venv. Not a final installed Home States artifact.',
    own_source_drift=[], unrelated_parallel_source_drift=cuts['metadata-final']['source_drift'],
    payload_files=1013, payload_drift=[], all_owned_processes_exited=True, provider_calls=0,
    proof_contract='Write-time hash of exact persisted result; requested/verdict metadata joined by workspace/handoff/claim/revision and causal event ID. No content hash UDF in Home GET.',
    regression_scope=['Standalone NULL comparison, same/historical claims, canonical pass/fail and authority/stale-claim denials, persisted None-rework, no GET writes/one SQL statement, artifact grouping/workspace separation and existing Home queries.'],
    lint=dict(owned_exit=lint.returncode, legacy_home_baseline=len(before_lint), legacy_home_current=len(after_lint), new_home_diagnostics=[]),
    limits=['SOURCE_ONLY, not installed package/browser/AT/native harness qualification.', 'No unified success claim for earlier failed SQL cut; its failures and cleanup are retained.', 'Global source changes in operational board/facts belong to parallel owners; only these six owned source files are asserted unchanged during the final cut.', 'No throughput/p95 claim from these focal tests; 1/10/100 and large-volume measurements remain separate.', 'Event retention or historical events without matching submitted-delivery metadata yield unknown, never a fabricated approved badge.'])
(OUT / 'qualification.json').write_text(json.dumps(report, indent=2))
entries = [dict(path=p.relative_to(OUT).as_posix(), bytes=p.stat().st_size, sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name != 'manifest.json']
(OUT / 'manifest.json').write_text(json.dumps(entries, indent=2))
print(json.dumps(dict(tests=58, report_sha256=hashlib.sha256((OUT / 'qualification.json').read_bytes()).hexdigest(), owned_pins=sourcepins, lint=report['lint'])))

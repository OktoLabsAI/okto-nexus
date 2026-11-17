"""Curate the actual R6 supplement; preserve the original R5/package cuts."""
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
root = Path(json.loads((HERE / 'allocation.json').read_text())['root'])
run = json.loads((root / 'result.json').read_text())
inventory = json.loads((root / 'reports/inventory.json').read_text())
phases = [json.loads(line) for line in (root / 'reports/phases.jsonl').read_text().splitlines()]
assert run['exit_code'] == 0 and not run['timed_out'] and not run['forced'] and not run['signals']
assert not any(run[field] for field in ('payload_drift', 'source_drift', 'helper_drift', 'remaining_known_processes'))
assert len(inventory['collected']) == len(inventory['finished']) == 11 and not inventory['not_run']
assert set(inventory['collected']) == set(inventory['finished'])
assert len({item['nodeid'] for item in phases if item['phase'] == 'call' and item['outcome'] == 'passed'}) == 11
assert all(item['outcome'] == 'passed' for item in phases)
assert run['base_build_source_pin_count'] == 1824 and run['guarded_source_test_pin_count'] == 1825

copies = [
    'TESTS_READY.json', 'result.json', 'source-before.json', 'source-after.json',
    'payload-before.json', 'payload-after.json', 'copied-tests.json',
    'copied-helpers-before.json', 'copied-helpers-after.json',
    'reports/collected.json', 'reports/inventory.json',
    'reports/origins-start.json', 'reports/origins-end.json',
]
out = HERE / 'evidence'
assert not out.exists()
out.mkdir()
manifest = {}
for name in copies:
    source, dest = root / name, out / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(source.read_bytes())
    manifest[name] = hashlib.sha256(dest.read_bytes()).hexdigest()
(out / 'phase-inventory.json').write_text(json.dumps(phases, indent=2) + '\n', encoding='utf-8')
xml = ET.parse(root / 'reports/tests.xml')
for parent in xml.iter():
    for child in list(parent):
        if child.tag in ('system-out', 'system-err'):
            parent.remove(child)
xml.write(out / 'tests-sanitized.xml', encoding='utf-8', xml_declaration=True)
report = dict(at=datetime.now(UTC).isoformat(), status='PASS_R6_INSTALLED_SUPPLEMENT',
    counts=dict(PASS=11, SKIP=0, FAIL=0, ERROR=0, NOT_RUN=0),
    collected=inventory['collected'], runtime_source_commit=run['runtime_source_commit'],
    runtime_wheel_sha256=json.loads((HERE / 'TESTS_READY.json').read_text())['runtime_wheel_sha256'],
    new_test_file=run['additional_test_pins'], existing_build_pins=1824, guarded_total_pins=1825,
    process_exit=0, timed_out=False, force_used=False, remaining_known_processes=[],
    source_payload_helper_drift=[], provider_calls=0, human=False,
    stdout=dict(raw_preserved=str(root / 'reports/stdout.log'),
        sha256=hashlib.sha256((root / 'reports/stdout.log').read_bytes()).hexdigest()),
    layers=dict(canonical_handoff_rejection=1, historical_read_contracts=5,
        original_recipient_api_authorization=3, canonical_private_operator_message_handoff=2),
    limitations=[
        'These eleven ran on R6 after build; the original 251 remain R5 execution with scoped backend equivalence.',
        'Historical read fixtures use the existing injected read-service HTTP fixture, not full application/native assembly.',
        'No real provider/harness, browser, AT, human, performance or default activation is qualified.',
        run['observation_limit'],
    ])
(HERE / 'qualification.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
for p in sorted(out.rglob('*')):
    if p.is_file():
        manifest[p.relative_to(out).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
(HERE / 'curation-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
print(json.dumps({key: report[key] for key in ('status', 'counts', 'layers')}))

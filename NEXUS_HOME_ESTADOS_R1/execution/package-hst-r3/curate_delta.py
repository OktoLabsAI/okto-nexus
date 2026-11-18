"""Compare frozen R3 module payloads with R2 evidence, never its interpreter."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE.parent/'package-hst-r2'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


old = read(BASE/'evidence/payload-manifest.json')
new = read(HERE/'evidence/payload-manifest.json')
changes = {}
for module in old.keys() | new.keys():
    before, after = old.get(module, {}), new.get(module, {})
    changes[module] = dict(added=sorted(after.keys()-before.keys()), removed=sorted(before.keys()-after.keys()),
        changed=sorted(name for name in before.keys() & after.keys() if before[name] != after[name]))
assert not any(changes[name]['added'] or changes[name]['removed'] or changes[name]['changed']
    for name in ('nexus_connector_core', 'okto_nexus_connector'))
assert changes['okto_nexus'] == dict(added=[], removed=[], changed=[
    'okto_nexus/adapters/outbound/sqlite/home.py', 'okto_nexus/adapters/outbound/sqlite/home_operational_facts.py'])
old_pins = read(BASE/'evidence/source-pins-before.json')
new_pins = read(HERE/'evidence/source-pins-before.json')
report = dict(status='PASS_EXACT_EXPECTED_DELTA', baseline_report_sha256=hashlib.sha256((BASE/'qualification.json').read_bytes()).hexdigest(),
    candidate_report_sha256=hashlib.sha256((HERE/'qualification.json').read_bytes()).hexdigest(),
    payload_changes=changes, assets_unchanged=all(old['okto_nexus'][name] == pin
        for name, pin in new['okto_nexus'].items() if '/http/static/' in name),
    schema_payload_unchanged=all(old['okto_nexus'][name] == pin
        for name, pin in new['okto_nexus'].items() if name.endswith('.sql')),
    source_inputs=dict(before=len(old_pins), after=len(new_pins),
        added=sorted(new_pins.keys()-old_pins.keys()), removed=sorted(old_pins.keys()-new_pins.keys()),
        changed=sorted(name for name in old_pins.keys() & new_pins.keys() if old_pins[name] != new_pins[name])),
    intentional_behavior='Committed-contiguous/currentness correction is distinct from batch-performance equivalence; v1 factual status/revision may correct while IDs/shape/targets are preserved by source qualification.',
    old_prefix_reinstalled=False, scope='Module payload bytes, not identical raw wheel ZIP metadata/timestamps')
(HERE/'delta-vs-r2.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
print(json.dumps(report, indent=2))

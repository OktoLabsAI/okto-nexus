"""Scope R5 installed evidence reuse to exact backend bytes and versions."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE.parent / 'package-hst-r5'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


old = read(BASE / 'evidence/payload-manifest.json')
new = read(HERE / 'evidence/payload-manifest.json')
counts = {}
for module in old.keys() | new.keys():
    before = {name: pin for name, pin in old[module].items()
              if module != 'okto_nexus' or '/http/static/' not in name}
    after = {name: pin for name, pin in new[module].items()
             if module != 'okto_nexus' or '/http/static/' not in name}
    assert before == after, ('Backend payload changed', module,
        [name for name in before.keys() | after.keys() if before.get(name) != after.get(name)])
    counts[module] = len(after)
old_static = {name: pin for name, pin in old['okto_nexus'].items() if '/http/static/' in name}
new_static = {name: pin for name, pin in new['okto_nexus'].items() if '/http/static/' in name}
static_delta = dict(added=sorted(new_static.keys() - old_static.keys()),
    removed=sorted(old_static.keys() - new_static.keys()),
    changed=sorted(name for name in old_static.keys() & new_static.keys() if old_static[name] != new_static[name]))
assert all(name.endswith('.js') for name in static_delta['added'] + static_delta['removed'])
assert all(name.endswith(('/index.html', '.js')) for name in static_delta['changed'])
old_pins = read(BASE / 'evidence/source-pins-before.json')
new_pins = read(HERE / 'evidence/source-pins-before.json')
for name in ('pyproject.toml', 'uv.lock'):
    assert old_pins[name] == new_pins[name], name
old_env = read(BASE / 'qualification.json')
new_env = read(HERE / 'qualification.json')
assert old_env['python_version'] == new_env['python_version']
assert old_env['dependencies'] == new_env['dependencies']
baseline = read(BASE / 'installed-qualification.json')
assert baseline['counts']['PASS'] == 251
assert all(baseline['counts'].get(key, 0) == 0 for key in ('FAIL', 'ERROR', 'SKIP', 'NOT_RUN'))
report = dict(
    status='PASS_RUNTIME_BYTE_EQUIVALENCE',
    current_ready=read(HERE / 'READY.json'), baseline_ready=read(BASE / 'READY.json'),
    nonstatic_runtime_files=counts, total_nonstatic_runtime_files=sum(counts.values()),
    static_delta=static_delta,
    packaging_and_lock_equal=['pyproject.toml', 'uv.lock'],
    python_version_equal=True, installed_dependency_versions_equal=True,
    dependency_comparison_limit='Third-party version metadata compared; full byte equality applies to the three Nexus/Core/Connector module payloads.',
    reusable_evidence=dict(path=str(BASE / 'installed-qualification.json'),
        sha256=hashlib.sha256((BASE / 'installed-qualification.json').read_bytes()).hexdigest(),
        executed_on='R5 installed wheel, not R6', counts=baseline['counts'],
        scope='Identical backend Python/SQLite/ASGI Home scopes only; all original fixture and platform limits remain.'),
    pytest_executed_on_r6=False, frontend_browser_qualification_reused=False,
    required_separate_evidence='R6 compiled UI real-browser checks and current Node/build evidence.',
    old_prefix_reinstalled=False, provider_calls=0)
output = HERE / 'runtime-equivalence-vs-r5.json'
assert not output.exists()
output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
print(json.dumps(dict(status=report['status'], files=counts, pytest_r6=False)))

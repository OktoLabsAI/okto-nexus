"""Scope R3 installed evidence reuse to byte-identical runtime payload only."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE.parent/'package-hst-r3'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


old = read(BASE/'evidence/payload-manifest.json')
new = read(HERE/'evidence/payload-manifest.json')
runtime_counts = {}
for module in old.keys() | new.keys():
    before = {name:pin for name,pin in old[module].items() if module!='okto_nexus' or '/http/static/' not in name}
    after = {name:pin for name,pin in new[module].items() if module!='okto_nexus' or '/http/static/' not in name}
    assert before == after, ('Runtime payload drift', module,
        sorted(name for name in before.keys()|after.keys() if before.get(name)!=after.get(name)))
    runtime_counts[module] = len(after)
old_pins = read(BASE/'evidence/source-pins-before.json')
new_pins = read(HERE/'evidence/source-pins-before.json')
for name in ('pyproject.toml','uv.lock'):
    assert old_pins[name] == new_pins[name], name
old_static = {name:pin for name,pin in old['okto_nexus'].items() if '/http/static/' in name}
new_static = {name:pin for name,pin in new['okto_nexus'].items() if '/http/static/' in name}
baseline = read(BASE/'installed-qualification.json')
assert baseline['counts'] == {'PASS':746,'SKIP':8,'FAIL':0,'NOT_RUN':0}
old_environment = read(BASE/'qualification.json')
new_environment = read(HERE/'qualification.json')
assert old_environment['python_version'] == new_environment['python_version']
assert old_environment['dependencies'] == new_environment['dependencies'], 'Review dependency-version drift before reusing installed evidence'
report = dict(status='PASS_RUNTIME_BYTE_EQUIVALENCE',
    current_ready=read(HERE/'READY.json'), baseline_ready=read(BASE/'READY.json'),
    nonstatic_runtime_files=runtime_counts,total_nonstatic_runtime_files=sum(runtime_counts.values()),
    packaging_and_lock_equal=['pyproject.toml','uv.lock'],
    python_version_equal=True,installed_dependency_versions_equal=True,
    dependency_comparison_limit='Version metadata compared; byte equality claim covers the three application/Core/Connector module payloads, not all third-party package files.',
    static_delta=dict(added=sorted(new_static.keys()-old_static.keys()),removed=sorted(old_static.keys()-new_static.keys()),
        changed=sorted(name for name in old_static.keys()&new_static.keys() if old_static[name]!=new_static[name])),
    reusable_evidence=dict(path=str(BASE/'installed-qualification.json'),
        sha256=hashlib.sha256((BASE/'installed-qualification.json').read_bytes()).hexdigest(),
        executed_on='R3 installed wheel, not R4',counts=baseline['counts'],
        scope='Byte-identical Python/Nexus nonstatic/Core/Connector runtime only; synthetic fixture/HTTP/SQLite/CLI layer and original limits preserved.'),
    pytest_executed_on_r4=False,frontend_browser_qualification_reused=False,
    required_separate_evidence='R4 final real-browser validation and Root new frontend Node/build evidence.',
    old_prefix_reinstalled=False,provider_calls=0)
(HERE/'runtime-equivalence-vs-r3.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps(dict(status=report['status'],nonstatic_runtime_files=runtime_counts,
    total_nonstatic_runtime_files=sum(runtime_counts.values()),pytest_r4=False,static_delta=report['static_delta']),indent=2))

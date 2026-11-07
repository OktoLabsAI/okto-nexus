"""Copy closed qualification reports; never rewrite earlier milestone evidence."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import xml.etree.ElementTree as ET

BASE = Path(__file__).resolve().parent
TEMP = BASE.parent
NEXUS = Path(r'D:/Projetos/Techridy/okto_labs_okto_nexus')
CONNECTOR = NEXUS.parent / 'okto-nexus-connector'
DEST = NEXUS / 'plans/agent_ops/evidence/pr03-remote-bootstrap'
DEST.mkdir(exist_ok=False)
copies = {}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def copy(source, relative):
    target = DEST / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    assert source.read_bytes() == target.read_bytes()
    copies[relative] = str(source)


for source in sorted(TEMP.glob('dx1819-*.xml')):
    kind = 'connector' if source.name.startswith('dx1819-connector') else 'operator'
    copy(source, 'source/' + kind + '/' + source.name)
for source in sorted((TEMP / 'dx1819-server-xvlrq8il').iterdir()):
    if source.suffix in ('.xml', '.json'):
        copy(source, 'source/server/' + source.name)
for source in sorted((TEMP / 'dx1819-connector-source-final-y7uqsck6').iterdir()):
    if source.suffix == '.json':
        copy(source, 'source/connector/' + source.name)
for source in sorted(BASE.glob('*.py')):
    copy(source, 'drivers/' + source.name)
copy(BASE / 'connector-nodes.json', 'drivers/connector-nodes.json')
copy(BASE / 'nexus-schema-focal-nodes.json', 'drivers/nexus-schema-focal-nodes.json')
copy(BASE / 'changed-paths.json', 'drivers/changed-paths.json')
for name in ('static-checks.json', 'connector-ruff-initial.json',
             'connector-ruff-baseline-comparison.json', 'test-format-equivalence.json'):
    copy(BASE / name, 'static/' + name)
candidate = BASE / 'candidate-v1'
for name in ('package-proof.json', 'okto_nexus-build.log', 'okto_nexus_connector-build.log', 'venv-create.log', 'wheel-install.log'):
    copy(candidate / name, 'candidate-v1/' + name)
for kind in ('nexus', 'connector', 'nexus-schema-focal'):
    for name in ('installed.xml', 'qualification.json'):
        copy(candidate / ('tests-' + kind) / name, 'candidate-v1/' + kind + '/' + name)
reports = {}
for path in sorted(DEST.rglob('*.xml')):
    data = path.read_bytes()
    assert not re.search(rb'(?:nxs_[0-9a-f]{48}|nxt4_[A-Za-z0-9_-]{24,}|nexus_operator_session=[A-Za-z0-9_-]{32,})', data)
    root = ET.fromstring(data)
    rows = list(root.iter('testcase'))
    reports[path.relative_to(DEST).as_posix()] = dict(
        sha256=sha(data), tests=len(rows), failures=sum(x.find('failure') is not None for x in rows),
        errors=sum(x.find('error') is not None for x in rows), skips=sum(x.find('skipped') is not None for x in rows),
        unique_identities=len({(x.get('classname'), x.get('name')) for x in rows}),
        suites=[dict(s.attrib) for s in root.iter('testsuite')])
installed = {'connector': reports['candidate-v1/connector/installed.xml']}
nexus_runs = ['candidate-v1/nexus/installed.xml', 'candidate-v1/nexus-schema-focal/installed.xml']
latest = {}
observations = 0
for relative in nexus_runs:
    for row in ET.parse(DEST / relative).getroot().iter('testcase'):
        observations += 1
        latest[(row.get('classname'), row.get('name'))] = row
installed['nexus'] = dict(tests=len(latest), unique_identities=len(latest),
    failures=sum(x.find('failure') is not None for x in latest.values()),
    errors=sum(x.find('error') is not None for x in latest.values()),
    skips=sum(x.find('skipped') is not None for x in latest.values()),
    observations=observations, runs=nexus_runs, overlapping_identities=observations-len(latest),
    aggregation='latest result by exact classname and test name; raw attempts retained')
assert all(r['failures'] == r['errors'] == r['skips'] == 0 and r['tests'] == r['unique_identities'] for r in installed.values())
(DEST / 'reports.json').write_text(json.dumps(dict(reports=reports, installed=installed,
    initial_failures_preserved=True, source_reports_overlap=True, copied_from=copies), indent=2), encoding='utf-8')
proof = json.loads((candidate / 'package-proof.json').read_text())
for name, package in proof['packages'].items():
    root = Path(package['repository']) / 'src' / name
    actual = {p.relative_to(root).as_posix(): sha(p.read_bytes()) for p in root.rglob('*')
        if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc', '.pyo')}
    assert actual == package['files'], 'Product changed after wheel qualification: ' + name

# Connector carries its own closed source/installed evidence and package pin.
other = CONNECTOR / 'docs/evidence/remote-bootstrap'
other.mkdir(exist_ok=False)
for relative in copies:
    if relative.startswith(('source/connector/', 'candidate-v1/connector/', 'static/')):
        target = other / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(DEST / relative, target)
(other / 'package-proof.json').write_text(json.dumps(dict(
    connector=proof['packages']['okto_nexus_connector'], core_sha256=proof['core_sha256'],
    nexus_wheel_sha256=proof['packages']['okto_nexus']['wheel_sha256']), indent=2), encoding='utf-8')
(other / 'reports.json').write_text(json.dumps(dict(installed=installed['connector'],
    source={k: v for k, v in reports.items() if k.startswith('source/connector/')},
    source_reports_overlap=True, initial_failures_preserved=True), indent=2), encoding='utf-8')
print(json.dumps(dict(installed=installed, nexus_artifacts=str(DEST), connector_artifacts=str(other)), indent=2))

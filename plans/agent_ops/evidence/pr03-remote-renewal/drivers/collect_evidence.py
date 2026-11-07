"""Retain closed qualification evidence; redact synthetic credentials in copies."""
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

BASE = Path(__file__).parent
TEMP = BASE.parent
NEXUS = Path(r'D:/Projetos/Techridy/okto_labs_okto_nexus')
CONNECTOR = NEXUS.parent / 'okto-nexus-connector'
DEST = NEXUS / 'plans/agent_ops/evidence/pr03-remote-renewal'
DEST.mkdir(exist_ok=False)
records = {}
patterns = {
    'canonical_key': rb'nxs_[A-Za-z0-9_-]{20,}',
    'execution_ticket': rb'nxt4_[A-Za-z0-9_-]{20,}',
    'operator_cookie': rb'(?:nexus_operator_session|okto_operator_session)[=\s\x22\x27:]+[A-Za-z0-9_-]{32,}',
}


def sha(value):
    return hashlib.sha256(value).hexdigest()


def copy(source, relative):
    raw = source.read_bytes()
    public = raw
    counts = {}
    for name, pattern in patterns.items():
        public, count = re.subn(pattern, b'[REDACTED_SYNTHETIC_' + name.upper().encode() + b']', public)
        if count:
            counts[name] = count
    target = DEST / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(public)
    if source.suffix == '.xml':
        ET.fromstring(public)
    records[relative] = dict(source=str(source), source_sha256=sha(raw), public_sha256=sha(public), redactions=counts)


for pattern in ('remote-renewal-operator-*.xml', 'remote-renewal-work-cli-*.xml'):
    for source in sorted(TEMP.glob(pattern)):
        copy(source, 'source/operator/' + source.name)
for source in sorted(TEMP.glob('dx1819-connector-rotation-*.xml')):
    copy(source, 'source/connector/' + source.name)
for source in sorted((TEMP / 'dx1819-connector-rotation-source-qu_ihg15').glob('*.json')):
    copy(source, 'source/connector/' + source.name)
for source in sorted((TEMP / 'remote-renewal-pnqywuv9').glob('*.xml')):
    copy(source, 'source/integrated/' + source.name)
copy(TEMP / 'remote-renewal-pnqywuv9/campaign-summary.json', 'source/integrated/campaign-summary.json')
for source in sorted(BASE.glob('*.py')):
    copy(source, 'drivers/' + source.name)
for name in ('nexus-nodes.json', 'connector-nodes.json', 'changed-paths.json'):
    copy(BASE / name, 'drivers/' + name)
copy(BASE / 'static-checks.json', 'static-checks.json')
candidate = BASE / 'candidate-v2'
for version in ('candidate-v1', 'candidate-v2'):
    for name in ('package-proof.json', 'okto_nexus-build.log', 'okto_nexus_connector-build.log', 'venv-create.log', 'wheel-install.log'):
        copy(BASE / version / name, version + '/' + name)
for kind, directory, version in [('nexus', 'tests-nexus-final', 'candidate-v2'), ('connector', 'tests-connector', 'candidate-v1')]:
    for name in ('installed.xml', 'qualification.json', 'pytest.raw.log'):
        copy(BASE / version / directory / name, version + '/' + kind + '/' + name)
reports = {}
for path in sorted(DEST.rglob('*.xml')):
    tree = ET.parse(path).getroot()
    rows = list(tree.iter('testcase'))
    reports[path.relative_to(DEST).as_posix()] = dict(tests=len(rows),
        failures=sum(row.find('failure') is not None for row in rows),
        errors=sum(row.find('error') is not None for row in rows),
        skips=sum(row.find('skipped') is not None for row in rows),
        unique_identities=len({(row.get('classname'), row.get('name')) for row in rows}),
        public_sha256=sha(path.read_bytes()), suites=[dict(s.attrib) for s in tree.iter('testsuite')])
installed = {'nexus': reports['candidate-v2/nexus/installed.xml'],
    'connector': reports['candidate-v1/connector/installed.xml']}
assert all(r['tests'] == r['unique_identities'] and r['failures'] == r['errors'] == r['skips'] == 0 for r in installed.values())
proof = json.loads((candidate / 'package-proof.json').read_text())
for name, item in proof['packages'].items():
    root = Path(item['repository']) / 'src' / name
    actual = {p.relative_to(root).as_posix(): sha(p.read_bytes()) for p in root.rglob('*')
        if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc', '.pyo')}
    assert actual == item['files'], 'Product changed after qualification: ' + name
summary = dict(reports=reports, installed=installed, copied_from=records,
    source_reports_overlap=True, original_reports_preserved_outside_repository=True,
    redaction_policy='Only synthetic credential literals are redacted in public copies; source/public hashes and counts retained. Raw files are not committed.')
(DEST / 'reports.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
other = CONNECTOR / 'docs/evidence/remote-rotation'
other.mkdir(exist_ok=False)
for relative in records:
    if relative.startswith(('source/connector/', 'candidate-v1/connector/')):
        target = other / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((DEST / relative).read_bytes())
(other / 'package-proof.json').write_text(json.dumps(dict(connector=proof['packages']['okto_nexus_connector'],
    nexus_wheel_sha256=proof['packages']['okto_nexus']['wheel_sha256'], core_sha256=proof['core_sha256']), indent=2))
(other / 'reports.json').write_text(json.dumps(dict(installed=installed['connector'],
    source={key: value for key, value in reports.items() if key.startswith('source/connector/')},
    copied_from={key: value for key, value in records.items() if key.startswith(('source/connector/', 'candidate-v1/connector/'))},
    source_reports_overlap=True), indent=2))
print(json.dumps(dict(installed=installed, redacted_files=sum(bool(r['redactions']) for r in records.values())), indent=2))

"""Retain only named public qualification artifacts; never inspect fixture secrets."""
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
TEMP = ROOT.parent
REPO = Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
OUT = REPO / 'plans/agent_ops/evidence/pr10-correlation'
OUT.mkdir(exist_ok=True)
sha = lambda value: hashlib.sha256(value).hexdigest()
credentials = re.compile(rb'nxobs_[0-9a-f]{64}|nxs_[0-9a-f]{48}')
metadata_path = OUT / 'reports.json'
metadata = (json.loads(metadata_path.read_text(encoding='utf-8')) if metadata_path.exists() else
    dict(schema_version=1, collection_phase='partial_closed_reports', retained_inputs=[], reports=[]))
assert metadata['collection_phase'] == 'partial_closed_reports'


def retain(source, relative):
    assert source.is_file(), source
    assert 'private' not in source.name.lower()
    assert source.suffix.lower() not in ('.db', '.sqlite', '.sqlite3', '.whl', '.key', '.pyc')
    assert not source.name.endswith(('-wal', '-shm'))
    data = source.read_bytes()
    assert not credentials.search(data), ('Credential-shaped data refused', source.name)
    target = OUT / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        assert target.read_bytes() == data, ('Retained artifact is immutable', relative)
    else:
        target.write_bytes(data)
    path = target.relative_to(REPO).as_posix()
    if not any(row['path'] == path for row in metadata['retained_inputs']):
        metadata['retained_inputs'].append(dict(path=path, original_path=str(source),
            bytes=len(data), sha256=sha(data), original_sha256=sha(data),
            exact_original_bytes=True, credential_pattern_matches=0))
    return path


def report(source, relative, scope):
    path = retain(source, relative)
    cases = list(ET.parse(source).getroot().iter('testcase'))
    identities = [(case.get('classname', '').removeprefix('tests.'), case.get('name')) for case in cases]
    counts = {tag: sum(len(case.findall(tag)) for case in cases) for tag in ('failure', 'error', 'skipped')}
    if not any(row['path'] == path for row in metadata['reports']):
        metadata['reports'].append(dict(path=path, scope=scope, cases=len(cases),
            unique_identities=len(set(identities)),
            passed=sum(not any(case.find(tag) is not None for tag in ('failure', 'error', 'skipped')) for case in cases),
            **counts, sha256=sha(source.read_bytes())))


names = '''pr10b-correlation-domain-final.xml
pr10b-correlation-projection-initial.xml
pr10b-correlation-projection-retest.xml
pr10b-correlation-read-regressions-initial.xml
pr10b-correlation-reads-initial.xml
pr10b-correlation-reads-query-trace.xml
pr10b-correlation-reads-retest.xml
pr10b-correlation-view-strict-scope.xml
pr10b-http-regression-initial.xml
pr10b-process-birth-source-initial.xml
pr10b-storage-settings-initial.xml
pr10b-upgrade-regressions.xml
obs12-correlation-http-final-boundaries.xml
obs12-correlation-http-initial.xml
obs12-correlation-http-second.xml
obs12-correlation-postfix-boundaries.xml
obs12-correlation-proof-initial.xml
pr10-observation-correlation-projection-time-initial.xml
pr10-observation-correlation-view-initial.xml'''.splitlines()
for name in names:
    report(TEMP / name, 'source/' + name, 'source_history_not_an_additive_acceptance_total')
report(TEMP / 'obs12-frontend-final.xml', 'frontend/final.xml', 'frontend_final')
retain(TEMP / 'obs12-frontend-build-report.json', 'frontend/build-report.json')
diagnostic_source = TEMP / 'dx0714-nexus-diagnostics-4_rod_up'
for name in ('prototype-initial.xml', 'source-initial.xml', 'source-metadata-final.xml', 'source-final.xml'):
    report(diagnostic_source / name, 'diagnostics/source/' + name, 'diagnostic_source_history_overlapping')
retain(diagnostic_source / 'source-qualification.json', 'diagnostics/source/qualification.json')
for name in ('prepare_drivers.py', 'build_release.py', 'qualify_installed.py'):
    retain(ROOT / name, 'drivers/' + name)
retain(ROOT / 'changed-python-ruff.json', 'source/changed-python-ruff.json')
retain(ROOT / 'shared-contract-comparison.json', 'diagnostics/shared-contract-comparison.json')

candidate = ROOT / 'candidate-v1'
proof = json.loads((candidate / 'package-proof.json').read_text(encoding='utf-8'))
for name, item in proof['files'].items():
    assert sha((REPO / 'src/okto_nexus' / name).read_bytes()) == item['source_sha256'], name
    assert sha((Path(proof['installed_package']) / name).read_bytes()) == item['installed_sha256'], name
retain(candidate / 'package-proof.json', 'installed/package-proof.json')
for name in ('wheel-build.log', 'venv-create.log', 'wheel-install.log'):
    retain(candidate / name, 'installed/' + name)
for suite in ('correlation', 'regression', 'diagnostics'):
    directory = candidate / ('tests-' + suite)
    closed = directory / 'installed-qualification.json'
    if not closed.exists():
        continue
    qualification = json.loads(closed.read_text(encoding='utf-8'))
    assert qualification['xml_sha256'] == sha((directory / 'installed.xml').read_bytes())
    report(directory / 'installed.xml', 'installed/' + suite + '/installed.xml', 'installed_' + suite)
    retain(closed, 'installed/' + suite + '/qualification.json')

metadata.update(wheel_sha256=proof['wheel_sha256'], core_wheel_sha256=proof['core_wheel_sha256'],
    package_counts=proof['counts'],
    plan_sha256='20d0fafdedc793b97a277f5d41355d7d597ff724a77687394215eea3113ba996',
    limits=[
        'Only explicit allowlisted reports/drivers are retained. Private credential registries, databases and wheels are excluded.',
        'Historical source reports include failed candidates and overlapping executions; no source sum is an acceptance total.',
        'Frontend first loader failure was corrected before the retained final XML; its terminal output has no standalone retained artifact.',
        'Installed correlation/regression, actual browser projection and measured load must close before OBS12 is verified.',
        'Synthetic native data do not qualify a real process birth, provider, native user service, M1/M2 or full R3.',
    ])
metadata_path.write_text(json.dumps(metadata, indent=2) + '\n', encoding='utf-8')
print(json.dumps(dict(phase=metadata['collection_phase'], artifacts=len(metadata['retained_inputs']),
    reports=len(metadata['reports']), closed_installed=[r['scope'] for r in metadata['reports']
    if r['scope'].startswith('installed_')]), indent=2))

import difflib
import hashlib
import json
from pathlib import Path
import shutil

HERE = Path(__file__).parent
OLD = HERE.parent
BASE = Path('D:/Projetos/Techridy/okto_labs_okto_nexus/plans/agent_ops/evidence/r3-m1-controller/preparation')
old_manifest = json.loads((OLD / 'public/artifact-manifest.json').read_text())
assert hashlib.sha256((OLD / 'public/artifact-manifest.json').read_bytes()).hexdigest() == '49a3966061aa6e0e19f630786d970078173b0a9f7f0c873b0b2980341a7a4849'
ancestry = json.loads((HERE / 'ancestry.json').read_text())
for name, value in ancestry['historical_files'].items():
    assert hashlib.sha256((BASE / name).read_bytes()).hexdigest() == value
freeze = {name: hashlib.sha256((HERE / name).read_bytes()).hexdigest() for name in (
    'controller.py', 'token_collector.py', 'test_v8.py', 'setup_journal.py', 'canonical_fixture.py', 'run_tests.py')}
(HERE / 'freeze.json').write_text(json.dumps(freeze, indent=2), encoding='utf-8')
for label, before, names in [('candidate', BASE, ('controller.py', 'token_collector.py')),
                              ('revision-2', OLD, ('controller.py', 'test_v8.py'))]:
    delta = ''.join(''.join(difflib.unified_diff((before / name).read_text().splitlines(True),
        (HERE / name).read_text().splitlines(True), fromfile=str(before / name), tofile=str(HERE / name))) for name in names)
    (HERE / (label + '.diff')).write_text(delta, encoding='utf-8')
summary = {'status': 'PREPARATION_ONLY_NOT_AUTHORIZED', 'revision': 2,
    'tests': 23, 'failures': 0, 'errors': 0, 'skipped': 0, 'seconds': 6.55,
    'previous_tests': 19, 'previous_artifacts_preserved': True,
    'guard': 'Existing session requires exactly one known non-retired controller stream with matching binding scope before reservation.',
    'negative_cases': ['foreign_session', 'scope_mismatch', 'ambiguous_epochs', 'retired_stream'],
    'negative_oracles': ['zero_dispatch', 'zero_reservation', 'checkpoint_unchanged'],
    'positive_oracle': 'First work new_session=True; known own continuation=False.',
    'historical_sources_unchanged': True, 'campaign_effects': 0}
(HERE / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
OUT = HERE / 'public'
OUT.mkdir(exist_ok=False)
def copy(source, name):
    target = OUT / name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
for name, value in old_manifest['files'].items():
    source = OLD / 'public' / name
    assert hashlib.sha256(source.read_bytes()).hexdigest() == value['sha256']
    copy(source, 'history-v1/' + name)
copy(OLD / 'public/artifact-manifest.json', 'history-v1/artifact-manifest.json')
for name in list(freeze) + ['freeze.json', 'ancestry.json', 'previous.json', 'README.md', 'summary.json',
                            'candidate.diff', 'revision-2.diff', 'curate.py']:
    copy(HERE / name, name)
for name in ('tests.xml', 'stdout.log', 'result.json', 'imports.json', 'inputs-before.json'):
    copy(HERE / 'final' / name, 'final/' + name)
files = {str(path.relative_to(OUT)).replace('\\', '/'): {
    'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'bytes': path.stat().st_size}
    for path in sorted(OUT.rglob('*')) if path.is_file()}
(OUT / 'artifact-manifest.json').write_text(json.dumps({'version': 2, 'files': files}, indent=2), encoding='utf-8')
print(json.dumps({'path': str(OUT), 'payloads': len(files),
    'manifest_sha256': hashlib.sha256((OUT / 'artifact-manifest.json').read_bytes()).hexdigest(),
    'controller_sha256': freeze['controller.py'], 'test_sha256': freeze['test_v8.py']}))

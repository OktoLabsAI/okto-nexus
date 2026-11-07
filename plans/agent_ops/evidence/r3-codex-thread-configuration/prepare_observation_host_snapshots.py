from pathlib import Path
import hashlib
import json
import shutil

root = Path('C:/Users/jpamb/AppData/Local/Temp/m1-observation-hosts-ai03jk1l')
repo = Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
nexus = root / 'nexus-source'
nexus.mkdir(exist_ok=False)
for name in ('src', 'tests', 'tools', 'vendor'):
    shutil.copytree(repo / name, nexus / name,
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '.pytest_cache'))
for name in ('pyproject.toml', 'README.md', 'LICENSE'):
    shutil.copy2(repo / name, nexus / name)
core = Path('C:/Users/jpamb/AppData/Local/Temp/core-dx43-observation-du1arc40/wheel/okto_nexus_connector_core-0.0.14-py3-none-any.whl')
digest = hashlib.sha256(core.read_bytes()).hexdigest()
assert digest == '609e0fbbb20855c6b788d2523b0aeb6cdfbf4b3f5c9792c9e4a080284729c9dd'
shutil.copy2(core, nexus / 'vendor/wheels' / core.name)
manifest_path = nexus / 'vendor/ci/manifest.json'
manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
record, = [item for item in manifest['artifacts'] if item['path'].endswith('/' + core.name)]
record['sha256'] = digest
manifest_path.write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8')
connector_repo = Path('D:/Projetos/Techridy/okto-nexus-connector')
connector = root / 'connector-tests'
shutil.copytree(connector_repo / 'tests', connector / 'tests',
                ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '.pytest_cache'))
(connector / 'pytest.ini').write_text('[pytest]\nasyncio_mode=auto\nasyncio_default_fixture_loop_scope=function\n')
test = 'tests/execution_r4/test_canonical_event_views.py'
remote_test = 'tests/unit/test_r4_events.py'
assert (nexus / test).read_bytes() == (repo / test).read_bytes()
assert (connector / remote_test).read_bytes() == (connector_repo / remote_test).read_bytes()
proof = dict(nexus=str(nexus), connector=str(connector), core_sha256=digest,
             nexus_test_sha256=hashlib.sha256((nexus / test).read_bytes()).hexdigest(),
             connector_test_sha256=hashlib.sha256((connector / remote_test).read_bytes()).hexdigest(),
             scope='Frozen installed consumer tests; synthetic native events, no provider or OS service campaign.')
(root / 'snapshot.json').write_text(json.dumps(proof, indent=2)+'\n', encoding='utf-8')
print(json.dumps(proof))

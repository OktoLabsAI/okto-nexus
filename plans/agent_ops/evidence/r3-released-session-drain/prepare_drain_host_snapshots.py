from pathlib import Path
import hashlib, json, shutil

root = Path('C:/Users/jpamb/AppData/Local/Temp/m1-drain-hosts-n7pm3omg')
repo = Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
nexus = root / 'nexus-source'
nexus.mkdir(exist_ok=False)
for name in ('src', 'tests', 'tools', 'vendor'):
    shutil.copytree(repo / name, nexus / name, ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '.pytest_cache'))
for name in ('pyproject.toml', 'README.md', 'LICENSE'):
    shutil.copy2(repo / name, nexus / name)
core = Path('C:/Users/jpamb/AppData/Local/Temp/core-eviction-drain-ru1nczz0/candidate/wheels/okto_nexus_connector_core-0.0.14-py3-none-any.whl')
digest = hashlib.sha256(core.read_bytes()).hexdigest()
assert digest == '4e677a205f5a486ef7134b8411983420c1c763c3dda274128a9c623ad1b1775d'
shutil.copy2(core, nexus / 'vendor/wheels' / core.name)
manifest_path = nexus / 'vendor/ci/manifest.json'
manifest = json.loads(manifest_path.read_text())
record, = [item for item in manifest['artifacts'] if item['path'].endswith('/' + core.name)]
record['sha256'] = digest
manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
connector = root / 'connector-tests'
shutil.copytree(Path('D:/Projetos/Techridy/okto-nexus-connector/tests'), connector / 'tests', ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '.pytest_cache'))
(connector / 'pytest.ini').write_text('[pytest]\nasyncio_mode=auto\nasyncio_default_fixture_loop_scope=function\n')
test = 'tests/execution_r4/test_service_cooperative_drain.py'
assert (nexus / test).read_bytes() == (repo / test).read_bytes()
(root / 'snapshot.json').write_text(json.dumps(dict(nexus=str(nexus), connector=str(connector), core_sha256=digest, test_sha256=hashlib.sha256((nexus / test).read_bytes()).hexdigest(), scope='Fresh frozen installed host regression inputs; repository pins not changed until validation.'), indent=2) + '\n')
print(json.dumps(dict(nexus=str(nexus), connector=str(connector), core_sha256=digest)))

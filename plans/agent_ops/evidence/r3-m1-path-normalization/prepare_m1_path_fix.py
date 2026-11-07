from pathlib import Path
import hashlib, json, os, shutil, subprocess, sys, tempfile, venv, zipfile

repo = Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix='m1-path-fix-'))
source = root / 'source'
if not source.exists():
    source.mkdir()
    for name in ('src', 'tests', 'tools', 'vendor'):
        shutil.copytree(repo / name, source / name, ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '.pytest_cache'))
    for name in ('pyproject.toml', 'README.md', 'LICENSE'):
        if (repo / name).exists():
            shutil.copy2(repo / name, source / name)
for name in ('src/okto_nexus/application/terminal_connection.py', 'tests/execution_r4/test_terminal_connect.py'):
    assert (repo / name).read_bytes() == (source / name).read_bytes()
(root / 'preparation.json').write_text(json.dumps({'root': str(root), 'source': str(source), 'state': 'BUILDING'}, indent=2))
print(json.dumps({'root': str(root), 'state': 'BUILDING'}), flush=True)
env = {k: v for k, v in os.environ.items() if k.upper() in {'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATH', 'PATHEXT', 'TEMP', 'TMP'}}
env.update(PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1')
with (root / 'build-uv.txt').open('wb') as log:
    subprocess.run(['rtk', 'proxy', 'uv', 'build', '--wheel', '--offline', '--out-dir', str(root / 'wheels'), str(source)], cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
target = root / 'venv'
venv.EnvBuilder(with_pip=False).create(target)
dependency_env = Path('C:/Users/jpamb/AppData/Local/Temp/r3-cooperative-drain-09ucmgsr/venv')
shutil.copytree(dependency_env / 'Lib/site-packages', target / 'Lib/site-packages', dirs_exist_ok=True, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
python = target / 'Scripts/python.exe'
wheel = next((root / 'wheels').glob('*.whl'))
with (root / 'install.txt').open('wb') as log:
    subprocess.run([str(python), '-I', '-m', 'pip', 'install', '--no-index', '--no-deps', '--force-reinstall', str(wheel)], cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
historical = Path('C:/Users/jpamb/AppData/Local/Temp/r3-campaign-refresh-0ssbo8pb/native/wheels')
proof = {}
for artifact, module in [(wheel, 'okto_nexus'), (next(historical.glob('okto_nexus_connector-*.whl')), 'okto_nexus_connector'), (next(historical.glob('okto_nexus_connector_core-*.whl')), 'nexus_connector_core')]:
    with zipfile.ZipFile(artifact) as archive:
        names = [n for n in archive.namelist() if n.startswith(module + '/') and not n.endswith('/')]
        for name in names:
            assert archive.read(name) == (target / 'Lib/site-packages' / name).read_bytes(), name
        proof[module] = dict(wheel=str(artifact), sha256=hashlib.sha256(artifact.read_bytes()).hexdigest(), files=len(names))
old = next(historical.glob('okto_nexus-*.whl'))
with zipfile.ZipFile(old) as original, zipfile.ZipFile(wheel) as fixed:
    names = [n for n in original.namelist() if n.startswith('okto_nexus/') and not n.endswith('/')]
    assert set(names) == {n for n in fixed.namelist() if n.startswith('okto_nexus/') and not n.endswith('/')}
    changed = [n for n in names if original.read(n) != fixed.read(n)]
    assert changed == ['okto_nexus/application/terminal_connection.py'], changed
proof['changed_product_payloads'] = changed
proof['dependency_source'] = str(dependency_env)
proof['method'] = 'Fresh venv; copied disposable qualified dependencies; new Nexus wheel installed offline without editable paths.'
proof['terminal_connection_sha256'] = hashlib.sha256((target / 'Lib/site-packages/okto_nexus/application/terminal_connection.py').read_bytes()).hexdigest()
(root / 'package-proof.json').write_text(json.dumps(proof, indent=2) + '\n')
(root / 'preparation.json').write_text(json.dumps(dict(root=str(root), source=str(source), python=str(python), wheel=str(wheel), state='PREPARED_FOR_QUALIFICATION'), indent=2) + '\n')
print(json.dumps(dict(root=str(root), python=str(python), state='PREPARED_FOR_QUALIFICATION', nexus=proof['okto_nexus'], terminal_connection_sha256=proof['terminal_connection_sha256'])), flush=True)

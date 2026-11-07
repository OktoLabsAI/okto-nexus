"""Derive the PR09 harness from the retained PR08 harness; no build or launch."""
import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OLD = Path('C:/Users/jpamb/AppData/Local/Temp/pr08-installed-wy268uaa')
files = ['build_release.py', 'qualify_installed.py', 'verify_release.py',
         'server_entry.py', 'start_server.py', 'stop_server.py']
manifest = {'revision': 1, 'previous_harness': str(OLD), 'scripts': {}}


def change(source, old, new):
    if old not in source:
        raise RuntimeError('Harness template changed')
    return source.replace(old, new)


for name in files:
    original = (OLD / name).read_bytes()
    source = original.decode('utf-8')
    source = source.replace('PR08', 'PR09').replace('pr08-', 'pr09-')
    if name in ('build_release.py', 'verify_release.py'):
        source = change(source,
            "return (name.endswith('.py') or name.startswith('migrations/') or\n            name.startswith('adapters/inbound/http/static/')) and '__pycache__' not in name",
            "return '__pycache__' not in Path(name).parts and not name.endswith(('.pyc', '.pyo'))")
    if name == 'build_release.py':
        source = change(source, 'ROOT = Path(__file__).resolve().parent',
            "ROOT = Path(__file__).resolve().parent / 'qualified'\nROOT.mkdir(exist_ok=False)")
        source = change(source, "[sys.executable, '-I', '-m', 'build'", "[sys.executable, '-m', 'build'")
        source = change(source, "'pip', 'install', '--no-deps', '--no-index'",
            "'pip', '--isolated', 'install', '--ignore-installed', '--no-deps', '--no-index'")
        source = change(source, "before = inventory(PACKAGE)",
            "before = inventory(PACKAGE)\ncore_digest = sha(CORE.read_bytes())\nmetadata_digest = sha((REPO / 'pyproject.toml').read_bytes())")
        source = change(source, "run([sys.executable, '-m', 'build'",
            "assert inventory(staging / 'src/okto_nexus') == before, 'Detached copy differs.'\nrun([sys.executable, '-m', 'build'")
        source = change(source, "assert before == after,",
            "assert sha(CORE.read_bytes()) == core_digest\nassert sha((REPO / 'pyproject.toml').read_bytes()) == metadata_digest\nassert before == after,")
        source = change(source, "'revision': 1, 'source_root': str(REPO),",
            "'revision': 2, 'inventory': 'all package files except Python caches',\n    'pyproject_sha256': metadata_digest, 'source_root': str(REPO),")
    if name == 'qualify_installed.py':
        source = change(source, "os.chdir(ROOT)",
            "home = ROOT / 'test-home'\nhome.mkdir()\nfor key in ('HOME', 'USERPROFILE'):\n    os.environ[key] = str(home)\nos.environ['APPDATA'] = str(home / 'appdata')\nos.environ['LOCALAPPDATA'] = str(home / 'localappdata')\nos.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD'] = '1'\nos.chdir(ROOT)\n# Shared dependencies only; Nexus and Core remain pinned to the local wheel.\nif len(sys.argv) > 2:\n    sys.path.append(str(Path(sys.argv[2]).resolve()))")
        start = source.index("names = [")
        end = source.index("copied = {}", start)
        source = source[:start] + "names = ['conftest.py', 'fake_clock.py', 'test_import_boundary.py',\n         'test_herdr_observer.py', 'test_observation_client.py',\n         'test_herdr_observations.py', 'test_herdr_windows_identity.py',\n         'test_herdr_transport.py', 'test_observation_journal.py', 'test_observe_cli.py']\n" + source[end:]
        source = change(source, "config = ROOT / 'pytest.ini'",
            "docs = ROOT / 'docs'\ndocs.mkdir()\nexample = REPO / 'docs/observation-client-example.py'\nshutil.copy2(example, docs / example.name)\ncopied['docs/' + example.name] = {'source': str(example), 'copy': str(docs / example.name),\n    'sha256': hashlib.sha256(example.read_bytes()).hexdigest()}\nconfig = ROOT / 'pytest.ini'")
        start = source.index('nodes = [')
        end = source.index('import pytest', start)
        source = source[:start] + "nodes = [name for name in names if name.startswith('test_')]\n" + source[end:]
        source = change(source, "class Guard:\n", "class Guard:\n    def pytest_runtest_setup(self, item):\n        guard()\n\n")
        source = change(source, "'cwd': str(Path.cwd()), 'pytest_config': str(config)",
            "'cwd': str(Path.cwd()), 'isolated_home': str(home), 'pytest_config': str(config)")
    if name == 'server_entry.py':
        source = change(source, "'--feature-harness-integrations', 'false']",
            "'--feature-harness-integrations', 'false', '--feature-memory', 'false', '--metrics-mode', 'disabled']")
        source = change(source, "'observation_feature_at_start': 'default false, not pinned',",
            "'observation_feature_at_start': 'default false, not pinned',\n    'embedding_mode': 'off', 'metrics_mode': 'disabled', 'feature_memory': False,")
    if name == 'start_server.py':
        source = change(source, 'import site\n', '')
        source = change(source, 'site.getusersitepackages()', 'sys.argv[2]')
        source = change(source, 'from urllib.request import urlopen',
            "from urllib.request import ProxyHandler, build_opener\nurlopen = build_opener(ProxyHandler({})).open")
        source = change(source, "print(json.dumps(metadata, indent=2))",
            "with urlopen(metadata['url'] + '/api/v1/service', timeout=2) as response:\n    service = json.load(response)['data']\n(ROOT / 'server-owner.json').write_text(json.dumps({'server_pid': service['pid'],\n    'generation': service['generation'], 'instance_id': service['instance_id']}, indent=2), encoding='utf-8')\nprint(json.dumps(metadata, indent=2))")
    if name == 'stop_server.py':
        source = change(source, "timeout=40,", "timeout=40, trust_env=False,")
    ast.parse(source, filename=name)
    target = ROOT / name
    target.write_text(source, encoding='utf-8')
    manifest['scripts'][name] = {'template_sha256': hashlib.sha256(original).hexdigest(),
        'prepared_sha256': hashlib.sha256(target.read_bytes()).hexdigest()}
(ROOT / 'preparation.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
print(json.dumps({'prepared': str(ROOT), 'scripts': len(files), 'build_started': False}))

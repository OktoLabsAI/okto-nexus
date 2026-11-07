"""Build an isolated test-only mirror; never copy application source into it."""
from pathlib import Path
import hashlib
import importlib.util
import json
import shutil

root = Path(__file__).resolve().parent
source = Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
target = root / 'project'
target.mkdir()
spec = importlib.util.spec_from_file_location('retained_ci_runner', source / 'tools/ci_installed.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
before = module.input_hashes()
(root / 'original-checkout-before.json').write_text(json.dumps(before, indent=2) + '\n', encoding='utf-8')
for folder in ('tests', 'plans/r4_execution', 'plans/contratos'):
    shutil.copytree(source / folder, target / folder,
                    ignore=shutil.ignore_patterns('__pycache__', '.pytest_cache'))
files = ['pyproject.toml', 'uv.lock', 'README.md', 'tools/ci_installed.py',
         'tools/build_validation_artifacts.py', '.github/workflows/ci.yml', 'vendor/ci/manifest.json']
vendor = json.loads((source / 'vendor/ci/manifest.json').read_text(encoding='utf-8'))
files.extend(item['path'] for item in vendor['artifacts'])
for name in files:
    dest = target / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source / name, dest)
assert not (target / 'src').exists()
assert (source / 'tools/ci_installed.py').read_bytes() == (target / 'tools/ci_installed.py').read_bytes()
specification = json.loads(Path('C:/Users/jpamb/AppData/Local/Temp/r3-rg04-installed-9h8px6xo/selection.json').read_text(encoding='utf-8'))
specification.update(root=str(root), repo=str(target), expected_identities=1,
                     tests=['tests/execution_r4/test_one_shot_remote.py::test_remote_connector_queues_disposes_and_opens_fresh_session'])
(root / 'selection.json').write_text(json.dumps(specification, indent=2) + '\n', encoding='utf-8')
for name in ('run.py', 'curate.py', 'coverage-map.json'):
    shutil.copy2(Path('C:/Users/jpamb/AppData/Local/Temp/r3-rg04-installed-9h8px6xo') / name, root / name)
print(json.dumps({'root': str(root), 'original_input_count': len(before),
                  'runner_sha256': hashlib.sha256((target / 'tools/ci_installed.py').read_bytes()).hexdigest(),
                  'application_source_copied': False}))

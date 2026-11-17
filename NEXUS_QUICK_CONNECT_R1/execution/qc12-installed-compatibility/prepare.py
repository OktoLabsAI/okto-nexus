"""Prepare fixtures and runner only; pytest execution requires package READY."""
import ast
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
root = Path(tempfile.mkdtemp(prefix='nexus-qc12-installed-')).resolve()
(HERE / 'allocation.json').write_text(json.dumps(dict(root=str(root)), indent=2), encoding='utf-8')
index = {}
for directory in (REPO / 'tests/quick_connect', REPO / 'tests/execution_r4', REPO / 'tests'):
    for path in directory.glob('*.py'):
        index.setdefault(path.stem, path)
queue = list((REPO / 'tests/quick_connect').glob('test_*.py'))
queue.extend(index[name] for name in ('test_connection_catalog', 'test_terminal_multi_harness'))
queue.extend((REPO / 'tests/conftest.py', REPO / 'tests/execution_r4/conftest.py'))
selected = set()
while queue:
    path = queue.pop()
    if path in selected:
        continue
    selected.add(path)
    for node in ast.walk(ast.parse(path.read_text(encoding='utf-8-sig'))):
        names = [v.name.split('.')[0] for v in node.names] if isinstance(node, ast.Import) else (
            [node.module.split('.')[0]] if isinstance(node, ast.ImportFrom) and node.module else [])
        queue.extend(index[name] for name in names if name in index and index[name] not in selected)
selected.update((REPO / 'tests/legacy_native_fixture').rglob('*.py'))
selected.update((REPO / 'plans/contratos').glob('*.json'))
pins = {}
for path in selected:
    relative = path.relative_to(REPO)
    pins[relative.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    target = root / 'after' / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(path, target)
for path in (REPO / 'src').rglob('*'):
    if path.is_file() and '__pycache__' not in path.parts:
        pins[path.relative_to(REPO).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
assert not (root / 'after/src').exists()
(root / 'source-pins.json').write_text(json.dumps(pins, indent=2), encoding='utf-8')
(root / 'pytest.ini').write_text('[pytest]\nasyncio_mode=auto\nasyncio_default_fixture_loop_scope=function\n'
    'pythonpath=after/tests after/tests/execution_r4 after/tests/quick_connect\n', encoding='utf-8')
runner = (HERE.parent / 'qc09-review/run_derivative.py').read_text(encoding='utf-8')
runner = runner.replace("HERE/'derivative-allocation.json'", "HERE/'allocation.json'")
runner = runner.replace("HERE.parent/'qc08-package/allocation.json'", "HERE.parent/'qc11-package/allocation.json'")
runner = runner.replace("HERE.parent/'qc08-package/package.py'", "HERE.parent/'qc08-package/package.py'")
start = runner.index("nodes=[('mutable-feature'")
end = runner.index('\nfor label,node in nodes:', start)
nodes = [(path.stem, 'tests/quick_connect/' + path.name)
    for path in sorted((REPO / 'tests/quick_connect').glob('test_*.py'))]
nodes.extend([
    ('legacy-canonical-shortcut', 'tests/execution_r4/test_connection_catalog.py::test_cli_existing_canonical_without_profile_creates_only_shortcut'),
    ('legacy-single-harness', 'tests/execution_r4/test_terminal_multi_harness.py::test_single_observed_harness_needs_no_profile_and_existing_connection_offers_all_intents'),
    ('legacy-two-harnesses', 'tests/execution_r4/test_terminal_multi_harness.py::test_two_distinct_harnesses_share_project_keep_custom_a_and_recover_b_finish')])
runner = runner[:start] + 'nodes=' + repr(nodes) + runner[end:]
runner = runner.replace("env['PATH']=str(out/'empty-path')", "env['PATH']=str(Path(r'C:/Program Files/Git/cmd'))\n    env.update(GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_SYSTEM=os.devnull,GIT_CONFIG_GLOBAL=os.devnull,GIT_TERMINAL_PROMPT='0')")
runner = runner.replace('deadline_seconds=60', 'deadline_seconds=180').replace('deadline=time.monotonic()+60', 'deadline=time.monotonic()+180')
runner = runner.replace('before=payload()', '''ready=HERE/'package-ready.json'
assert ready.exists(), 'Wait for explicit package-owner READY, not just an installed folder'
ready_value=json.loads(ready.read_text())
assert ready_value['ready'] is True and ready_value['wheel_sha256']==hashlib.sha256((package/'artifacts/okto_nexus-0.3.6-py3-none-any.whl').read_bytes()).hexdigest()
before=payload()''')
(HERE / 'run.py').write_text(runner, encoding='utf-8')
report = dict(root=str(root), status='PREPARED_WAITING_PACKAGE_READY', copied_files=len(selected),
    source_pins=len(pins), cuts=len(nodes), nodes=nodes, pytest_started=False,
    fixture_src_present=False, git_path=r'C:/Program Files/Git/cmd',
    limitations=['PTY-specific tests require real input and will honestly skip in this non-PTY automated cut.',
        'This run checks copied test fixtures, with installed application imports only; no source child APP path is inserted.',
        'Git fixtures operate only on temporary repositories with global/system configuration disabled; no network or provider.'])
(HERE / 'prepared.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(dict(root=str(root), copied_files=len(selected), cuts=len(nodes), pytest_started=False)))

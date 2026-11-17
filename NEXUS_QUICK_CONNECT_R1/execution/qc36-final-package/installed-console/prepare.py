"""Bind the two already-qualified console controllers to the frozen i4 package.

Preparation copies fixture tests and scripts only. It never opens a console or
starts pytest; run.py is a separately authorized action after the Git phase.
"""
import ast
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

HERE = Path(__file__).resolve().parent
EXEC = HERE.parents[1]
REPO = HERE.parents[3]
PACKAGE = Path(json.loads((HERE.parent/'allocation.json').read_text())['root']).resolve()
assert (HERE.parent/'READY.json').is_file()
expected_wheel = 'd2c322168d56e87bde22cfe262d5d2fbc9a5737b0572144774894624d561cf88'
assert hashlib.sha256((PACKAGE/'artifacts/okto_nexus-0.3.6-py3-none-any.whl').read_bytes()).hexdigest() == expected_wheel
original_test = REPO/'tests/quick_connect/test_quick_connect_pty.py'
original_sha = hashlib.sha256(original_test.read_bytes()).hexdigest()
assert original_sha == 'de71181344a41eddbc58b08bd875de0dd561f0d1b7ecc72e62abe293e36f35c3'
old = EXEC/'qc22-owned-console-interrupt'
tree = ast.parse((old/'prepare.py').read_text())
plugin = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
              and any(isinstance(t, ast.Name) and t.id == 'plugin' for t in n.targets))
records = []
for label, scripts, runner_path in [
    ('ctrl-c', old, old/'run.py'),
    ('resize', EXEC/'qc37-owned-console-resize/counterpart', EXEC/'qc37-owned-console-resize/run_counterpart.py')]:
    target = HERE/label
    target.mkdir(exist_ok=False)
    root = Path(tempfile.mkdtemp(prefix='nexus-qc36-console-'+label+'-')).resolve()
    shutil.copytree(REPO/'tests', root/'fixtures/tests', ignore=shutil.ignore_patterns('__pycache__','*.pyc','*.pyo'))
    assert (root/'fixtures/tests/quick_connect/test_quick_connect_pty.py').read_bytes() == original_test.read_bytes()
    for name in ('child.py','controller.py','win.py'):
        shutil.copyfile(scripts/name, root/name)
        shutil.copyfile(scripts/name, target/name)
        assert (root/name).read_bytes() == (scripts/name).read_bytes()
    for name in ('cwd','empty-path'):
        (root/name).mkdir()
    (root/'pytest.ini').write_text('[pytest]\nasyncio_mode=auto\nasyncio_default_fixture_loop_scope=function\n'
        'pythonpath=fixtures/tests fixtures/tests/execution_r4 fixtures/tests/quick_connect\n')
    (root/'fixtures/conftest.py').write_text(plugin,encoding='utf-8')
    pins = {p.relative_to(REPO).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
            for folder in ('src','tests') for p in (REPO/folder).rglob('*') if p.is_file()
            and '__pycache__' not in p.parts and p.suffix not in ('.pyc','.pyo')}
    (root/'source-pins.json').write_text(json.dumps(pins,indent=2))
    (target/'allocation.json').write_text(json.dumps(dict(root=str(root)),indent=2))
    (target/'mechanism.json').write_text(json.dumps(dict(original_test_sha256=original_sha,
        source_candidate='9bc4034663ca63cfee43790b4bc03c38f8bdebcc',wheel_sha256=expected_wheel,
        control_scripts_unchanged=True,controller_source=str(scripts),node='Ctrl-C130' if label=='ctrl-c' else 'confirm/resize/resume'),indent=2))
    runner = runner_path.read_text()
    runner = runner.replace('REPO = HERE.parents[2]', 'REPO = HERE.parents[4]')
    runner = runner.replace("sys.path.insert(0, str(HERE.parent / 'qc22-owned-console-interrupt'))", "sys.path.insert(0, str(HERE))")
    runner = runner.replace("HERE / 'counterpart-allocation.json'", "HERE / 'allocation.json'")
    runner = runner.replace("HERE.parent / 'qc11-package/allocation.json'", "HERE.parents[1] / 'allocation.json'")
    runner = runner.replace("HERE.parent / 'qc08-package/package.py'", "REPO / 'NEXUS_QUICK_CONNECT_R1/execution/qc08-package/package.py'")
    runner = runner.replace('assert len(before) == 1027','assert len(before) == 1028')
    runner = runner.replace('payload_files=1027','payload_files=1028')
    needle = '        assert any(same_image(owner.image, image) for image in allowed_images)\n        known[pid] = (owner, expected)'
    assert needle in runner
    runner = runner.replace(needle, '''        if owner.birth < known[parent][0].birth:
            observed.append(dict(pid=pid,parent_pid=parent,birth_filetime=owner.birth,parent_birth=known[parent][0].birth,authorization='rejected older non-owned PID; no signal/permit'))
            owner.close()
            continue
        assert any(same_image(owner.image, image) for image in allowed_images)
        known[pid] = (owner, expected)''')
    runner = runner.replace("assert os.name == 'nt' and not (ROOT / 'result.json').exists()", "assert os.name == 'nt' and not (ROOT / 'result.json').exists()\nassert hashlib.sha256((PACKAGE / 'artifacts/okto_nexus-0.3.6-py3-none-any.whl').read_bytes()).hexdigest() == '"+expected_wheel+"'")
    compile(runner,str(target/'run.py'),'exec')
    (target/'run.py').write_text(runner,encoding='utf-8')
    records.append(dict(label=label,root=str(root),runner=str(target/'run.py'),original_test_sha256=original_sha,
        fixture_tests_unchanged=True,copied_application_source=False,
        script_hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in ('child.py','controller.py','win.py')},
        changes=['Rebind supervisor package/path/payload to i4 and1028.','Reject older descendant births before permit; no change to controller/input sequence or pytest assertions.']))
(HERE/'preparation.json').write_text(json.dumps(dict(status='PREPARED_NO_CONSOLE_STARTED',cases=records),indent=2))
print(json.dumps(dict(status='PREPARED_NO_CONSOLE_STARTED',cases=[dict(label=r['label'],root=r['root']) for r in records])))

"""Prepare the owned hidden-console mechanism; no console/process starts here."""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
prior = HERE.parent / 'qc12-installed-compatibility'
previous = Path(json.loads((prior / 'allocation.json').read_text())['root'])
root = Path(tempfile.mkdtemp(prefix='nexus-qc22-hidden-console-')).resolve()
shutil.copytree(previous / 'after', root / 'fixtures', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
for name in ('win.py', 'child.py', 'controller.py'):
    shutil.copyfile(HERE / name, root / name)
(root / 'cwd').mkdir()
(root / 'empty-path').mkdir()
(root / 'pytest.ini').write_text('[pytest]\nasyncio_mode=auto\nasyncio_default_fixture_loop_scope=function\n'
    'pythonpath=fixtures/tests fixtures/tests/execution_r4 fixtures/tests/quick_connect\n')
plugin = '''import ctypes, importlib.util, json, msvcrt, pathlib, sys
from ctypes import wintypes
import pytest
ROOT=pathlib.Path(__file__).resolve().parents[1]
def pytest_sessionstart(session):
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.GetConsoleMode.argtypes=[wintypes.HANDLE,ctypes.POINTER(wintypes.DWORD)]
    mode=wintypes.DWORD()
    assert sys.stdin.isatty() and kernel.GetConsoleMode(msvcrt.get_osfhandle(sys.stdin.fileno()),ctypes.byref(mode))
    origins={name:importlib.util.find_spec(name).origin for name in ('okto_nexus','nexus_connector_core','okto_nexus_connector')}
    assert all(pathlib.Path(value).resolve().is_relative_to(pathlib.Path(sys.prefix).resolve()) for value in origins.values())
    (ROOT/'origins.json').write_text(json.dumps(dict(origins=origins,prefix=sys.prefix,stdin_isatty=sys.stdin.isatty(),console_mode=mode.value,sys_path=sys.path),indent=2))
@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item,call):
    outcome=yield
    report=outcome.get_result()
    value=dict(nodeid=report.nodeid,when=report.when,outcome=report.outcome,duration=report.duration)
    if report.failed:
        value['failure']='\\n'.join(report.longreprtext.splitlines()[:8])
    with (ROOT/'reports.jsonl').open('a') as output:
        output.write(json.dumps(value)+'\\n')
'''
(root / 'fixtures/conftest.py').write_text(plugin, encoding='utf-8')
original = REPO / 'tests/quick_connect/test_quick_connect_pty.py'
copied = root / 'fixtures/tests/quick_connect/test_quick_connect_pty.py'
assert original.read_bytes() == copied.read_bytes()
pins = {p.relative_to(REPO).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
    for p in (REPO / 'src').rglob('*') if p.is_file() and '__pycache__' not in p.parts}
pins[original.relative_to(REPO).as_posix()] = hashlib.sha256(original.read_bytes()).hexdigest()
(root / 'source-pins.json').write_text(json.dumps(pins, indent=2))
(HERE / 'allocation.json').write_text(json.dumps(dict(root=str(root)), indent=2))
plan = dict(root=str(root), status='PREPARED_NO_CONSOLE_OR_PROCESS_STARTED',
    node='tests/quick_connect/test_quick_connect_pty.py::test_ctrl_c_after_issued_test_preserves_checkpoint_and_only_ends_observation',
    original_test_sha256=hashlib.sha256(original.read_bytes()).hexdigest(),
    mechanics=['Supervisor uses a new CREATE_NEW_CONSOLE child with STARTF_USESHOWWINDOW/SW_HIDE and redirected output.',
        'Child reopens real CONIN$, proves GetConsoleMode/isatty and hidden console window, then executes one unchanged original pytest node.',
        'A separate CREATE_NO_WINDOW controller attaches only to that child console after supervisor records parent/birth/image/script-path ownership.',
        'Console membership must contain only those proven Python clients plus controller; target main and controller must both be present. A fresh proof is required before input and signal.',
        'Controller alone ignores its Ctrl-C; it sends y+Enter using four KEY_EVENT records after the exact review prompt.',
        'Only after the exact issued-Test marker and another membership/birth/image check, controller calls GenerateConsoleCtrlEvent(CTRL_C_EVENT,0) once.',
        'Any unknown membership, non-real input, visible window or missing marker refuses the signal. No retry or global/user-console signal exists.',
        'An external 180s deadline permits containment only through retained handles for exact owned child/controller Python processes with proven birth/path/parent.',
        'PASS requires original pytest exit0 and preservation marker, which follows CLI130/checkpoint test_submitted/no binding/grant/explicit fixture gate release assertions.'],
    provider_calls=0, copied_application_source=False,
    script_pins={name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in ('win.py','child.py','controller.py')})
(HERE / 'mechanism.json').write_text(json.dumps(plan, indent=2))
print(json.dumps(dict(root=str(root), status=plan['status'], original_test_sha256=plan['original_test_sha256'])))

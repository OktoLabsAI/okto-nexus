"""Prepare isolated real-console resize; no console starts here."""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
old = HERE.parent / 'qc22-owned-console-interrupt'
root = Path(tempfile.mkdtemp(prefix='nexus-qc37-console-resize-')).resolve()
prior = Path(json.loads((old / 'allocation.json').read_text())['root'])
shutil.copytree(prior / 'fixtures', root / 'fixtures', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
shutil.copyfile(REPO / 'tests/quick_connect/test_quick_connect_pty.py', root / 'fixtures/tests/quick_connect/test_quick_connect_pty.py')
shutil.copyfile(prior / 'pytest.ini', root / 'pytest.ini')
for name in ['cwd', 'empty-path']:
    (root / name).mkdir()
shutil.copyfile(old / 'win.py', root / 'win.py')
child = (old / 'child.py').read_text()
child = child.replace("    sys.__stdin__ = sys.stdin", "    sys.__stdin__ = sys.stdin\n    sys.stdout = open('CONOUT$', 'w', encoding='utf-8', buffering=1)\n    sys.stderr = open('CONOUT$', 'w', encoding='utf-8', buffering=1)\n    sys.__stdout__, sys.__stderr__ = sys.stdout, sys.stderr\n    for stream in (sys.stdout, sys.stderr):\n        output_mode = wintypes.DWORD()\n        assert stream.isatty() and kernel.GetConsoleMode(msvcrt.get_osfhandle(stream.fileno()), ctypes.byref(output_mode))")
child = child.replace("console_mode=mode.value, stdin_isatty=sys.stdin.isatty(),", "console_mode=mode.value, stdin_isatty=sys.stdin.isatty(), stdout_isatty=sys.stdout.isatty(), stderr_isatty=sys.stderr.isatty(),")
child = child.replace('test_ctrl_c_after_issued_test_preserves_checkpoint_and_only_ends_observation', 'test_confirm_and_resume_use_actual_terminal_without_replaying_test')
child = child.replace('faulthandler_timeout=20', 'faulthandler_timeout=0')
(root / 'child.py').write_text(child)
shutil.copyfile(HERE / 'controller.py', root / 'controller.py')
pins = {p.relative_to(REPO).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in (REPO / 'src').rglob('*') if p.is_file() and '__pycache__' not in p.parts}
test = REPO / 'tests/quick_connect/test_quick_connect_pty.py'
pins[test.relative_to(REPO).as_posix()] = hashlib.sha256(test.read_bytes()).hexdigest()
(root / 'source-pins.json').write_text(json.dumps(pins, indent=2))
(HERE / 'allocation.json').write_text(json.dumps({'root': str(root)}, indent=2))
mechanism = {'status': 'PREPARED', 'original_test_sha256': hashlib.sha256(test.read_bytes()).hexdigest(),
    'mechanics': ['Child CREATE_NEW_CONSOLE SW_HIDE, real CONIN$ plus real stdout/stderr CONOUT$, no fake isatty/input.',
        'Controller attaches only after retained ownership/birth/image/path permit and verifies hidden same console and membership before every resize/input.',
        'ReadConsoleOutputCharacterW reads only owned console buffer. Exact two distinct prompts gate y+Enter; no signal is sent.',
        'At review prompt set owned window/buffer narrow50 columns; at resume prompt set wide100 columns, recording actual before/after dimensions.',
        'Only original confirm/resume test executes; it asserts one Test/probe and unchanged canonical snapshot on resume.',
        'PASS additionally requires real readable public ID and one-test completion marker in observed buffer.',
        '180s supervisor deadline, fail closed to NOT_QUALIFIED, containment only exact retained own Python handles.'], 'provider_calls': 0}
(HERE / 'mechanism.json').write_text(json.dumps(mechanism, indent=2))
runner = (old / 'run.py').read_text().replace("'qc22_environment'", "'qc37_environment'")
runner = runner.replace("sys.path.insert(0, str(HERE))", "sys.path.insert(0, str(HERE.parent / 'qc22-owned-console-interrupt'))")
runner = runner.replace("'SIGNAL_AND_PRESERVATION_MARKER_CONFIRMED'", "'RESIZE_AND_ONE_TEST_RESUME_CONFIRMED'")
(HERE / 'run.py').write_text(runner)
print(json.dumps({'root': str(root), 'prepared_only': True}))

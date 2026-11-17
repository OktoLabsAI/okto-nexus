"""One unchanged original pytest node in its new hidden console."""
import ctypes
from ctypes import wintypes
import hashlib
import importlib.util
import json
import msvcrt
import os
from pathlib import Path
import signal
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from win import console_members, hidden_window, kernel

value = dict(pid=os.getpid(), parent_pid=os.getppid(), sys_prefix=sys.prefix)
try:
    sys.stdin = open('CONIN$', 'r', encoding='utf-8')
    sys.__stdin__ = sys.stdin
    handle = msvcrt.get_osfhandle(sys.stdin.fileno())
    mode = wintypes.DWORD()
    assert kernel.GetConsoleMode(handle, ctypes.byref(mode)), 'CONIN$ is not a real console input'
    assert sys.stdin.isatty(), 'Console input must be real, not a stub'
    assert kernel.SetConsoleMode(handle, mode.value | 1)
    assert kernel.SetConsoleCtrlHandler(None, False)
    signal.signal(signal.SIGINT, signal.default_int_handler)
    value.update(console_mode=mode.value, stdin_isatty=sys.stdin.isatty(),
        console_members=console_members(), window=hidden_window())
    assert not value['window']['visible'], 'The owned console must remain hidden'
    prefix = Path(sys.prefix).resolve()
    origins = {name: importlib.util.find_spec(name).origin for name in
        ('okto_nexus', 'nexus_connector_core', 'okto_nexus_connector')}
    assert all(Path(path).resolve().is_relative_to(prefix) for path in origins.values())
    value['origins'] = origins
    original = ROOT / 'fixtures/tests/quick_connect/test_quick_connect_pty.py'
    value['original_test_sha256'] = hashlib.sha256(original.read_bytes()).hexdigest()
    (ROOT / 'child-ready.json').write_text(json.dumps(value, indent=2))
    import pytest
    code = pytest.main(['-c', str(ROOT / 'pytest.ini'), '--rootdir=' + str(ROOT / 'fixtures'),
        '--confcutdir=' + str(ROOT / 'fixtures'), str(original) +
        '::test_ctrl_c_after_issued_test_preserves_checkpoint_and_only_ends_observation',
        '-v', '-s', '--tb=short', '-o', 'faulthandler_timeout=20', '--junitxml=' + str(ROOT / 'junit.xml')])
    (ROOT / 'child-result.json').write_text(json.dumps(dict(pytest_exit=code, pid=os.getpid())))
    raise SystemExit(code)
except BaseException as error:
    if not isinstance(error, SystemExit):
        (ROOT / 'child-refused.json').write_text(json.dumps(dict(error=type(error).__name__, reason=str(error))))
    raise

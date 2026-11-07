"""Only the installed terminal sink function; no CLI, service or account."""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import secrets
import sys

SITE = Path('C:/Users/jpamb/AppData/Local/Temp/m1-observation-hosts-ai03jk1l/venv/Lib/site-packages')
sys.path.insert(0, str(SITE))
from okto_nexus.adapters.inbound.cli import remote_setup_io

assert Path(remote_setup_io.__file__).is_relative_to(SITE)
kernel = ctypes.WinDLL('kernel32')
kernel.GetConsoleWindow.restype = wintypes.HWND
user = ctypes.WinDLL('user32')
user.IsWindowVisible.argtypes = [wintypes.HWND]
user.IsWindowVisible.restype = wintypes.BOOL
assert sys.stdin.readline().strip() == 'go'
print('PTY_PROBE ' + json.dumps({'pid': os.getpid(), 'streams': {
    name: getattr(sys, name).isatty() for name in ('stdin', 'stdout', 'stderr')},
    'visible': bool(user.IsWindowVisible(kernel.GetConsoleWindow())),
    'installed_sink': str(Path(remote_setup_io.__file__))}), flush=True)
assert remote_setup_io.material_sink(True) is None
sink = remote_setup_io.material_sink(False)
assert callable(sink)
sink('nxs_' + secrets.token_hex(24))

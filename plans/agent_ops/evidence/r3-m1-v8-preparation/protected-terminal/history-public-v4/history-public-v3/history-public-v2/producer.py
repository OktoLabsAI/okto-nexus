"""Benign Python only: no product imports, provider or credential access."""
import ctypes
from ctypes import wintypes
import json
import os
import secrets
import sys
import time

assert 'OKTO_NEXUS_CONNECTER_DAEMON_FG' not in os.environ

kernel = ctypes.WinDLL('kernel32')
kernel.GetConsoleWindow.restype = wintypes.HWND
user = ctypes.WinDLL('user32')
user.IsWindowVisible.argtypes = [wintypes.HWND]
user.IsWindowVisible.restype = wintypes.BOOL
assert sys.stdin.readline().strip() == 'go'
print('PTY_PROBE ' + json.dumps({'pid': os.getpid(), 'streams': {
    name: getattr(sys, name).isatty() for name in ('stdin', 'stdout', 'stderr')},
    'visible': bool(user.IsWindowVisible(kernel.GetConsoleWindow()))}), flush=True)
if sys.argv[1] == 'hang':
    time.sleep(60)
else:
    print('\nCanonical agent key — shown once. Paste it into the Connector masked prompt:', file=sys.stderr)
    print('nxs_' + secrets.token_hex(24), file=sys.stderr, flush=True)
    if sys.argv[1] == 'ambiguous':
        print('nxs_' + secrets.token_hex(24), file=sys.stderr, flush=True)
    print('Keep this key if you need to resume import; the Server cannot recover its plaintext.\n', file=sys.stderr, flush=True)

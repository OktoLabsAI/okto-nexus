"""Synthetic producer waits for its consumer, matching the one-shot dependency."""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import secrets
import sys
import time

assert 'OKTO_NEXUS_CONNECTER_DAEMON_FG' not in os.environ
kernel = ctypes.WinDLL('kernel32')
kernel.GetConsoleWindow.restype = wintypes.HWND
user = ctypes.WinDLL('user32')
user.IsWindowVisible.argtypes = [wintypes.HWND]
user.IsWindowVisible.restype = wintypes.BOOL
mode = sys.argv[1]
assert sys.stdin.readline().strip() == 'go'
print('PTY_PROBE ' + json.dumps({'pid': os.getpid(), 'streams': {
    name: getattr(sys, name).isatty() for name in ('stdin', 'stdout', 'stderr')},
    'visible': bool(user.IsWindowVisible(kernel.GetConsoleWindow()))}), flush=True)
if mode == 'producer-deadline':
    time.sleep(60)
    raise SystemExit(5)
material = 'nxs_' + secrets.token_hex(24)
if mode == 'installed-functions':
    site = Path('C:/Users/jpamb/AppData/Local/Temp/m1-observation-hosts-ai03jk1l/venv/Lib/site-packages')
    sys.path.insert(0, str(site))
    from okto_nexus.adapters.inbound.cli import remote_setup_io
    assert Path(remote_setup_io.__file__).is_relative_to(site)
    assert remote_setup_io.material_sink(True) is None
    sink = remote_setup_io.material_sink(False)
    assert callable(sink)
    sink(material)
    sys.stderr.flush()
else:
    print('\nCanonical agent key — shown once. Paste it into the Connector masked prompt:', file=sys.stderr)
    print(material, file=sys.stderr)
    if mode == 'ambiguous-before':
        print('nxs_' + secrets.token_hex(24), file=sys.stderr)
    print('Keep this key if you need to resume import; the Server cannot recover its plaintext.\n', file=sys.stderr, flush=True)
if mode == 'ambiguous-before':
    raise SystemExit(0)
until = time.monotonic() + 50
while not Path('consumer-ack.json').exists():
    if time.monotonic() >= until:
        raise SystemExit(6)
    time.sleep(.01)
Path('producer-saw-ack.json').write_text('{"synthetic_completion_signal_seen":true}')
if mode == 'ambiguous-after':
    print('nxs_' + secrets.token_hex(24), file=sys.stderr, flush=True)

"""Synthetic key, delayed own handoff, then wait for the consumer completion."""
import ctypes
import hashlib
from ctypes import wintypes
import json
import os
from pathlib import Path
import secrets
import sys
import time

assert 'OKTO_NEXUS_CONNECTER_DAEMON_FG' not in os.environ
SITE = Path('C:/Users/jpamb/AppData/Local/Temp/m1-recovery-diagnostics-installed-xtfm5o4x/venv/Lib/site-packages')
sys.path.insert(0, str(SITE))
from okto_nexus.adapters.inbound.cli import remote_setup_io
assert Path(remote_setup_io.__file__).is_relative_to(SITE)
kernel = ctypes.WinDLL('kernel32')
kernel.GetConsoleWindow.restype = wintypes.HWND
user = ctypes.WinDLL('user32')
user.IsWindowVisible.argtypes = [wintypes.HWND]
user.IsWindowVisible.restype = wintypes.BOOL
mode, handoff = sys.argv[1], Path(sys.argv[2])
assert not handoff.exists()
assert sys.stdin.readline().strip() == 'go'
Path('producer-started.json').write_text('{"synthetic_producer_started":true}')
print('PTY_PROBE ' + json.dumps({'pid': os.getpid(), 'streams': {
    name: getattr(sys, name).isatty() for name in ('stdin', 'stdout', 'stderr')},
    'visible': bool(user.IsWindowVisible(kernel.GetConsoleWindow())),
    'material_sink_module': remote_setup_io.__file__,
    'material_sink_sha256': hashlib.sha256(Path(remote_setup_io.__file__).read_bytes()).hexdigest()}), flush=True)
sink = remote_setup_io.material_sink(False)
assert callable(sink)
sink('nxs_' + secrets.token_hex(24))
sys.stderr.flush()
# The helper must observe the complete key block while the handoff is absent.
time.sleep(.75)
if mode == 'marker-absent':
    time.sleep(60)
elif mode == 'marker-divergent':
    print('Host handoff (contains no key): ' + str(handoff) + '.different', flush=True)
else:
    export, destination = remote_setup_io.handoff_sink(handoff, 'synthetic-own-setup', as_json=False)
    assert destination == str(handoff)
    export({'format': 'okto.remote-setup-handoff', 'bootstrap': {'setup_run_id': 'synthetic-own-setup'}})
    sys.stdout.flush()
    until = time.monotonic() + 30
    while not Path('consumer-ack.json').exists():
        if time.monotonic() >= until:
            raise SystemExit(6)
        time.sleep(.01)
    Path('producer-saw-ack.json').write_text('{"synthetic_completion_signal_seen":true}')

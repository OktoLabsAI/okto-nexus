import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = Path(json.loads((HERE / 'allocation.json').read_text())['root'])
OUT = HERE / 'evidence'
OUT.mkdir(exist_ok=True)
result = json.loads((ROOT / 'result.json').read_text())
ready = json.loads((ROOT / 'child-ready.json').read_text())
assert result['status'] == 'NOT_QUALIFIED' and not result['source_drift'] and not result['payload_drift']
assert all(not row['alive'] for row in result['process_proofs'])
pids = sorted({row['pid'] for row in result['process_proofs'] + result['observed_non_clients']})
command = 'Get-CimInstance Win32_Process -Filter "' + ' OR '.join('ProcessId=' + str(pid) for pid in pids) + '" | Select-Object ProcessId,ParentProcessId,ExecutablePath | ConvertTo-Json'
probe = subprocess.run(['rtk', 'proxy', 'C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe', '-NoProfile', '-Command', command], capture_output=True, text=True, timeout=10)
assert probe.returncode == 0 and not probe.stdout.strip()
user = ctypes.WinDLL('user32', use_last_error=True)
user.IsWindow.argtypes = [wintypes.HWND]
assert not user.IsWindow(ready['window']['hwnd'])
counts = []
for db in (ROOT / 'environment').rglob('nexus.db'):
    connection = sqlite3.connect(db.as_uri() + '?mode=ro', uri=True)
    try:
        connection.execute('PRAGMA query_only=ON')
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        values = {name: connection.execute('SELECT COUNT(*) FROM ' + name).fetchone()[0] for name in ('connection_setup_commits', 'runtime_execution_grants', 'execution_bindings', 'execution_operations') if name in tables}
        assert all(value == 0 for value in values.values())
        counts.append({'database': str(db), 'counts': values})
    finally:
        connection.close()
for name in ['child-ready.json', 'controller-refused.json', 'controller-started.json', 'origins.json', 'permit.json', 'result.json', 'source-pins.json', 'reports.jsonl', 'child.py', 'controller.py', 'win.py']:
    if (ROOT / name).exists():
        shutil.copyfile(ROOT / name, OUT / name)
report = {
    'at': datetime.now(timezone.utc).isoformat(), 'status': 'NOT_QUALIFIED', 'requirement': 'QC030',
    'cause': 'Controller refused before input/resize because initial buffer cell count exceeded its bound or was otherwise outside 0<count<=1000000. Dimensions were not persisted before that assertion; no exact dimension claim.',
    'not_product_failure': True,
    'real_console': {'stdin_tty': True, 'stdout_tty': True, 'stderr_tty': True, 'GetConsoleMode': True, 'hidden': True},
    'input_events_sent': 0, 'signals_sent': 0, 'resize_attempts': 0,
    'pytest_result': 'INTERRUPTED_BY_OWN_CONTAINMENT_NOT_PASS',
    'original_test_sha256': ready['original_test_sha256'], 'original_test_modified': False,
    'containment': result['containment'], 'all_owned_python_and_conhosts_absent': True, 'console_window_destroyed': True,
    'process_absence_probe': {'pids': pids, 'command': command, 'exit_code': probe.returncode, 'stdout_empty': True},
    'canonical_counts_after': counts, 'payload_files': 1027, 'payload_drift': [], 'source_drift': [],
    'provider_calls': 0, 'retry_started': False,
    'limits': ['No resize, readable-ID or Test/resume qualification achieved.', 'This attempt proves only real isolated console readiness and conservative refusal/owned cleanup.', 'No user console, Windows configuration or product/prefix was modified.']}
(HERE / 'qualification.json').write_text(json.dumps(report, indent=2))
manifest = [{'path': p.relative_to(HERE).as_posix(), 'bytes': p.stat().st_size, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(HERE.rglob('*')) if p.is_file() and p.name != 'manifest.json']
(HERE / 'manifest.json').write_text(json.dumps(manifest, indent=2))
print(json.dumps({'status': report['status'], 'qualification_sha256': hashlib.sha256((HERE / 'qualification.json').read_bytes()).hexdigest(), 'all_owned_processes_absent': True, 'db_count_proofs': len(counts)}))

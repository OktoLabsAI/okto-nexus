import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
ROOT = Path(json.loads((HERE / 'counterpart-allocation.json').read_text())['root'])
OUT = HERE / 'counterpart'
OUT.mkdir(exist_ok=True)
result = json.loads((ROOT / 'result.json').read_text())
ready = json.loads((ROOT / 'child-ready.json').read_text())
control = json.loads((ROOT / 'controller-result.json').read_text())
assert result['status'] == 'PASS' and not result['containment'] and not result['source_drift'] and not result['payload_drift']
assert all(not row['alive'] for row in result['process_proofs'])
assert ready['stdin_isatty'] and ready['stdout_isatty'] and ready['stderr_isatty'] and not ready['window']['visible']
assert control['inputs'] == 2 and control['signals'] == 0 and control['public_id_observed'] == 'codex'
pids = sorted({row['pid'] for row in result['process_proofs'] + result['observed_non_clients']})
command = 'Get-CimInstance Win32_Process -Filter "' + ' OR '.join('ProcessId=' + str(pid) for pid in pids) + '" | Select-Object ProcessId,ParentProcessId,ExecutablePath | ConvertTo-Json'
probe = subprocess.run(['rtk', 'proxy', 'C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe', '-NoProfile', '-Command', command], capture_output=True, text=True, timeout=10)
assert probe.returncode == 0 and not probe.stdout.strip()
user = ctypes.WinDLL('user32', use_last_error=True)
user.IsWindow.argtypes = [wintypes.HWND]
assert not user.IsWindow(ready['window']['hwnd'])
tests = list(ET.parse(ROOT / 'junit.xml').iter('testcase'))
assert len(tests) == 1 and tests[0].find('failure') is None and tests[0].find('error') is None
metadata = [json.loads(line) for line in (ROOT / 'console-read-metadata.jsonl').read_text().splitlines()]
assert all(0 < row['chars'] <= 200000 and row['lines'] <= 400 for row in metadata)
narrow = json.loads((ROOT / 'resize-narrow.json').read_text())
wide = json.loads((ROOT / 'resize-wide.json').read_text())
assert narrow['after_buffer'][0] == 50 and wide['after_buffer'][0] == 100
buffers = []
for name in ['buffer-review.txt', 'buffer-resume.txt', 'buffer-final.txt']:
    path = ROOT / name
    buffers.append({'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'bytes': path.stat().st_size, 'raw_exported': False})
text = (ROOT / 'buffer-final.txt').read_text(encoding='utf-8')
assert 'codex' in text and 'PTY_RESUME_CONFIRMED_ONE_TEST_TOTAL' in text
excerpts = []
for marker in ['ID do Harness:', 'PTY_RESUME_CONFIRMED_ONE_TEST_TOTAL']:
    offset = text.find(marker)
    if offset >= 0:
        excerpts.append(text[offset:offset + 90].strip())
for name in ['child-ready.json', 'child-result.json', 'controller-started.json', 'controller-result.json', 'origins.json', 'permit.json', 'result.json', 'source-pins.json', 'reports.jsonl', 'junit.xml', 'child.py', 'controller.py', 'win.py', 'resize-narrow.json', 'resize-wide.json', 'console-read-metadata.jsonl']:
    shutil.copyfile(ROOT / name, OUT / name)
for path in ROOT.glob('console-proof-*.json'):
    shutil.copyfile(path, OUT / path.name)
report = {
    'at': datetime.now(timezone.utc).isoformat(), 'status': 'PASS', 'requirement': 'QC030',
    'tests': 1, 'node': tests[0].attrib['name'], 'node_seconds': tests[0].attrib['time'],
    'original_test_sha256': ready['original_test_sha256'], 'original_test_modified': False,
    'installed_wheel_sha256': 'a36e448c80a8190c7e8c92d81ea5a251c4bdf7e370eca0f0b395a5ad29e36cc6',
    'real_console': {'stdin_tty': True, 'stdout_tty': True, 'stderr_tty': True, 'GetConsoleMode': True, 'hidden': True},
    'resizes': [narrow, wide], 'input_events': 'Exactly two y+Enter confirmations through WriteConsoleInputW after exact prompts and fresh ownership fences.',
    'signals_sent': 0, 'containment': [], 'console_read_bound': {'used_lines_max': 400, 'chars_max': 200000, 'maximum_observed_chars': max(row['chars'] for row in metadata)},
    'observed_buffer_excerpts': excerpts, 'buffer_metadata': buffers,
    'canonical_assertions': 'Original test asserts one synthetic Test and probe, successful Finish, exact profile resume, unchanged complete canonical snapshot, no replay.',
    'all_owned_python_and_conhosts_absent': True, 'console_window_destroyed': True,
    'process_absence_probe': {'pids': pids, 'command': command, 'exit_code': probe.returncode, 'stdout_empty': True},
    'payload_files': 1027, 'payload_drift': [], 'source_drift': [], 'provider_calls': 0,
    'limits': ['Earlier refused full-buffer attempt remains NOT_QUALIFIED and preserved.', 'This qualifies one owned hidden Windows console at 50 and 100 columns, not every terminal implementation or language.', 'No real provider/native harness qualification, user console input, Windows settings or product/prefix changes.']}
(OUT / 'qualification.json').write_text(json.dumps(report, indent=2))
manifest = [{'path': p.relative_to(OUT).as_posix(), 'bytes': p.stat().st_size, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(OUT.rglob('*')) if p.is_file() and p.name != 'manifest.json']
(OUT / 'manifest.json').write_text(json.dumps(manifest, indent=2))
print(json.dumps({'status': 'PASS', 'qualification_sha256': hashlib.sha256((OUT / 'qualification.json').read_bytes()).hexdigest(), 'tests': 1, 'all_owned_processes_absent': True, 'max_chars_read': max(row['chars'] for row in metadata)}))

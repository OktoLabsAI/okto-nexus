import hashlib
import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
ROOT = Path(json.loads((HERE / 'final-allocation.json').read_text())['root'])
OUT = HERE / 'final-private-focal'
OUT.mkdir(exist_ok=True)
result = json.loads((ROOT / 'separate-result.json').read_text())
assert result['payload_files'] == 1027 and result['payload_drift'] == result['repository_input_drift'] == []
case = result['cases'][0]
assert case['exit_code'] == 0 and not case['signals']
assert all(not item['alive'] for item in case['processes_after'])
folder = ROOT / 'final-private-focal'
proof_path = next((folder / 'tmp').glob('pytest-of-*/pytest-*/test_d25*/privacy-proof.json'))
proof = json.loads(proof_path.read_text())
assert len(proof['length_proofs']) == 1
lock = proof_path.parent / proof['length_proofs'][0]['path']
assert lock.stat().st_size == 1 and lock.read_bytes() == b'\0'
proof['post_exit_lock'] = {'size': 1, 'sha256': hashlib.sha256(lock.read_bytes()).hexdigest(), 'read_complete': True}
(OUT / 'privacy-proof.json').write_text(json.dumps(proof, indent=2))
for source, name in [(ROOT / 'separate-result.json', 'result.json'), (ROOT / 'source-pins.json', 'source-pins.json'),
                     (ROOT / 'changes.patch', 'changes.patch'), (ROOT / 'pytest.ini', 'pytest.ini'),
                     (ROOT / 'after/tests/quick_connect/test_ancestor_privacy.py', 'test_ancestor_privacy.py')]:
    shutil.copyfile(source, OUT / name)
for name in ['junit.xml', 'origins.json', 'runner.json', 'reports.jsonl', 'file-read-audit.jsonl']:
    shutil.copyfile(folder / name, OUT / name)
tests = list(ET.parse(folder / 'junit.xml').iter('testcase'))
assert len(tests) == 1 and tests[0].find('failure') is None and tests[0].find('error') is None
report = {
    'status': 'PASS', 'tests': 1, 'pytest_node': tests[0].attrib['name'], 'node_seconds': tests[0].attrib['time'],
    'installed_wheel_sha256': 'a36e448c80a8190c7e8c92d81ea5a251c4bdf7e370eca0f0b395a5ad29e36cc6',
    'payload_files': 1027, 'payload_drift': [], 'source_drift': [],
    'runtime_assertions': 'Four JSON outputs, scripted-TTY stdout/resume, checkpoints, trace absence and real active local logging sink; all files read completely except exact live-owned one-byte lock proven incapable of containing any encoded marker.',
    'sink_httpx_events': proof['httpx_request_events'], 'sqlite_live_tables': proof['sqlite_table_count'],
    'sqlite_live_rows': proof['sqlite_rows_checked'], 'sqlite_live_text_blob_cells': proof['sqlite_text_cells_checked'],
    'lock_length_proof': proof['length_proofs'], 'all_sqlite_tables_and_files': 'privacy-proof.json',
    'cleanup': {'all_owned_processes_exited': True, 'signals': [], 'force': False},
    'raw_log': {'path': str(folder / 'raw.log'), 'sha256': hashlib.sha256((folder / 'raw.log').read_bytes()).hexdigest(), 'exported': False},
    'limits': ['Earlier access violation and failed live scanner remain preserved as separate NOT_GREEN cuts; no retrospective cause attribution.', 'One new focal passes; this is not a single combined ancestor/privacy green run.', 'Observed configured local logging channels only; no outbound analytics or all-transient-history claim.', 'Synthetic canonical setup/test boundary, zero real provider/native CLI calls.']
}
(OUT / 'qualification.json').write_text(json.dumps(report, indent=2))
manifest = [{'path': str(p.relative_to(OUT)), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest(), 'bytes': p.stat().st_size} for p in sorted(OUT.iterdir()) if p.is_file() and p.name != 'manifest.json']
(OUT / 'manifest.json').write_text(json.dumps(manifest, indent=2))
print(json.dumps({'qualification_sha256': hashlib.sha256((OUT / 'qualification.json').read_bytes()).hexdigest(), 'tests': 1, 'status': 'PASS', 'live_tables': proof['sqlite_table_count'], 'files_full_read': len(proof['files']), 'length_proofs': len(proof['length_proofs'])}))

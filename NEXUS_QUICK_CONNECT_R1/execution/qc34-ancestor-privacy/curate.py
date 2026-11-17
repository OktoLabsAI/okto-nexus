"""Curate metadata only; never export fixture databases or captured logs."""
import hashlib
import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET

OUT = Path(__file__).resolve().parent
ORIGINAL = Path('C:/Users/jpamb/AppData/Local/Temp/nexus-qc34-ancestor-privacy-3d5bynj3')
ROUTED = Path('C:/Users/jpamb/AppData/Local/Temp/nexus-qc34-routed-focals-_f1l4j9w')


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def copy_metadata(source, relative):
    target = OUT / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)


original = read(ORIGINAL / 'result.json')
routed = read(ROUTED / 'separate-result.json')
scan = read(OUT / 'post-exit-privacy-scan.json')
assert not original['payload_drift'] and not original['repository_input_drift']
assert not routed['payload_drift'] and not routed['repository_input_drift']
assert all(not p['alive'] for cut in [original, routed] for c in cut['cases'] for p in c['processes_after'])
assert not scan['violations'] and not scan['files']['read_errors']
assert len([t for t in scan['sqlite']['tables'] if not t['table'].startswith('sqlite_')]) == 162

for source, target in [
    (ORIGINAL / 'result.json', 'original/result.json'),
    (ORIGINAL / 'source-pins.json', 'original/source-pins.json'),
    (ORIGINAL / 'extra-test-pin.json', 'original/test-pin.json'),
    (ROUTED / 'separate-result.json', 'routed/result.json'),
    (ROUTED / 'source-pins.json', 'routed/source-pins.json'),
    (ROUTED / 'extra-test-pin.json', 'routed/test-pin.json'),
    (ROUTED / 'changes.patch', 'routed/changes.patch'),
    (ROUTED / 'pytest.ini', 'routed/pytest.ini'),
    (ROUTED / 'after/tests/quick_connect/test_ancestor_privacy.py', 'routed/test_ancestor_privacy.py'),
]:
    copy_metadata(source, target)

nodes = []
raw = []
for case in routed['cases']:
    label = case['label']
    folder = ROUTED / label
    for name in ['origins.json', 'runner.json']:
        copy_metadata(folder / name, f'routed/{label}/{name}')
    reports = [json.loads(line) for line in (folder / 'reports.jsonl').read_text(encoding='utf-8').splitlines()]
    for item in reports:
        if 'failure' in item:
            item['failure'] = 'PermissionError at test_ancestor_privacy.py:173 data = path.read_bytes(); raw failure retained in owned Temp.'
    (OUT / 'routed' / label / 'reports.jsonl').write_text(''.join(json.dumps(item) + '\n' for item in reports), encoding='utf-8')
    # Failed JUnit contains captured DEBUG messages; preserve only status metadata.
    tree = ET.parse(folder / 'junit.xml')
    for node in tree.iter('testcase'):
        failed = node.find('failure') is not None
        nodes.append({'case': label, 'name': node.attrib['name'], 'seconds': node.attrib['time'], 'status': 'FAIL' if failed else 'PASS'})
    raw.append({'path': str(folder / 'raw.log'), 'sha256': sha(folder / 'raw.log'), 'exported': False})

raw.append({'path': str(ORIGINAL / 'ancestor-privacy/raw.log'), 'sha256': sha(ORIGINAL / 'ancestor-privacy/raw.log'), 'bytes': (ORIGINAL / 'ancestor-privacy/raw.log').stat().st_size, 'exported': False})
report = {
    'status': 'NOT_GREEN',
    'candidate_source': 'fa031697b37a1b879d855f7858f01320addf0df7',
    'wheel_sha256': 'a36e448c80a8190c7e8c92d81ea5a251c4bdf7e370eca0f0b395a5ad29e36cc6',
    'original': {'status': 'INCONCLUSIVE_ACCESS_VIOLATION', 'exit_code': 3221225477, 'causality': 'Not attributed to faulthandler; no counterproof establishes cause.', 'privacy_node_started': False},
    'routed': {'nodes': nodes, 'faulthandler_timeout': 0, 'external_deadline_seconds_per_node': 180, 'input': 'Finite exact-prompt routing, rejects unexpected prompts; scripted TTY, not real PTY.'},
    'C13': {'status': 'PASS', 'scope': 'Ancestor first registered through canonical setup; nested CWD retains its exact child root through review and Finish, with a distinct workspace/binding and original profile/authority preserved.'},
    'D25': {'runtime_node': 'FAIL_PERMISSION_ERROR_DURING_LIVE_FILE_READ', 'scope': 'Active real local FileHandler with before/after markers and 75 HTTPX events; stdout/JSON/resume assertions completed before file-read failure. Same retained files/database scanned read-only after process exit.', 'post_exit_scan': 'post-exit-privacy-scan.json', 'application_tables': 162, 'internal_tables': 1, 'rows': 251, 'text_or_blob_cells': 601, 'files': 17, 'sensitive_hits': 0, 'read_errors': 0, 'only_exclusion': 'Synthetic input workspace/.git/config, positively verified to contain the private origin.'},
    'payload_files': 1027, 'payload_drift': [], 'source_drift': [],
    'cleanup': {'all_owned_processes_exited': True, 'signals': [], 'force': False, 'data_preserved': True},
    'raw_logs': raw,
    'limits': ['No claim of a single green two-case round.', 'Post-exit persistence is not a proof of all transient live database states. Lock or transient files can disappear on close; the post-exit scan does not convert the failed live scan into a passing runner.', 'Only the explicitly enabled local logging channels were observed; no outbound product analytics qualification.', 'Synthetic canonical Setup/Test boundaries; zero real provider/native CLI calls.', 'Raw logs, checkpoints, databases and credential-bearing fixture material remain in owned Temp and are not exported.'],
}
(OUT / 'qualification.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
manifest = [{'path': str(p.relative_to(OUT)), 'bytes': p.stat().st_size, 'sha256': sha(p)} for p in sorted(OUT.rglob('*')) if p.is_file() and p.name != 'manifest.json']
(OUT / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'qualification_sha256': sha(OUT / 'qualification.json'), 'files': len(manifest), 'nodes': nodes}))

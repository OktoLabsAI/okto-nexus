"""Copy only the closed, audited browser allowlist; no fixture/private reads."""
import hashlib
import json
from pathlib import Path
import re

REPO = Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
OUT = REPO / 'plans/agent_ops/evidence/pr10-correlation'
SOURCE = Path('C:/Users/jpamb/AppData/Local/Temp/obs12-installed-browser-6fs92j_4/curated-v2')
sha = lambda value: hashlib.sha256(value).hexdigest()
manifest = json.loads((SOURCE / 'manifest.json').read_text(encoding='utf-8'))
summary = json.loads((SOURCE / 'campaign-summary.json').read_text(encoding='utf-8'))
assert summary['status'] == 'PASS' and summary['checkpoints_passed'] == 8
assert summary['browser_closed'] and summary['server_drain_state'] == 'DRAINED'
assert summary['process_wait_code'] == 0 and summary['trace_header_audit_passed']
assert summary['wheel_sha256'] == '991a1995bec626012d113df12c90e897274a83b320373539c28b73c6b4fb7be1'
entries = manifest['entries']
assert sha(json.dumps(entries, sort_keys=True, separators=(',', ':')).encode()) == manifest['aggregate_sha256']
assert manifest['aggregate_sha256'] == '370e6f737f1cc9ffe06bede76cea9df326c8443a59c9130b4f69214ba4ae3d51'
assert len(entries) == 230
assert {p.relative_to(SOURCE).as_posix() for p in SOURCE.rglob('*') if p.is_file()} == {
    'manifest.json', *(row['path'] for row in entries)}
rows = entries + [dict(path='manifest.json', sha256=sha((SOURCE / 'manifest.json').read_bytes()))]
reports_path = OUT / 'reports.json'
reports = json.loads(reports_path.read_text(encoding='utf-8'))
assert reports['collection_phase'] == 'partial_closed_reports'
pattern = re.compile(rb'nxobs_[0-9a-f]{64}|nxs_[0-9a-f]{48}')
for row in rows:
    source = (SOURCE / row['path']).resolve()
    assert source.is_relative_to(SOURCE) and source.is_file()
    assert 'private' not in source.name.lower() and source.suffix.lower() not in ('.db', '.whl', '.key')
    data = source.read_bytes()
    assert sha(data) == row['sha256']
    assert not pattern.search(data), row['path']
    target = OUT / 'browser' / row['path']
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        assert target.read_bytes() == data
    else:
        target.write_bytes(data)
    relative = target.relative_to(REPO).as_posix()
    if not any(item['path'] == relative for item in reports['retained_inputs']):
        reports['retained_inputs'].append(dict(path=relative, original_path=str(source),
            bytes=len(data), sha256=sha(data), original_sha256=sha(data),
            exact_original_bytes=True, credential_pattern_matches=0))
reports['browser'] = dict(summary='plans/agent_ops/evidence/pr10-correlation/browser/campaign-summary.json',
    manifest='plans/agent_ops/evidence/pr10-correlation/browser/manifest.json',
    manifest_aggregate_sha256=manifest['aggregate_sha256'], status='PASS',
    checkpoints=8, canonical_tables_unchanged=13, network_requests=467,
    scope='Actual installed HTTP and browser over explicitly synthetic canonical records; no real process/Core proof.')
reports_path.write_text(json.dumps(reports, indent=2) + '\n', encoding='utf-8')
print(json.dumps(dict(copied_files=len(rows), audited_requests=467, checkpoints=8,
    aggregate_sha256=manifest['aggregate_sha256']), indent=2))

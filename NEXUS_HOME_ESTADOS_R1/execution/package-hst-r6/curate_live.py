"""Curate sanitized metadata only; raw HTTP/session logs remain in owned Temp."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil

import psutil

HERE = Path(__file__).resolve().parent
report = json.loads((HERE/'live-qualification.json').read_text(encoding='utf-8'))
assert report['status'] == 'PASS' and report['cleanup_verified']
assert not report['payload_drift'] and not report['source_drift']
root = Path(report['root']).resolve()
observations = []
for info in report['process']['known_processes']:
    same = False
    try:
        process = psutil.Process(info['pid'])
        same = process.create_time() == info['birth'] and process.exe() == info['exe']
    except psutil.NoSuchProcess:
        pass
    observations.append(dict(**info, same_process_still_alive=same))
assert not any(row['same_process_still_alive'] for row in observations)
evidence = HERE/'live-evidence'
evidence.mkdir(exist_ok=True)
for name in ('origins.json', 'payload-before.json', 'payload-after.json'):
    shutil.copyfile(root/name, evidence/name)
raw = root/'stdout.log'
proof = dict(at=datetime.now(timezone.utc).isoformat(), status='PASS',
    process_observations=observations,
    raw_logs=dict(location=str(raw), sha256=hashlib.sha256(raw.read_bytes()).hexdigest(),
        size=raw.stat().st_size, copied_to_repository=False),
    canonical_stop=report['summary']['cleanup'],
    provider_calls=0, personal_credentials_accessed=False,
    limits=['Smoke qualifies real HTTP MCP/SDK transport, not a real model/harness or browser.',
        '100ms process polling does not enumerate every short-lived child.',
        'Only sanitized origins, payload hashes, summary and cleanup metadata are curated.'])
(evidence/'cleanup-and-log-hash.json').write_text(json.dumps(proof, indent=2)+'\n', encoding='utf-8')
files = [HERE/'live-qualification.json', HERE/'live_mcp.py', HERE/'curate_live.py', *evidence.glob('*.json')]
manifest = {str(path.relative_to(HERE)).replace('\\','/'):hashlib.sha256(path.read_bytes()).hexdigest() for path in files}
(HERE/'live-manifest.json').write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8')
print(json.dumps(dict(status='PASS', report=str(HERE/'live-qualification.json'),
    report_sha256=manifest['live-qualification.json'], known_processes_absent=len(observations),
    raw_log_copied=False)))

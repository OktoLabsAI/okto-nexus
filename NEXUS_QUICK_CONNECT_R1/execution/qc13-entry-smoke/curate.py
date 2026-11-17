"""Pin the fresh installed entry cut without replacing its raw report."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import socket

HERE = Path(__file__).resolve().parent
report = json.loads((HERE / 'qualification.json').read_text('utf-8'))
package = json.loads((HERE.parent / 'qc11-package/qualification.json').read_text('utf-8'))
assert report['status'] == 'PASS_SCOPED_INSTALLED_ENTRY'
assert report['cleanup']['canonical_exit'] == report['cleanup']['physical_exit'] == 0
assert report['cleanup']['forced'] is False and report['provider_calls'] == 0
assert len(report['commands']) == 3
assert report['commands'][-1]['result']['code'] == 'CONNECT_ID_UNSUPPORTED_SERVER'
stop = report['cleanup']['command']
port = int(stop[stop.index('--port') + 1])
with socket.socket() as sock:
    sock.settimeout(1)
    listening = sock.connect_ex(('127.0.0.1', port)) == 0
assert not listening, 'Record unexpected listener; never stop an unrelated process'
proof = dict(at=datetime.now(timezone.utc).isoformat(),
    source_candidate_commit=package['source_candidate_commit'],
    wheel_sha256=package['artifacts']['okto_nexus-0.3.6-py3-none-any.whl'],
    original_failure='../qc10-entry-smoke/qualification.json',
    current_result='qualification.json', actual_old_server=True,
    scope='Installed console cold plan / explicit script-add guard / actual old Server capability refusal',
    lifecycle='Canonical stop and direct process handle confirmed exit 0; listener absent at curation',
    provider_calls=0, listening_after=False,
    limitations=report['limitations'])
(HERE / 'proof.json').write_text(json.dumps(proof, indent=2) + '\n', encoding='utf-8')
manifest = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
    for path in HERE.iterdir() if path.is_file() and path.name != 'manifest.json'}
(HERE / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
print(json.dumps(dict(status='PASS', commands=3, provider_calls=0, listening_after=False)))

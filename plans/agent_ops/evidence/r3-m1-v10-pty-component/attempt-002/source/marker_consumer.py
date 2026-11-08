"""Read the public handoff before stdin, matching the real Connector ordering."""
import hashlib
import json
import os
from pathlib import Path
import re
import sys

assert os.environ.get('OKTO_NEXUS_CONNECTER_DAEMON_FG') == '1'
Path('consumer-started.json').write_text('{"synthetic_consumer_started":true}')
handoff = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
assert handoff == {'format': 'okto.remote-setup-handoff', 'bootstrap': {'setup_run_id': 'synthetic-own-setup'}}
assert not sys.stdin.isatty()
value = sys.stdin.readline().strip()
assert re.fullmatch(r'nxs_[0-9a-f]{48}', value)
Path('consumer-ack.json').write_text('{"synthetic_material_received":true}')
print(hashlib.sha256(value.encode()).hexdigest(), flush=True)

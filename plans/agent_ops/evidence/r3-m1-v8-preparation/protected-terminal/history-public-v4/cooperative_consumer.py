"""Private stdin only, then a public completion bit; never persist material."""
import hashlib
import os
from pathlib import Path
import re
import sys
import time

assert os.environ.get('OKTO_NEXUS_CONNECTER_DAEMON_FG') == '1'
mode = sys.argv[1]
Path('consumer-started.json').write_text('{"synthetic_consumer_started":true}')
assert not sys.stdin.isatty()
if mode == 'installed-functions':
    site = Path('C:/Users/jpamb/AppData/Local/Temp/m1-observation-hosts-ai03jk1l/venv/Lib/site-packages')
    sys.path.insert(0, str(site))
    from okto_nexus_connector.identity import import_flow
    assert Path(import_flow.__file__).is_relative_to(site)
    value = import_flow.read_secret_stdin()
else:
    value = sys.stdin.readline().strip()
assert re.fullmatch(r'nxs_[0-9a-f]{48}', value)
Path('consumer-ack.json').write_text('{"synthetic_material_received":true}')
if mode == 'consumer-deadline':
    time.sleep(60)
if mode == 'consumer-nonzero':
    raise SystemExit(9)
print(hashlib.sha256(value.encode()).hexdigest(), flush=True)

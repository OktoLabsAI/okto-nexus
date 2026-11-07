"""Only the installed credential-stdin parser, never the import/CLI flow."""
import hashlib
import os
from pathlib import Path
import sys

assert os.environ.get('OKTO_NEXUS_CONNECTER_DAEMON_FG') == '1'

SITE = Path('C:/Users/jpamb/AppData/Local/Temp/m1-observation-hosts-ai03jk1l/venv/Lib/site-packages')
sys.path.insert(0, str(SITE))
from okto_nexus_connector.identity import import_flow

assert Path(import_flow.__file__).is_relative_to(SITE)
assert not sys.stdin.isatty()
Path('consumer-started.json').write_text('{"synthetic_consumer_started":true}')
value = import_flow.read_secret_stdin()
print(hashlib.sha256(value.encode()).hexdigest(), flush=True)

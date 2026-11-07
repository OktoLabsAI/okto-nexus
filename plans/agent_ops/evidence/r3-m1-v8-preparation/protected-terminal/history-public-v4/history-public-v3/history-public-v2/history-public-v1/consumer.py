"""Only stdin receives synthetic material; digest returned over private pipe."""
import hashlib
from pathlib import Path
import re
import sys

Path('consumer-started.json').write_text('{"synthetic_consumer_started":true}')
value = sys.stdin.readline().strip()
assert re.fullmatch(r'nxs_[0-9a-f]{48}', value)
assert not sys.stdin.isatty()
print(hashlib.sha256(value.encode()).hexdigest(), flush=True)

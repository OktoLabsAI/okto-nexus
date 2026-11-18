"""Frozen runner; only actual AX session chooser locator differs from prior cut."""
import hashlib
from pathlib import Path

HERE=Path(__file__).resolve().parent
raw=(HERE/'run.py').read_bytes();assert hashlib.sha256(raw).hexdigest()=='298bb89a72bf7ea956ede8dd14bd058b82e718b9eae9161028110581a09f6377'
source=raw.decode().replace('\r\n','\n');old="(HERE/'browser.js')";assert source.count(old)==1
exec(compile(source.replace(old,"(HERE/'browser-session-role.js')"),str(HERE/'run.py'),'exec'))

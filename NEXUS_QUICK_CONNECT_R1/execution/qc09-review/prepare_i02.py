"""Prepare a reviewable HTTP-status derivative, without modifying CI inputs."""
import difflib
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

HERE = Path(__file__).resolve().parent
PREFIX = Path(r'C:/Users/jpamb/AppData/Local/Temp/nexus-qc-r1-package-0s9w2_3_/venv')
SOURCE = PREFIX / 'Lib/site-packages/okto_nexus'
ROOT = Path(tempfile.mkdtemp(prefix='nexus-qc-i02-derivative-')).resolve()
PACKAGE = ROOT / 'overlay/okto_nexus'
shutil.copytree(SOURCE, PACKAGE, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
changes = []


def edit(relative, replacements):
    path = PACKAGE / relative
    before = path.read_text(encoding='utf-8')
    after = before
    for old, new in replacements:
        assert old in after, (relative, old)
        after = after.replace(old, new)
    path.write_text(after, encoding='utf-8', newline='\n')
    original = ROOT / 'before' / relative
    original.parent.mkdir(parents=True, exist_ok=True)
    original.write_text(before, encoding='utf-8', newline='\n')
    changes.extend(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
        fromfile='a/src/okto_nexus/' + relative, tofile='b/src/okto_nexus/' + relative))


edit('application/terminal_connection.py', [
    ("stage='connect', choices=None):", "stage='connect', choices=None, http_status=None):"),
    ('self.choices = choices', 'self.choices = choices\n        self.http_status = http_status'),
])
edit('adapters/outbound/terminal_http.py', [
    ('failed = False', 'failed = False\n        http_status = None'),
    ('response, failed = error, True', 'response, failed = error, True\n            http_status = error.code'),
    ("possible_effect=method != 'GET') from None\n        if failed:",
     "possible_effect=method != 'GET', http_status=http_status) from None\n        if failed:"),
    ("'The Server error response is malformed.', possible_effect=method != 'GET')",
     "'The Server error response is malformed.', possible_effect=method != 'GET', http_status=http_status)"),
    ("stage=error.get('stage', 'http'), possible_effect=error.get('possible_effect', False))",
     "stage=error.get('stage', 'http'), possible_effect=error.get('possible_effect', False), http_status=http_status)"),
])
edit('adapters/outbound/operator_client.py', [
    ('stage=error.stage) from None', 'stage=error.stage, http_status=error.http_status) from None'),
])
edit('adapters/inbound/cli/quick_connect_ids.py', [
    ("if error.code in ('NOT_FOUND', 'HTTP_ERROR', 'VALIDATION_ERROR'):",
     "if (error.http_status in (404, 405) or error.http_status is None\n                and error.code in ('NOT_FOUND', 'HTTP_ERROR', 'VALIDATION_ERROR')):"),
])
(ROOT / 'changes.patch').write_text(''.join(changes), encoding='utf-8')
pins = {p.relative_to(SOURCE).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in SOURCE.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc'}
assert len(pins) == 732, len(pins)
(ROOT / 'installed-before.json').write_text(json.dumps(pins, indent=2), encoding='utf-8')
(HERE / 'i02-allocation.json').write_text(json.dumps(dict(root=str(ROOT)), indent=2), encoding='utf-8')
print(json.dumps(dict(root=str(ROOT), files=len(pins), patch=str(ROOT / 'changes.patch'))))

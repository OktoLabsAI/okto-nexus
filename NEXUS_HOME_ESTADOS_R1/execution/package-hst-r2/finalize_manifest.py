"""Preserve PACKAGE_READY manifest and capture subsequent sanitized curation."""
import hashlib
import json
from pathlib import Path
import shutil

here = Path(__file__).resolve().parent
original = here/'manifest.json'
snapshot = here/'manifest-package-ready.json'
assert not snapshot.exists(), 'Preserve the finalized curation rather than overwriting it'
before = json.loads(original.read_text(encoding='utf-8'))
changes = {name:dict(before=pin, after=hashlib.sha256((here/name).read_bytes()).hexdigest())
    for name, pin in before.items()
    if (here/name).is_file() and hashlib.sha256((here/name).read_bytes()).hexdigest() != pin}
assert set(changes) == {'curate_delta.py'}, changes
shutil.copyfile(original, snapshot)
note = dict(package_ready_manifest_sha256=hashlib.sha256(snapshot.read_bytes()).hexdigest(),
    existing_member_changes=changes,
    reason='Comparison helper corrected its expected changed-file list from two to the three authorized Python files; initial assertion failure is recorded in delta-vs-r1.json. No package/prefix/product modification.',
    raw_auth_session_logs_copied=False,
    package_qualification_sha256=hashlib.sha256((here/'qualification.json').read_bytes()).hexdigest(),
    live_qualification_sha256=hashlib.sha256((here/'live-qualification.json').read_bytes()).hexdigest())
(here/'curation-addendum.json').write_text(json.dumps(note, indent=2)+'\n', encoding='utf-8')
manifest = {str(path.relative_to(here)).replace('\\','/'):hashlib.sha256(path.read_bytes()).hexdigest()
    for path in sorted(here.rglob('*')) if path.is_file() and path != original and '__pycache__' not in path.parts}
original.write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8')
print(json.dumps(dict(status='CURATED',files=len(manifest),manifest_sha256=hashlib.sha256(original.read_bytes()).hexdigest(),**note)))

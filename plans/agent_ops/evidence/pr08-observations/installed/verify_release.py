"""Recheck source/wheel/installed raw bytes from an immutable package proof."""
import hashlib
import json
from pathlib import Path
import sys
import zipfile

proof_path = Path(sys.argv[1]).resolve()
proof = json.loads(proof_path.read_text(encoding='utf-8'))


def digest(data):
    return hashlib.sha256(data).hexdigest()


def relevant(name):
    return (name.endswith('.py') or name.startswith('migrations/') or
            name.startswith('adapters/inbound/http/static/')) and '__pycache__' not in name


wheel = Path(proof['wheel'])
assert digest(wheel.read_bytes()) == proof['wheel_sha256']
assert digest(Path(proof['core_wheel']).read_bytes()) == proof['core_wheel_sha256']
for label, directory in [('source', Path(proof['source_root']) / 'src/okto_nexus'),
                         ('installed', Path(proof['installed_package']))]:
    paths = {p.relative_to(directory).as_posix(): p for p in directory.rglob('*')
             if p.is_file() and relevant(p.relative_to(directory).as_posix())}
    assert set(paths) == set(proof['files']), label + ' file set changed'
    for name, path in paths.items():
        assert digest(path.read_bytes()) == proof['files'][name][label + '_sha256'], (label, name)
with zipfile.ZipFile(wheel) as archive:
    names = {name[len('okto_nexus/'):] for name in archive.namelist()
             if name.startswith('okto_nexus/') and not name.endswith('/') and relevant(name[len('okto_nexus/'):])}
    assert names == set(proof['files'])
    for name in names:
        assert digest(archive.read('okto_nexus/' + name)) == proof['files'][name]['wheel_sha256'], name
print(json.dumps({'result': 'passed', 'files': len(proof['files']),
                  'proof_sha256': digest(proof_path.read_bytes()), 'wheel_sha256': proof['wheel_sha256']}))

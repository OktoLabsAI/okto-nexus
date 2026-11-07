"""Bind the closed milestone's explicit artifact tree to its raw/staged bytes."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

REPO = Path('D:/Projetos/Techridy/okto_labs_okto_nexus').resolve()
OUT = REPO / 'plans/agent_ops/evidence/pr10-correlation'
sha = lambda data: hashlib.sha256(data).hexdigest()
mode = sys.argv[1]
reports = json.loads((OUT / 'reports.json').read_text(encoding='utf-8'))
for row in reports['retained_inputs']:
    path = (REPO / row['path']).resolve()
    assert path.is_relative_to(OUT) and sha(path.read_bytes()) == row['sha256'], row['path']
browser = json.loads((OUT / 'browser/manifest.json').read_text(encoding='utf-8'))
assert sha(json.dumps(browser['entries'], sort_keys=True, separators=(',', ':')).encode()) == browser['aggregate_sha256']
for row in browser['entries']:
    path = (OUT / 'browser' / row['path']).resolve()
    assert path.is_relative_to(OUT / 'browser') and sha(path.read_bytes()) == row['sha256']
manifest_path = OUT / 'artifact-manifest.json'
if mode == 'manifest':
    assert reports['collection_phase'] == 'closed_qualified_milestone'
    assert not manifest_path.exists()
    files = []
    for path in sorted(p for p in OUT.rglob('*') if p.is_file()):
        assert path.suffix.lower() not in ('.db', '.sqlite', '.sqlite3', '.key', '.whl', '.pyc')
        assert 'private' not in path.name.lower() and not path.name.endswith(('-wal', '-shm'))
        data = path.read_bytes()
        files.append(dict(path=path.relative_to(REPO).as_posix(), bytes=len(data), sha256=sha(data)))
    manifest = dict(schema_version=1, files=files,
        files_sha256=sha(json.dumps(files, sort_keys=True, separators=(',', ':')).encode()),
        plan_sha256='20d0fafdedc793b97a277f5d41355d7d597ff724a77687394215eea3113ba996',
        scope='All files under pr10-correlation except this manifest; original candidates/failures remain separately labeled. No private database, credential registry or wheel included.')
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
elif mode in ('verify', 'staged'):
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    actual = {p.relative_to(REPO).as_posix() for p in OUT.rglob('*') if p.is_file() and p != manifest_path}
    assert actual == {row['path'] for row in manifest['files']}
    assert sha(json.dumps(manifest['files'], sort_keys=True, separators=(',', ':')).encode()) == manifest['files_sha256']
    for row in manifest['files']:
        assert sha((REPO / row['path']).read_bytes()) == row['sha256'], row['path']
    if mode == 'staged':
        rows = [*manifest['files'], dict(path=manifest_path.relative_to(REPO).as_posix(), sha256=sha(manifest_path.read_bytes()))]
        assert not any('\n' in row['path'] or '\r' in row['path'] for row in rows)
        raw = subprocess.check_output(['git', 'cat-file', '--batch'], cwd=REPO,
            input=''.join(':' + row['path'] + '\n' for row in rows).encode())
        offset = 0
        for row in rows:
            end = raw.index(b'\n', offset)
            header = raw[offset:end].split()
            assert len(header) == 3 and header[1] == b'blob', row['path']
            size = int(header[2])
            data = raw[end + 1:end + 1 + size]
            assert len(data) == size and sha(data) == row['sha256'], row['path']
            offset = end + 2 + size
        assert offset == len(raw)
elif mode == 'preflight':
    manifest = None
else:
    raise ValueError('Unknown mode')
print(json.dumps(dict(mode=mode, retained_inputs=len(reports['retained_inputs']),
    browser_entries=len(browser['entries']), artifact_files=len(manifest['files']) if manifest else None,
    aggregate_sha256=manifest['files_sha256'] if manifest else None), indent=2))

"""Verify retained evidence and optionally bind its exact bytes to the Git index."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile

REPO = Path('D:/Projetos/Techridy/okto_labs_okto_nexus').resolve()
OUT = REPO / 'plans/agent_ops/evidence/pr10-external'
MODE = sys.argv[1]
sha = lambda data: hashlib.sha256(data).hexdigest()


def verify(relative, expected, base=REPO):
    target = (base / relative).resolve()
    assert target.is_relative_to(REPO) and target.is_file(), relative
    assert sha(target.read_bytes()) == expected, relative


reports = json.loads((OUT / 'reports.json').read_text(encoding='utf-8'))
for row in reports['retained_inputs']:
    verify(row['path'], row['sha256'])
browser = json.loads((OUT / 'browser/browser-results.json').read_text(encoding='utf-8'))
for row in browser['retained_inputs']:
    verify(row['path'], row['sha256'], OUT / 'browser')
with zipfile.ZipFile(OUT / 'browser/playwright-trace.zip') as archive:
    assert archive.testzip() is None
    assert set(archive.namelist()) == {row['path'] for row in browser['trace_entries']}
    for row in browser['trace_entries']:
        assert sha(archive.read(row['path'])) == row['sha256'], row['path']
    network = archive.read('trace-1794019020953.network').decode('utf-8')
    requests = [json.loads(line)['snapshot']['request'] for line in network.splitlines()]
    assert len(requests) == 1077
    assert not any(h['name'].lower() in ('authorization', 'proxy-authorization', 'cookie')
                   for request in requests for h in request['headers'])

manifest_path = OUT / 'artifact-manifest.json'
if MODE == 'manifest':
    assert reports['collection_phase'] == 'closed_qualified_milestone'
    assert not manifest_path.exists()
    files = []
    for path in sorted(p for p in OUT.rglob('*') if p.is_file()):
        assert path.suffix.lower() not in ('.db', '.sqlite', '.sqlite3', '.key', '.whl', '.pyc')
        assert 'private' not in path.name.lower() and not path.name.endswith(('-wal', '-shm'))
        data = path.read_bytes()
        files.append(dict(path=path.relative_to(REPO).as_posix(), bytes=len(data), sha256=sha(data)))
    aggregate = sha(json.dumps(files, sort_keys=True, separators=(',', ':')).encode('utf-8'))
    result = dict(schema_version=1, files=files, files_sha256=aggregate,
        archive_scope='All files under pr10-external except this manifest; retired candidates retained and labeled. No database, private credential file or wheel is included.',
        browser_trace_entries=len(browser['trace_entries']), browser_credential_header_requests=0,
        plan_sha256='20d0fafdedc793b97a277f5d41355d7d597ff724a77687394215eea3113ba996')
    manifest_path.write_text(json.dumps(result, indent=2), encoding='utf-8')
elif MODE in ('verify', 'staged'):
    result = json.loads(manifest_path.read_text(encoding='utf-8'))
    for row in result['files']:
        verify(row['path'], row['sha256'])
    actual = {p.relative_to(REPO).as_posix() for p in OUT.rglob('*') if p.is_file() and p != manifest_path}
    assert actual == {row['path'] for row in result['files']}
    assert sha(json.dumps(result['files'], sort_keys=True, separators=(',', ':')).encode()) == result['files_sha256']
    if MODE == 'staged':
        rows = [*result['files'], dict(path=manifest_path.relative_to(REPO).as_posix(), sha256=sha(manifest_path.read_bytes()))]
        names = [row['path'] for row in rows]
        assert not any('\n' in name or '\r' in name for name in names)
        output = subprocess.check_output(['git', 'cat-file', '--batch'], cwd=REPO,
            input=''.join(':' + name + '\n' for name in names).encode())
        offset = 0
        for row in rows:
            end = output.index(b'\n', offset)
            header = output[offset:end].split()
            assert len(header) == 3 and header[1] == b'blob', row['path']
            size = int(header[2])
            data = output[end + 1:end + 1 + size]
            assert len(data) == size and sha(data) == row['sha256'], row['path']
            offset = end + 2 + size
        assert offset == len(output)
elif MODE == 'preflight':
    result = None
else:
    raise ValueError('Unknown verification mode')
print(json.dumps(dict(mode=MODE, retained_inputs=len(reports['retained_inputs']),
    trace_entries=len(browser['trace_entries']),
    artifact_files=len(result['files']) if result else None,
    aggregate_sha256=result['files_sha256'] if result else None)))

"""Pin raw artifacts and optionally compare their staged Git blobs."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(r'D:/Projetos/Techridy/okto_labs_okto_nexus')
folders = [(ROOT, 'plans/agent_ops/evidence/pr03-remote-renewal'),
    (ROOT.parent / 'okto-nexus-connector', 'docs/evidence/remote-rotation')]
verify = '--verify-staged' in sys.argv
for repo, folder in folders:
    directory = repo / folder
    files = {p.relative_to(directory).as_posix(): dict(size=p.stat().st_size,
        sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in sorted(directory.rglob('*'))
        if p.is_file() and p.name != 'artifact-manifest.json'}
    aggregate = hashlib.sha256(json.dumps(files, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    path = directory / 'artifact-manifest.json'
    if verify:
        manifest = json.loads(path.read_text())
        assert manifest['files'] == files and manifest['aggregate_sha256'] == aggregate
        for name in [*files, 'artifact-manifest.json']:
            relative = folder + '/' + name
            staged = subprocess.check_output(['git', 'show', ':' + relative], cwd=repo)
            assert staged == (directory / name).read_bytes(), relative
    else:
        path.write_text(json.dumps(dict(format=1, file_count=len(files), aggregate_sha256=aggregate,
            algorithm='sha256 of canonical JSON files map (sort_keys,compact separators)', files=files), indent=2), encoding='utf-8')
    print(json.dumps(dict(repository=str(repo), count=len(files), aggregate_sha256=aggregate, staged_verified=verify)))

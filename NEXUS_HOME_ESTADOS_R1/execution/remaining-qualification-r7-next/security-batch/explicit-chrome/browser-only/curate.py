"""Sanitized diagnostic curation only; raw debug/error logs remain ownTemp."""
import argparse
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
parser=argparse.ArgumentParser()
parser.add_argument('--root',type=Path,required=True)
args=parser.parse_args()
root=args.root.resolve()
assert root.name.startswith('nexus-hst-browser-diagnostic-')
data=json.loads((root/'browser-only-private.json').read_text())
assert Path(data['root']).resolve()==root
output=HERE/'runs'/data['cut_id']
assert not output.exists()
output.mkdir(parents=True)
public=dict(data)
public['failure_type']=data['failure']['type'] if data['failure'] else None
public.pop('failure')
public['raw_debug_copied']=False
public['raw_logs_location']=str(root)
(output/'qualification.json').write_text(json.dumps(public,indent=2)+'\n')
files=[path for path in root.rglob('*') if path.is_file() and 'browser-profile' not in path.parts]
hashes={path.relative_to(root).as_posix():{'bytes':path.stat().st_size,
    'sha256':hashlib.sha256(path.read_bytes()).hexdigest()} for path in files}
(output/'raw-hashes.json').write_text(json.dumps(hashes,indent=2)+'\n')
manifest={path.name:hashlib.sha256(path.read_bytes()).hexdigest() for path in output.iterdir() if path.is_file()}
(output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({'status':data['status'],'output':str(output),
    'qualification_sha256':hashlib.sha256((output/'qualification.json').read_bytes()).hexdigest(),
    'raw_debug_copied':False}))

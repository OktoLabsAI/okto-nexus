"""Append instrumental proof after the unchanged allowlisted base curator."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

HERE=Path(__file__).resolve().parent
BASE=HERE.parent

parser=argparse.ArgumentParser()
parser.add_argument('--root',type=Path,required=True)
args=parser.parse_args()
root=args.root.resolve()
assert root.name.startswith('nexus-hst-browser-')
data=json.loads((root/'security-run.private.json').read_text())
result=subprocess.run(['rtk','proxy',sys.executable,'-B',str(BASE/'curate.py'),'--root',str(root)],
    input=b'',capture_output=True,timeout=40,check=True)
out=BASE/'runs'/data['cut_id']
proof=data.get('instrumentation',{})
assert proof and proof['before']['cut_id']==data['cut_id']
qualification=json.loads((out/'qualification.json').read_text())
if qualification['status']=='PASS_SCOPED':
    assert proof['after'] is not None and proof['after']['unchanged'] is True
public={'status':'INSTRUMENTATION_UNCHANGED' if proof['after'] else 'INSTRUMENTATION_INCOMPLETE',
        'proof':proof,'base_qualification_sha256':hashlib.sha256((out/'qualification.json').read_bytes()).hexdigest(),
        'base_cut_reclassified':False,'personal_profile_used':False,
        'personal_environment_restored':False,'browser_installed':False}
target=out/'explicit-browser-instrumentation.json'
assert not target.exists()
target.write_text(json.dumps(public,indent=2)+'\n')
manifest={path.name:hashlib.sha256(path.read_bytes()).hexdigest() for path in out.iterdir()
          if path.is_file() and path.name not in {'manifest.json','instrumentation-manifest.json'}}
(out/'instrumentation-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(result.stdout.decode())
print(json.dumps({'instrumentation':str(target),'sha256':hashlib.sha256(target.read_bytes()).hexdigest()}))

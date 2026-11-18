"""Preserve base curation and add independently gated comment-template proof."""
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
child=subprocess.run(['rtk','proxy',sys.executable,'-B',str(BASE/'curate.py'),'--root',str(root)],
    input=b'',capture_output=True,timeout=40,check=True)
directory=BASE/'runs'/data['cut_id']
qualified=json.loads((directory/'qualification.json').read_text())
proof=json.loads((root/'comment-variant-after.json').read_text())
output={'status':qualified['status'] if proof['unchanged'] else 'FAIL_OR_INCONCLUSIVE_PRESERVED',
        'comment_template_proof':proof,'base_qualification_sha256':hashlib.sha256((directory/'qualification.json').read_bytes()).hexdigest(),
        'original_failed_cut_reclassified':False,'assertions_changed':False,'product_changed':False,
        'raw_logs_copied':False}
target=directory/'comment-template-qualification.json'
assert not target.exists()
target.write_text(json.dumps(output,indent=2)+'\n')
manifest={path.name:hashlib.sha256(path.read_bytes()).hexdigest() for path in directory.iterdir()
          if path.is_file() and path.name not in {'manifest.json','comment-manifest.json'}}
(directory/'comment-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(child.stdout.decode())
print(json.dumps({'status':output['status'],'comment_qualification_sha256':hashlib.sha256(target.read_bytes()).hexdigest()}))

"""Bind the one pre-runtime reader/stack/comment counterpart; no process startup."""
import ast
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent;REPO=HERE.parents[3]
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
assert sha(HERE/'prepared-app.json')=='9b9194dcd72da07d7a274b39e52b45981f97ebbfb144c95ee5dd59d03ad7dbb6'
manifest=json.loads((HERE/'prepared-app.json').read_text())
for name in ['run_v2.py','curate_v2.py','prepare_variant_v2.py','bind_variant_v2.py']:ast.parse((HERE/name).read_text())
for name in ['run_v2.py','curate_v2.py','app-display-v2.js','prepare_variant_v2.py','bind_variant_v2.py','variant-v2.diff','prepared-app.json']:
    manifest['input_pins'][str((HERE/name).relative_to(REPO)).replace('\\','/')]=sha(HERE/name)
manifest['status']='I05_APP_READER_STACK_COMMENTS_COUNTERPART_PREPARED_NOT_EXECUTED'
manifest['counterpart_changes']=['Same-deadline missing/incomplete control JSON observation audited by size/hash, no extra marker or admission','Stack y must be at/after previous bottom and x aligned within1CSSpx','Correct inherited browser-only comments; curator includes control-read audit']
path=HERE/'prepared-app-v2.json';assert not path.exists();path.write_text(json.dumps(manifest,indent=2)+'\n')
gate=json.loads((HERE/'GATE.template.json').read_text());assert gate['approved']is False;gate['manifest_sha256']=sha(path)
(HERE/'GATE-v2.template.json').write_text(json.dumps(gate,indent=2)+'\n')
print(json.dumps(dict(status='PREPARED_NOT_EXECUTED',manifest_sha256=sha(path),input_files=len(manifest['input_pins']),files={name:sha(HERE/name)for name in ['run_v2.py','app-display-v2.js','curate_v2.py']}),indent=2))

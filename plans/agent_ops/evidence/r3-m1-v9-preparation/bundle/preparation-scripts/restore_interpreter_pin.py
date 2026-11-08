"""Restore the v8 interpreter gate in v9 proposal data. No campaign effect."""
from pathlib import Path
import hashlib
import json

ROOT=Path(__file__).parent
D=ROOT/'draft'
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,value): Path(path).write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
p_path=D/'m1-codex-campaign-proposal-v9.json'
assert sha(p_path)=='0a2fe640c690da3b9fc565c4a3e247df3ce26f2b6ba4b52a51aad33fad739419'
p=json.loads(p_path.read_text())
old=json.loads((D/'history/v8-proposal.json').read_text())
old_python=[x for x in old['package_pins']['files'] if Path(x['path']).name.lower()=='python.exe']
assert len(old['package_pins']['files'])==983 and len(old_python)==1
python=Path(p['package_pins']['python'])
probe=json.loads((D/'installation/direct-interpreter-final.json').read_text())
expected='cd15f17b5382c676fe857fd9e7effe0b787f95611538f4193c60a65f2637dd79'
assert sha(python)==probe['venv_python_sha256']==old_python[0]['sha256']==expected
assert len(p['package_pins']['files'])==982
assert all(Path(x['path'])!=python for x in p['package_pins']['files'])
p['package_pins']['files'].append({'path':str(python),'sha256':expected})
p['package_pins']['pin_count_semantics']={'product_payload_files':982,'venv_interpreter_files':1,'total_entries':983}
p['completed_preparation_checks']['venv_interpreter_pin']={'sha256':expected,'scope':'Restored exact v8 gate: all campaign commands recheck this executable in addition to the installer precheck.'}
write(p_path,p)
pin_doc=json.loads((D/'prospective-package-pins.json').read_text())
pin_doc['interpreter_pin']={'path':str(python),'sha256':expected}
pin_doc['total_gate_entries']=983
write(D/'prospective-package-pins.json',pin_doc)
write(D/'interpreter-pin-correction.json',{
 'status':'RESTORED_V8_CONTRACT','previous_v9_proposal_sha256':'0a2fe640c690da3b9fc565c4a3e247df3ce26f2b6ba4b52a51aad33fad739419',
 'proposal_sha256':sha(p_path),'v8_entries':983,'previous_v9_entries':982,'corrected_v9_entries':983,
 'product_payloads':982,'interpreter_sha256':expected,
 'defect':'The v9 builder omitted the extra venv interpreter pin from package_pins.files. The installer check was intact, but the per-command gate had lost this entry.',
 'correction':'Append the exact owned venv Python hash to the same list consumed by the unchanged campaign_context gate.',
 'functional_code_changed':False,'campaign_or_installation_executed':False,
 'old_public_preserved':str(ROOT/'public'),
 'old_manifest_sha256':sha(ROOT/'public/artifact-manifest.json')})
print(json.dumps({'proposal_sha256':sha(p_path),'pin_entries':983,'product_payloads':982}))

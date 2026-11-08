"""Read-only evidence of the frozen requirements newline defect."""
import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile

ROOT=Path(__file__).parent
FROZEN=ROOT/'public-revision-2'
LIVE=ROOT/'draft/installation'
OUT=Path(tempfile.mkdtemp(prefix='m1-v9-requirements-diagnosis-'))
def sha(raw): return hashlib.sha256(raw).hexdigest()
def write(path,value): Path(path).write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')

proposal_raw=(FROZEN/'m1-codex-campaign-proposal-v9.json').read_bytes()
assert sha(proposal_raw)=='9a7004d1670076fd516311932bb894fbd55e47e2625fb6b3dfd89dc66caed279'
proposal=json.loads(proposal_raw)
source_raw=(FROZEN/'installation/timed_install.py').read_bytes()
source=source_raw.decode()
tree=ast.parse(source)
wheels=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign)
    and len(n.targets)==1 and isinstance(n.targets[0],ast.Name) and n.targets[0].id=='WHEELS')
actual=(FROZEN/'installation/products-requirements.txt').read_bytes()
expected=''.join(Path(pin['wheel']).as_uri()+' --hash=sha256:'+pin['sha256']+'\n' for pin in wheels.values()).encode()
assert actual.replace(b'\r\n',b'\n')==expected
assert actual.count(b'\r\n')==3 and len(actual)-len(expected)==3
assert sha(actual)==proposal['base06_installation']['requirements_sha256']
old_v8=Path('C:/Users/jpamb/AppData/Local/Temp/m1-base06-install-g9ii2zhe/products-requirements.txt').read_bytes()
assert old_v8.count(b'\r\n')==0 and old_v8.count(b'\n')==3
functions={n.name:n for n in tree.body if isinstance(n,ast.FunctionDef)}
install=functions['install']
calls=[(n.lineno,ast.unparse(n.func)) for n in ast.walk(install) if isinstance(n,ast.Call)]
first_verify=min(line for line,name in calls if name=='verify_wheels')
reserve=min(line for line,name in calls if name=='write_exclusive')
first_run=min(line for line,name in calls if name=='run_process')
assert first_verify < reserve < first_run
outcome={name:(LIVE/name).exists() for name in ('installation-reserved.json','installation-result.json','installation-unknown.json')}
products={name:(LIVE/'venv/Lib/site-packages'/name).exists() for name in ('okto_nexus','okto_nexus_connector','nexus_connector_core')}
(OUT/'frozen-authorized-requirements-crlf.txt').write_bytes(actual)
(OUT/'expected-requirements-lf.txt').write_bytes(expected)
for name in ('verify_wheels','install','main'):
    (OUT/(name+'-source.txt')).write_text(ast.get_source_segment(source,functions[name]),encoding='utf-8')
report={
 'status':'CONFIRMED_PREPARATION_NEWLINE_DEFECT',
 'observed_at_utc':datetime.now(timezone.utc).isoformat(),
 'original_proposal_sha256':sha(proposal_raw),'installer_sha256':sha(source_raw),
 'actual':{'bytes':len(actual),'sha256':sha(actual),'CRLF':actual.count(b'\r\n'),'matches_authorized_pin':True},
 'expected':{'bytes':len(expected),'sha256':sha(expected),'LF':expected.count(b'\n')},
 'only_change_needed':'Three CRLF pairs become LF; all wheel URLs, order and SHA256 pins identical.',
 'v8_requirements':{'sha256':sha(old_v8),'CRLF':0,'LF':3},
 'live_readonly_observation':{'reservation_result_unknown_exists':outcome,'product_directories_exist':products},
 'source_order':{'verify_wheels_line':first_verify,'exclusive_reservation_line':reserve,'first_pip_run_process_line':first_run},
 'effect_boundary':'REQUIREMENTS_CHANGED is raised before the exclusive installation reservation and before any run_process. Both paths execute=false and execute=true share this gate. The observed refusal plus absent reservation/product artifacts does not represent an installation attempt consuming the one-install slot.',
 'root_cause':'bind_candidate.py wrote requirements using Path.write_text on Windows, producing CRLF. verify_wheels compares exact UTF-8 bytes generated with LF. Frozen metadata consistently pinned the wrong representation, so isolated mocked gates missed this composition defect.',
 'minimum_correction':'Preserve original snapshot/receipt and write exact expected UTF-8 bytes via write_bytes (or newline=LF). Rebind only requirements/proposal-derived hashes in an explicit audit derivation. Keep verify_wheels strict, all wheels/argv/prefix/policy and one-install reservation unchanged. Root owns the authorization-scope decision.',
 'required_regression_before_effect':[
   'Invoke canonical timed_install.py --validate-only with the real corrected proposal and derived approval documents and their exact external hashes; no mocks or weakened validators.',
   'Require VALIDATED_NO_INSTALL exit0 using actual wheel hashes, dependency manifest, Python prefix/hash proof and exact requirements bytes.',
   'Verify reservation/result/unknown remain absent and all three product directories remain absent after validation.',
   'Only after successful real composition validation may root invoke the same single authorized installation effect; any reserved/unknown state must retain the no-replay rule.'
 ],
 'diagnostic_actions':{'product_install':False,'native_or_provider':False,'service':False,'credential':False,'authorized_original_mutated':False,'receipt_mutated':False},
 'scope_limit':'This diagnostic did not execute validation with corrected documents or installation; those belong to root.'
}
write(OUT/'diagnosis.json',report)
(OUT/'diagnose_requirements.py').write_bytes(Path(__file__).read_bytes())
files={p.name:{'sha256':sha(p.read_bytes()),'bytes':p.stat().st_size} for p in OUT.iterdir() if p.is_file()}
write(OUT/'artifact-manifest.json',{'files':files,'scope':'Finite public read-only diagnostic; no secrets or campaign data.'})
print(json.dumps({'directory':str(OUT),'diagnosis_sha256':sha((OUT/'diagnosis.json').read_bytes()),
 'manifest_sha256':sha((OUT/'artifact-manifest.json').read_bytes()),'payloads':len(files),
 'reservation_result_unknown_exists':outcome,'product_directories_exist':products}))

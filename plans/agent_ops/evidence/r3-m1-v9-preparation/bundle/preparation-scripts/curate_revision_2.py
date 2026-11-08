"""Allowlisted correction; preserve the first public snapshot byte-for-byte."""
from pathlib import Path
import hashlib
import json

ROOT=Path(__file__).parent
D=ROOT/'draft'
OLD=ROOT/'public'
OUT=ROOT/'public-revision-2'
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,v): Path(p).write_text(json.dumps(v,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
assert not OUT.exists()
assert sha(OLD/'artifact-manifest.json')=='3e1c78866ff22bf3fa9002e7cd65cd3037ea765afb32cf714e6a17db51b48f98'
old_manifest=json.loads((OLD/'artifact-manifest.json').read_text())
for name,entry in old_manifest['files'].items(): assert sha(OLD/name)==entry['sha256']
assert sha(D/'m1-codex-campaign-proposal-v9.json')=='9a7004d1670076fd516311932bb894fbd55e47e2625fb6b3dfd89dc66caed279'
result=json.loads((D/'interpreter-pin-check-execution.json').read_text())
assert result['status']=='PASS' and result['inputs_unchanged']
for name,digest in result['input_hashes_after'].items(): assert sha(D/name)==digest
p=json.loads((D/'m1-codex-campaign-proposal-v9.json').read_text())
assert len(p['package_pins']['files'])==983
assert p['base06_installation']['expected_payload_count']==982
for entry in p['execution_bundle']['files'].values(): assert sha(entry['path'])==entry['sha256']
assert not (ROOT/'campaign').exists() and not p['execution_authorized']

qualification=json.loads((OLD/'qualification.json').read_text())
qualification['proposal_sha256']=sha(D/'m1-codex-campaign-proposal-v9.json')
qualification['preparation_revision']=2
qualification['unique_pin_regression_cases']=1
qualification['total_package_gate_entries']=983
qualification['counting']='51 unique pytest cases, one focused pure interpreter-pin regression and 12 distinct entry denials. Repetitions are not added as unique cases.'
qualification['previous_proposal_sha256']='0a2fe640c690da3b9fc565c4a3e247df3ce26f2b6ba4b52a51aad33fad739419'
qualification['previous_proposal_status']='REJECTED_BEFORE_AUTHORIZATION_INTERPRETER_PIN_OMISSION'
qualification['correction_scope']='Only proposal pin data and public reporting changed. Controller/installer/wrappers identical; one changed-interpreter regression plus 12 entry-denial repeats PASS on final proposal.'
qualification['final_pin_gate_result_sha256']=sha(D/'interpreter-pin-gates.json')
write(D/'qualification.json',qualification)
checks=json.loads((D/'preparation-checks.json').read_text())
checks.update(preparation_revision=2,unique_pin_regression_cases=1,package_gate_entries=983,
              pin_regression='PASS_PRODUCT_PIN_CHANGED_BEFORE_DISPATCH',
              final_proposal_sha256=sha(D/'m1-codex-campaign-proposal-v9.json'))
write(D/'preparation-checks.json',checks)
OUT.mkdir()
overrides={'README.md','m1-codex-campaign-proposal-v9.json','prospective-package-pins.json',
           'guard-result.json','qualification.json','preparation-checks.json'}
for name in old_manifest['files']:
    source=D/name if name in overrides else OLD/name
    target=OUT/name
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_bytes(source.read_bytes())
for name in ('interpreter-pin-correction.json','check_restored_python_pin.py','interpreter-pin-gates.json',
             'interpreter-pin-gates.stdout.txt','interpreter-pin-gates.stderr.txt','interpreter-pin-check-execution.json'):
    (OUT/name).write_bytes((D/name).read_bytes())
for name in ('restore_interpreter_pin.py','execute_pin_check.py','curate_revision_2.py'):
    (OUT/'preparation-scripts'/name).write_bytes((ROOT/name).read_bytes())
(OUT/'history/prior-v9-proposal.json').write_bytes((OLD/'m1-codex-campaign-proposal-v9.json').read_bytes())
(OUT/'history/prior-v9-manifest.json').write_bytes((OLD/'artifact-manifest.json').read_bytes())
write(OUT/'history/prior-v9-notice.json',{
 'status':'REJECTED_BEFORE_AUTHORIZATION','reason':'Missing venv Python pin in package_pins.files; restored in preparation revision2.',
 'original_public_directory':str(OLD),'original_manifest_sha256':sha(OLD/'artifact-manifest.json'),
 'original_files_preserved':72,'campaign_or_installation_executed':False})
files={f.relative_to(OUT).as_posix():{'sha256':sha(f),'bytes':f.stat().st_size} for f in sorted(OUT.rglob('*')) if f.is_file()}
write(OUT/'artifact-manifest.json',{'status':'PUBLIC_FINITE_ALLOWLIST','preparation_revision':2,'files':files,
 'excluded':old_manifest['excluded']+['pin-regression-synthetic-only'],
 'scope':'Preparation only. Original v8 and previous v9 snapshots preserved. This revision restores the exact executable pin, with no campaign effect.'})
print(json.dumps({'public':str(OUT),'payloads':len(files),'manifest_sha256':sha(OUT/'artifact-manifest.json'),
 'proposal_sha256':sha(D/'m1-codex-campaign-proposal-v9.json')}))

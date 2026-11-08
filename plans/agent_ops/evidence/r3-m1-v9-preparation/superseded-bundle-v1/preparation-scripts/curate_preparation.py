"""Finite public allowlist only. No campaign data, venv, homes or credentials."""
import ast
import hashlib
import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET

ROOT=Path(__file__).parent
D=ROOT/'draft'
OUT=ROOT/'public'
assert not OUT.exists()
assert not (ROOT/'campaign').exists()
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,v): Path(p).write_text(json.dumps(v,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')

proposal=D/'m1-codex-campaign-proposal-v9.json'
p=json.loads(proposal.read_text())
assert sha(proposal)=='0a2fe640c690da3b9fc565c4a3e247df3ce26f2b6ba4b52a51aad33fad739419'
assert not p['execution_authorized'] and not p['controller_preparation']['approval_receipt_created']
final=json.loads((D/'final-gates-result.json').read_text())
initial=json.loads((D/'pure-tests-result.json').read_text())
assert final['status']==initial['status']=='PASS'
assert final['input_hashes_after']['m1-codex-campaign-proposal-v9.json']==sha(proposal)
for name,digest in final['input_hashes_after'].items(): assert sha(D/name)==digest
for entry in p['execution_bundle']['files'].values(): assert sha(entry['path'])==entry['sha256']
for entry in p['package_pins']['packages'].values(): assert not Path(entry['package']).exists()

sources=json.loads((D/'source-map.json').read_text())
for name,entry in sources.items():
    entry['sha256']=sha(D/name)
    assert sha(entry['source'])==entry['source_sha256']
    if entry['reuse']=='byte_identical': assert entry['sha256']==entry['source_sha256']
sources['installation/timed_install.py']={
    'source':'C:/Users/jpamb/AppData/Local/Temp/m1-base06-install-g9ii2zhe/timed_install.py',
    'source_sha256':sha('C:/Users/jpamb/AppData/Local/Temp/m1-base06-install-g9ii2zhe/timed_install.py'),
    'sha256':sha(D/'installation/timed_install.py'),
    'reuse':'new_target_v9_policy_ancestry_exact_wheels_count_and_approval_revision'}
write(D/'source-map.json',sources)
checks=json.loads((D/'preparation-checks.json').read_text())
checks.update(status='PASS_FINITE_PREPARATION_NOT_CAMPAIGN', tests_executed=51,
    unique_controller_cases=24,unique_installer_cases=27,entry_denials=12,
    final_installer_repeat=27, final_entry_repeat=12,
    qualification_scope='Pure transports and admission/installer gates; no product installation, provider/native/service or credential API.',
    inputs_unchanged=True, actual_v9_authorization=False)
write(D/'preparation-checks.json',checks)
delta=json.loads((D/'delta-map.json').read_text())
delta['must_qualify']=[]
delta['remaining_before_effects']=['Root final review and exact tasks/root/port inspection',
    'New explicit approval bound to final proposal SHA',
    'Repeat immediate preflight, perform approved timed product installation once and validate its receipt']
write(D/'delta-map.json',delta)
candidate=json.loads((D/'prospective-package-pins.json').read_text())
candidate['status']='QUALIFIED_ARTIFACTS_TARGET_INSTALLATION_NOT_EXECUTED'
candidate['root_qualification_pending']=False
candidate['qualification_sha256']='c524b04c21c9a9f0b2b3f0ff03ecf1410802bc368221732d322b8046fb0f36db'
write(D/'prospective-package-pins.json',candidate)
write(D/'preparation-incidents.json',{
    'incidents':[
        {'id':'collection-1','scope':'pure tests only','result':'Core fixture import failed because products correctly absent',
         'retained':'checks-attempt-1/','correction':'Pinned Core wheel zipimport for pure event translation only',
         'products_installed':False,'campaign_effects':0},
        {'id':'shell-edit-not-applied','scope':'preparation test helper edit',
         'error_type':'PowerShell ParserError','effects':0,
         'detail':'An optional command to remove an idempotent test monkeypatch did not parse. No file was changed by that command. Final tests retain FINAL_PINS_BOUND=True fixture assignment, equal to the actual qualified module constant; actual module bytes are pinned in the final report.'}
    ], 'native_retries':0,'campaign_runs':0})
controller_nodes=[]
installer_nodes=[]
for node in ET.parse(D/'pure-tests.xml').iter('testcase'):
    (controller_nodes if 'test_v9' in node.attrib.get('classname','') else installer_nodes).append(node.attrib['name'])
assert len(controller_nodes)==24 and len(installer_nodes)==27
write(D/'qualification.json',{
    'status':'PASS_PREPARATION_ONLY_NOT_AUTHORIZED',
    'proposal_sha256':sha(proposal),
    'unique_pure_cases':51,'controller_cases':controller_nodes,'installer_cases':installer_nodes,
    'entry_denials':12,'final_installer_repeat':27,'final_entry_repeat':12,
    'counting':'51 unique pytest cases plus 12 distinct entry denials; repeats are not added as unique cases.',
    'dependencies_verified':3209,'prospective_product_payloads':982,
    'products_installed':False,'campaign_root_created':False,
    'live_task_or_port_preflight_performed_by_this_agent':False,
    'controller_sha256':sha(D/'controller/controller.py'),
    'installer_sha256':sha(D/'installation/timed_install.py'),
    'prior_faults_preserved':True,'carry_in_reservations':3,'carry_in_observed_tokens':45843,
    'max_new_reservations':6,'max_cumulative_reservations':9,
    'historical_confirmed_productive':2,'predecessor_uncertain_reserved_slot':1,
    'max_confirmed_productive_if_all_new_confirm':8,
    'preventive_cumulative_observed_tokens':200000,'tolerance':700000,'serial_deadline_seconds':120,
    'no_final_billing_or_atomic_cap_claim':True,
    'limits':['Pure controller test loads exact ConnectionError class AST and pure Core translation from the pinned wheel; not installed integration.',
              'No v9 service/provider/native/runtime campaign has executed.',
              'Old v8 was closed normally and is not resumed or reset.',
              'Task/port/root checks must be performed again immediately before future authorized effects.',
              'Product qualification is separately retained in root milestone44c38254; it is not a v9 campaign.']})

allowlist=[
 'README.md','m1-codex-campaign-proposal-v9.json','proposed-commands.json','planning-commands.json',
 'campaign_context.py','m1_v9_lifecycle.py','m1_v9_setup.py','m1_v9_work.py','m1_v9_remote_setup.py',
 'supervisor_check.py','publication.py','response_loss.py','test_entry_guards.py',
 'run_pure_checks.py','run_final_gates.py','class-only-dependency.json',
 'source-map.json','delta-map.json','identity-preparation.json','initial-static-checks.json',
 'preparation-checks.json','preparation-incidents.json','prospective-package-pins.json',
 'reference-payload-proof.json','qualification.json',
 'pure-tests-result.json','pure-tests.xml','pure-tests.stdout.txt','pure-tests.stderr.txt',
 'guard-result.json','final-gates-result.json','final-gates.xml','final-gates.stdout.txt','final-gates.stderr.txt',
 'controller/controller.py','controller/token_collector.py','controller/setup_journal.py',
 'controller/controller.diff','controller/canonical_fixture.py','controller/test_v9.py',
 'installation/timed_install.py','installation/test_timed_install.py','installation/prepare_dependencies.py',
 'installation/probe_direct_interpreter.py','installation/products-requirements.txt',
 'installation/dependency-manifest.json','installation/dependency-preparation.json',
 'installation/dependency-probe.stdout.txt','installation/dependency-probe.stderr.txt',
 'installation/direct-interpreter-final.json','installation/direct-interpreter-final.stdout.txt','installation/direct-interpreter-final.stderr.txt',
 'history/v8-proposal.json','history/v8-closure.json','history/v8-qualification.json',
 'checks-attempt-1/pure-tests.stdout.txt','checks-attempt-1/pure-tests.stderr.txt',
 'checks-attempt-1/pure-tests.xml','checks-attempt-1/pure-tests-result.json',
 'checks-attempt-1/guard-result.json','checks-attempt-1/class-only-dependency.json',
 'checks-attempt-1/run_pure_checks.py','checks-attempt-1/test_entry_guards.py',
]
OUT.mkdir()
for relative in allowlist:
    source=D/relative
    target=OUT/relative
    assert source.is_file()
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_bytes(source.read_bytes())
for name in ('build_preparation.py','refine_draft.py','bind_candidate.py','prepare_checks.py',
             'execute_checks.py','finalize_preparation.py','execute_final_gates.py','curate_preparation.py'):
    target=OUT/'preparation-scripts'/name
    target.parent.mkdir(exist_ok=True)
    target.write_bytes((ROOT/name).read_bytes())
qualification=Path('D:/Projetos/Techridy/okto_labs_okto_nexus/plans/agent_ops/evidence/r3-m1-check-recovery/qualification.json')
(OUT/'history/nexus-check-recovery-qualification.json').write_bytes(qualification.read_bytes())
files={f.relative_to(OUT).as_posix():{'sha256':sha(f),'bytes':f.stat().st_size}
       for f in sorted(OUT.rglob('*')) if f.is_file()}
write(OUT/'artifact-manifest.json',{
    'status':'PUBLIC_FINITE_ALLOWLIST', 'files':files,
    'excluded':['venv','isolated environments','synthetic-test-homes','actual approval receipts',
                'campaign homes/state','databases','provider configuration','credentials'],
    'scope':'Preparation only. Original v8 artifacts/checkpoint untouched. Public history and first collection failure retained.'})
print(json.dumps({'public':str(OUT),'payloads':len(files),
    'manifest_sha256':sha(OUT/'artifact-manifest.json'),'proposal_sha256':sha(proposal)}))

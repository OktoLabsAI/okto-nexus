"""Finite public evidence copies/projections, no private state or event bodies."""
from pathlib import Path
import hashlib,json,re,tempfile
H=Path(__file__).resolve().parent
W=Path('C:/Users/jpamb/AppData/Local/Temp/m1-v12-bundle-bldo9qy7/successor14/work-revision15')
D=Path('C:/Users/jpamb/AppData/Local/Temp/r3-w15-native-decision-diagnosis-w1hv7idf')
OUT=Path(tempfile.mkdtemp(prefix='m1-v15-execution-curation-'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_bytes())
def pin(p):return {'path':str(p),'sha256':sha(p)}
files=[]
def copy(p,relative,expected=None):
    p=Path(p);data=p.read_bytes();digest=hashlib.sha256(data).hexdigest()
    assert expected is None or digest==expected
    q=OUT/relative;q.parent.mkdir(parents=True,exist_ok=True)
    with q.open('xb') as f:f.write(data)
    assert sha(q)==digest
    files.append({'relative_path':relative,'source':str(p),'sha256':digest,'bytes':len(data)})
def generated(relative,value):
    q=OUT/relative;q.parent.mkdir(parents=True,exist_ok=True)
    with q.open('x',encoding='utf-8',newline='\n') as f:json.dump(value,f,indent=2,ensure_ascii=False);f.write('\n')
    files.append({'relative_path':relative,'sha256':sha(q),'bytes':q.stat().st_size,'source':'CURATED_PROJECTION'})
account=read(H/'accounting-reconciliation.json')
assert sha(W/'private/controller.json')==account['original_checkpoint']['sha256']
assert sha(W/'public/closure.json')==account['original_closure']['sha256']
assert account['cumulative_observed_tokens']==341276 and account['charged_reservations']==13
for name in ('lifecycle-nexus-install-result.json','lifecycle-nexus-start-result.json','lifecycle-nexus-stop-result.json',
             'lifecycle-nexus-uninstall-result.json','nexus-owner-selection.json','nexus-exit-proof.json',
             'cleanup-nexus.json','final-presence.json','closure.json'):
    copy(W/'public'/name,'execution/'+name)
for mode in ('lifecycle-nexus-install','lifecycle-nexus-start','lifecycle-nexus-stop','lifecycle-nexus-uninstall',
             'authorize_local-review','authorize_local-apply','work-local-useful'):
    copy(W/'runtime-private'/(mode+'.returned.json'),'wrappers/'+mode+'.returned.json')
for name in ('observe.py','observation.json','interrupt.py','manifest.json','workflow.json',
             'reconcile_accounting.py','accounting-reconciliation.json','curate.py'):
    copy(H/name,'normal-interrupt/'+name)
for name in ('execute-reserved','resolve-reserved','resolved','admit-reserved','admitted','execute-result','controller-concurrent-after'):
    copy(H/'runtime'/(name+'.json'),'normal-interrupt/runtime/'+name+'.json')
copy(D/'diagnosis.json','diagnosis/diagnosis.json','292277c6548bed3779ebc121ef722db9118fc80f70dc9dd25ca65c79ef66f692')
copy(D/'observe.py','diagnosis/observe.py')
copy(D/'public-allowlist.json','diagnosis/public-allowlist.json','345b8c4794320c8c067466e30f79ecf30caeccec0302e2f95c571b0f0492f241134' if False else '345b8c4794320c8c067466e30f79ecf30caec0302e2f95c571b0f0492f241134')
decision='r4request_e133588fe9c28d66ac53353d1fedbde4f26e5c4607e382226d013500f0ad48c7-recovered-decision.json'
copy(W/'public'/decision,'execution/native-decision-recovered.json')
result_path=W/'public/m1v15-local-useful-13-result.json';result=read(result_path)
keys=('request_id','started','finished','useful_result_confirmed','record','report','submission_error',
      'maximum_poll_start_interval_seconds','outer_loop_interval_seconds','calls','independent_observation',
      'decision_count','recovered_decisions','stop_wrapper_exits','configuration_observation_limit','native_policy_fields')
projection={k:result[k] for k in keys}
projection.update(source=pin(result_path),summary={k:v for k,v in result['summary'].items() if k!='ancestry'},
                  configuration_reported_only=result['codex_thread_configuration'])
generated('execution/work-result-projection.json',projection)
apply_path=W/'public/authorize-local-apply.json';applied=read(apply_path)
generated('execution/authorization-apply-projection.json',{'source':pin(apply_path),**{k:applied[k] for k in ('status','grant','review_revision','review_sha256','model_admissions','calls')}})
companion={'status':'CANCELLED_WORK_NORMAL_CLOSURE_CONFIRMED_NO_M1_ACCEPTANCE','original_closure':pin(W/'public/closure.json'),
 'original_checkpoint':account['original_checkpoint'],'original_checkpoint_and_closure_untouched':True,
 'request_id':account['request_id'],'canonical_stage':'CANCELLED','session_state':'CLOSED','lease_state':'CLOSED',
 'collector_request_settled':True,'native_pending_count':0,'active_owned_slots':0,'cursor':51,'watermark':51,
 'interrupt':{'operation_id':account['interrupt_operation']['operation_id'],'admission_state':'DISPATCHED',
              'receipt_stage':'SUBMITTED','receipt_revision':1,'completion_receipt_confirmed':False},
 'accounting':pin(H/'accounting-reconciliation.json'),'carry_in_tokens':295262,'increment_tokens':46014,
 'cumulative_observed_tokens':341276,'charged_reservations':13,'refunds':0,'billing_final':False,
 'normal_cleanup':{'all_three_retained_handles_exited':True,'exit_codes':[0,0,0],'force_used':False,
                   'tasks_absent':True,'port_free':True,'data_directories_retained':True},
 'decision':{'canonical_state':'CONFIRMED','native_stage':'REFUSED_BEFORE_EFFECT','server_code':'PERMISSION_DENIED',
             'approval_replayed':False,'decision_count':1},
 'request14_selected':False,'remote_execution':'HELD','report_exists':False,'useful_result_confirmed':False,
 'm1_acceptance':False,'no_new_admission_authorized_by_companion':True,
 'configuration_fields':'Reported metadata only, not proof of enforcement.',
 'new_reconciliation_effects':{'provider':0,'service':0,'database_writes':0},
 'technical_limits_unchanged':{'maximum_cumulative_requests':16,'preventive_tokens':500000,'tolerance_tokens':700000}}
generated('closure-companion.json',companion)
patterns=[r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',r'\bsk-[A-Za-z0-9_-]{20,}',r'"(?:access_token|refresh_token|password|client_secret|service_token|attempt_nonce)"\s*:\s*"[^"\s]{8,}"']
matches=[]
for item in files:
    text=(OUT/item['relative_path']).read_text(encoding='utf-8')
    if any(re.search(p,text) for p in patterns):matches.append(item['relative_path'])
assert not matches,matches
generated('review.json',{'status':'ACTUAL_CANCELLED_WORK_NORMAL_CLOSURE_NO_ACCEPTANCE','copied_or_projected_artifacts':len(files),
 'copy_hashes_verified':True,'secret_scan_matches':matches,'scope':'Finite public receipts, exact returned wrapper metadata and explicit projections only; no controller, DB, event bodies, command lines, stdout, transcript or credentials copied.',
 'observed_tokens':341276,'charged_reservations':13,'request13_increment':46014,'original_checkpoint_sha256':account['original_checkpoint']['sha256'],
 'original_closure_sha256':account['original_closure']['sha256'],'original_faults':['WORK_TERMINAL_FAILED'],
 'interrupt_completion_confirmed':False,'acceptance_promoted':False,'scenario_counts':{'VERIFIED':124,'IN_PROGRESS':6,'NOT_RUN':2},
 'reconciliation':{'tool':'e5a430','exit_code':0,'elapsed_seconds':account['elapsed_seconds'],'source':'normal-interrupt/reconcile_accounting.py',
 'preparation_failures_preserved':[{'tools':['5838e3','4b0182'],'result':'Copy-builder replacement-order assertion, then absent generated script; both before DB access. Corrected builder4b316e and boundedROe5a430 passed.'}]},
 'root_execution_refs':{'interrupt':'97bfe9 exit0','work':'1f3f89 exit0; result CANCELLED','watch':'7eb0d4 exit0',
 'cleanup':'27caa7 exit0','uninstall':'1b3898 exit0','final_presence':'cbb46e exit0','closure':'0b241c exit0'},
 'root_execution_refs_are_reported_not_synthetic_process_receipts':True})
with (OUT/'artifact-manifest.json').open('x',encoding='utf-8',newline='\n') as f:json.dump({'files':files},f,indent=2);f.write('\n')
print(json.dumps({'curation':str(OUT),'files':len(files),'manifest_sha256':sha(OUT/'artifact-manifest.json'),'review_sha256':sha(OUT/'review.json')}))

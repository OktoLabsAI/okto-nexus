"""Derive accounting and closure evidence; never mutate a campaign checkpoint."""
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
B = Path('C:/Users/jpamb/AppData/Local/Temp/m1-v12-bundle-bldo9qy7')
W = B/'successor14/work-request11'
RETIRE = Path('C:/Users/jpamb/AppData/Local/Temp/m1-request11-retirement-rbqa3xf1')
PRIOR = Path('C:/Users/jpamb/AppData/Local/Temp/m1-v14-resume-interrupt-3_zkq__d')
EXTENDED = Path('C:/Users/jpamb/AppData/Local/Temp/m1-request11-exit-observation-if2rw59l/result.json')
REQUEST = 'm1v14-local-work-11'
OPENING = 'op_c43b1ade4ad6cd29dd60bf4eb1970fba'
TURN = 'op_dcd0455d4820f9abd40a57fad32c8fa9'
SESSION = 'ses_abdc7fd9ab15ccadc06fe7aec6b9f247'

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p): return json.loads(Path(p).read_bytes())
def pin(p): return {'path':str(p),'sha256':sha(p)}
def write(p,value):
    with p.open('x',encoding='utf-8',newline='\n') as f:
        json.dump(value,f,ensure_ascii=False,indent=2);f.write('\n')
def require(value,code):
    if not value: raise RuntimeError(code)

def main():
    checkpoint=W/'private/controller.json'
    initial_hash=sha(checkpoint);before=read(checkpoint)
    observation=read(HERE/'post-exit-accounting-observation.json')
    require(sha(HERE/'read_accounting.py')==observation['method']['source_sha256'],'SOURCE_CHANGED')
    sys.path.insert(0,str(W/'modules'))
    import token_collector as tokens
    from legacy_controller import seal
    require(before['state_sha256']==seal(before),'CHECKPOINT_SEAL')
    state=tokens.restore(before['collector']);summary=tokens.summary(state)
    require(before['policy']['carry_in_tokens']+summary['known_observed_tokens']==272648,'TOKENS_CHANGED')
    require(before['policy']['carry_in_admissions']+len(before['requests'])==11,'RESERVATIONS_CHANGED')
    require(before['requests'][REQUEST]['stream'] is None and before['requests'][REQUEST]['settled'] is False,'ORIGINAL_STATE_CHANGED')
    require(before['requests']['m1v14-local-work-01']['canonical_stage']=='CANCELLED' and before['requests']['m1v14-local-work-01']['settled'] is True,'HISTORY_CHANGED')
    require(sha(PRIOR/'closure-companion.json')=='9ab292850914b45c2495a4b9d7f4291ec715b7b3707b5cfe13c59a9160e0b020','PRIOR_CLOSURE_CHANGED')
    for item in read(PRIOR/'closure-companion.json')['files'].values():
        require(sha(item['path'])==item['sha256'],'PRIOR_EVIDENCE_CHANGED')
    for name,item in read(RETIRE/'manifest.json').items():
        require(sha(RETIRE/name)==item['sha256'],'RETIREMENT_PROJECTION_CHANGED')
    launch=observation['launch']
    require(len(launch)==1 and launch[0]['session_id']==SESSION and launch[0]['opening_operation_id']==OPENING
        and launch[0]['connection_generation']==6 and launch[0]['owner_generation']==1
        and launch[0]['revision']==3 and launch[0]['stop_proof']=='NEVER_CLAIMED'
        and launch[0]['producer_fenced']==1 and launch[0]['spawn_claimed']==0,'LAUNCH_PROOF_CHANGED')
    require(observation['counts']=={'process_births':0,'events':0,'event_streams':0},'NATIVE_ACTIVITY_NOT_ZERO')
    require(observation['action_counts']==[{'action':'runtime.open','count':1}],'TURN_ACTIVITY_NOT_ZERO')
    require(observation['operations']==[{'operation_id':OPENING,'stage':'FAILED','possible_effect':1,
        'retry_safe':0,'native_id':None,'error_code':'PROCESS_LAUNCH_FENCED'}],'OPENING_RECEIPT_CHANGED')
    require(observation['slots']==[] and observation['claims']==[{'operation_id':OPENING,'reconciliation_pending':1}],'CLAIM_STATE_CHANGED')
    session=observation['canonical_session']
    require(session['session_id']==SESSION and session['lifecycle_state']=='FAILED' and session['lease_state']=='CLOSED'
        and session['stream_epoch'] is None,'SESSION_CHANGED')
    db=sqlite3.connect((B/'campaign/nexus-home/nexus.db').as_uri()+'?mode=ro',uri=True,timeout=2)
    db.row_factory=sqlite3.Row;db.execute('PRAGMA query_only=ON')
    try:
        child=dict(db.execute('SELECT operation_id,session_id,parent_operation_id,admission_state,action FROM execution_operations WHERE operation_id=?',(TURN,)).fetchone())
    finally: db.close()
    require(child['session_id']==SESSION and child['parent_operation_id']==OPENING and child['admission_state']=='RESOLVED_TERMINAL','INITIAL_TURN_NOT_TERMINAL')
    force=read(HERE/'force-returned.json');removed=read(HERE/'uninstall-returned.json')
    require(force['exit_code']==0 and force['force_command_selected_once'] is True and force['state']=='stopped','FORCE_RESULT_UNCONFIRMED')
    require(removed['force_used'] is True and removed['uninstall_exit_code']==0 and removed['physical_exit_confirmed'] is True
        and removed['native_task_absent'] is True and removed['canonical_owner_absent'] is True,'REMOVAL_UNCONFIRMED')
    for path in (W/'public/nexus-exit-proof.json',EXTENDED):
        proof=read(path)
        require(proof['pid']==34276 and proof['birth_filetime']==134391567737609266
            and proof['generation']=='e700420fc6a5c92a7b434749361d805f'
            and proof['retained_handle'] is True and proof['exit_confirmed'] is True,'PHYSICAL_EXIT_MISMATCH')
    require(sha(checkpoint)==initial_hash,'ORIGINAL_CHANGED')
    derived={'format':'okto.m1.post_exit_accounting_companion','revision':1,
        'status':'FAILED_PRELAUNCH_ACCOUNTING_RECONCILED','original_checkpoint':pin(checkpoint),
        'request_id':REQUEST,'session_id':SESSION,'opening_operation_id':OPENING,'initial_turn_operation':child,
        'terminal_opening_stage':'FAILED','opening_error':'PROCESS_LAUNCH_FENCED',
        'opening_possible_effect':True,'opening_retry_safe':False,
        'canonical_session_state':'FAILED','canonical_lease_state':'CLOSED','canonical_stream_epoch':None,
        'core_launch_stop_proof':'NEVER_CLAIMED','core_claim_reconciliation_pending':True,
        'server_retirement_checkpoint_present':True,'server_retirement_release_kind':'failed_open',
        'new_native_turns':0,'new_observed_tokens':0,'cumulative_minimum_observed_tokens':272648,
        'cumulative_reserved_admissions':11,'reservation_refund':False,
        'faults_preserved':before['faults'],'collector_original_unchanged':True,
        'original_request_settled':False,'collector_settled_observed_synthesized':False,
        'loadable_controller_checkpoint':False,'accounting_reconciled':True,'billing_final':False,
        'next_admission_requires':'A genuinely new request and canonical agent recovery READY for the current replacement owner generation. No replay of request11.',
        'acceptance_promoted':False,'source':pin(Path(__file__)),
        'post_exit_projection':pin(HERE/'post-exit-accounting-observation.json'),
        'retirement_projection':pin(RETIRE/'projection-and-recovery-map.json')}
    write(HERE/'accounting-derived.json',derived)
    files={'original_checkpoint':checkpoint,'original_work_result':W/'public/m1v14-local-work-11-result.json',
        'original_work_returned':W/'runtime-private/work-local-useful.returned.json',
        'original_normal_containment':W/'public/normal-containment-result.json',
        'original_exit_observer':W/'public/nexus-exit-proof.json','extended_exit_observer':EXTENDED,
        'authorized_force_selected':HERE/'force-selected.json','authorized_force_returned':HERE/'force-returned.json',
        'uninstall_selected':HERE/'uninstall-selected.json','uninstall_returned':HERE/'uninstall-returned.json',
        'post_exit_accounting':HERE/'post-exit-accounting-observation.json','derived_accounting':HERE/'accounting-derived.json',
        'accounting_source':HERE/'read_accounting.py','derivation_source':Path(__file__),
        'prior_closure_companion':PRIOR/'closure-companion.json','retirement_projection':RETIRE/'projection-and-recovery-map.json',
        'retirement_manifest':RETIRE/'manifest.json'}
    closure={'format':'okto.m1.force_cleanup_closure_companion','revision':1,
        'status':'CLOSED_AFTER_AUTHORIZED_FORCE_ACCOUNTING_RECONCILED_ACCEPTANCE_NOT_INFERRED',
        'files':{k:pin(v) for k,v in files.items()},'campaign_revision':14,'request_id':REQUEST,
        'force_used':True,'force_command_selections':1,'user_authorization':read(HERE/'force-selected.json')['user_authorization'],
        'observer_force_false_interpretation':'Original observer records observation only; its fixed force_used=False does not describe the selected cleanup. This companion binds the actual authorized force receipt and reports force_used=True.',
        'physical_exit_confirmed':True,'nexus_task_absent':True,'canonical_owner_absent':True,
        'port_available':58631,'data_retained_scope':removed['scope'],'data_presence_unchanged':True,
        'canonical_session_state':'FAILED','canonical_lease_state':'CLOSED','server_retirement_present':True,
        'core_claim_reconciliation_pending':True,'canonical_recovery_executed':False,
        'cumulative_minimum_observed_tokens':272648,'cumulative_reserved_admissions':11,
        'request11_new_native_turns':0,'reservation_refund':False,'original_checkpoint_unchanged':True,
        'faults_preserved':before['faults'],'original_unsettled_requests':1,
        'normal_cleanup_confirmed':False,'acceptance_promoted':False,'model_or_service_started_by_reconciliation':False,
        'limits':['Canonical FAILED is not rewritten to CLOSED. Core pending claim is retained separately from Server retirement and physical absence.',
        'No fabricated stream, terminal usage event, generic release proof, or loadable replacement controller is produced.',
        'Only directory presence and primary database stat preservation were checked at uninstall; no credential or full database byte comparison.',
        'Next admission requires current-generation agent recovery READY and a genuinely new request. Original request is never replayed.']}
    write(HERE/'closure-companion.json',closure)
    require(sha(checkpoint)==initial_hash,'ORIGINAL_CHANGED_AFTER_DERIVATION')
    print(json.dumps({'accounting':pin(HERE/'accounting-derived.json'),'closure':pin(HERE/'closure-companion.json'),'force_used':True,'tokens':272648,'reservations':11}))

if __name__=='__main__':main()

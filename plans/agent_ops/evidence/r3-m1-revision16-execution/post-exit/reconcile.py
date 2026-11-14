"""Post-exit exact request14 counter/terminal metadata read; no runtime mutation."""
from pathlib import Path
import hashlib,json,sys,time
H=Path(__file__).resolve().parent
B=Path('C:/Users/jpamb/AppData/Local/Temp/m1-v12-bundle-bldo9qy7')
W=B/'successor14/work-revision16'
RID='m1v16-local-useful-14';SID='ses_7d4fc7d6c37508b2d0a6b479458da531';OP='op_8dd7095fbd5e23defbb95a7f0c22ec7e'
CP='eb57757c34300804383b37717e65acc2ce3492c95d9f243e5e9e154c7430b712'
CLOSE='eb881221c9516701a49c41ee4b9ad45445001050579eb8096a4c3dcb8ce4a1b9'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_bytes())
def pin(p):return {'path':str(p),'sha256':sha(p)}
def require(ok,code):
    if not ok:raise ValueError(code)
def main():
    cp_path=W/'private/controller.json';closure_path=W/'public/closure.json'
    require(sha(cp_path)==CP and sha(closure_path)==CLOSE,'ORIGINAL_CHANGED')
    freeze=W/'runtime-freeze.json';require(sha(freeze)=='fdcfab39cf9445c70878dfaf8f1bec3964b2debbf2c2e1ea857ba8496ccc1e94','FREEZE_CHANGED')
    for p in read(freeze)['files'].values():require(sha(p['path'])==p['sha256'],'SOURCE_CHANGED')
    physical=read(W/'public/nexus-exit-proof.json')
    require(physical['generation']=='a3b0b2982df347bd2eee1071a80ec68b' and physical['retained_handle'] is True
      and physical['exit_confirmed'] is True and physical['force_used'] is False,'EXIT_REQUIRED')
    for role,pid,birth in [('parent',3580,134391712074321788),('launcher',45752,134391712108155698),('child',49312,134391712108503297)]:
        row=physical['processes'][role]
        require(row['pid']==pid and row['birth_filetime']==birth and row['physical_exit_confirmed'] is True
          and row['exit_code']==0 and row['terminate_right'] is False,'COHORT_EXIT_REQUIRED')
    presence=read(W/'public/final-presence.json')
    require(presence['status']=='NORMAL_CLEANUP_CONFIRMED' and all(t['absent'] for t in presence['tasks'].values()),'PRESENCE_REQUIRED')
    sys.path.insert(0,str(W/'modules'))
    import token_collector as tokens
    from independent_journal import CanonicalIntentReader,CoreJournalReader
    from legacy_controller import seal
    cp=read(cp_path);require(cp['state_sha256']==seal(cp) and set(cp['requests'])=={RID},'CHECKPOINT_INVALID')
    record=cp['requests'][RID]
    require(record['session']==SID and record['operation']==OP and record['settled'] is True,'RECORD_CHANGED')
    require(cp['policy']['carry_in_tokens']==341276 and cp['policy']['carry_in_admissions']==13,'CARRY_CHANGED')
    state=tokens.restore(cp['collector']);original=tokens.summary(state)
    home=B/'campaign/nexus-home';reader=CanonicalIntentReader(B,home,server_id=record['scope']['server_id'],actor_id=record['actor_agent_id'],pre_scope=record['scope'])
    journal=CoreJournalReader(B,home,'local');start=time.monotonic()
    def bound():require(time.monotonic()-start<30,'READ_TOTAL_BOUND')
    reader.io.aggregate_check=bound;journal.io.aggregate_check=bound
    try:
        canonical=reader.read(RID)
        require(canonical and canonical['operation_id']==OP and canonical['scope']['session_id']==SID,'CANONICAL_CHANGED')
        scope=canonical['scope'];require(all(scope[k]==v for k,v in record['scope'].items()),'SCOPE_CHANGED')
        pages=[]
        for _ in range(20):
            cursor=state['streams'][record['stream']]['cursor'];page=journal.read(scope,cursor)
            require(page and page['stream_epoch']==canonical['session_state']['stream_epoch'],'STREAM_CHANGED')
            state=tokens.bind_operation(state,request_id=RID,operation_id=OP)
            state=tokens.observe(state,stream=record['stream'],after_sequence=cursor,page=page)
            pages.append({'after_sequence':cursor,'event_count':page['count'],'next_after_sequence':page['next_after_sequence'],
              'committed_contiguous':page['committed_contiguous'],'has_more':page['has_more'],'projection_sha256':tokens.fingerprint(page)})
            if not page['has_more']:break
        else:raise ValueError('CATCHUP_INCOMPLETE')
        key=tuple(scope[k] for k in ('server_id','executor_id','session_id'))
        with reader.io.open(reader.database) as db:
            native=[dict(row) for row in db.execute('SELECT canonical_request_id,source_operation_id,source_sequence,kind,request_revision,state FROM execution_native_requests WHERE server_id=? AND executor_id=? AND session_id=? LIMIT 20',key)]
        with journal.io.open(journal.path(scope)) as db:
            op=db.execute('SELECT operation_id,stage,possible_effect,retry_safe,error_code FROM operations_v2 WHERE server_id=? AND executor_id=? AND session_id=? AND operation_id=?',(*key,OP)).fetchone()
            slots=db.execute('SELECT count(*) FROM owned_slot_reservations WHERE server_id=? AND executor_id=? AND session_id=? AND released=0',key).fetchone()[0]
        summary=tokens.summary(state);stream=state['streams'][record['stream']];components=state['threads'][stream['thread']]['components']
        require(canonical['operation_receipt']['stage']=='SUCCEEDED' and state['requests'][RID]['state']=='settled_observed','TERMINAL_UNCONFIRMED')
        require(canonical['session_state']['lifecycle_state']=='CLOSED' and canonical['session_state']['lease_state']=='CLOSED','SESSION_NOT_CLOSED')
        require(slots==0 and not any(n['state']=='PENDING' for n in native),'PENDING_REMAINS')
        require(sha(cp_path)==CP and sha(closure_path)==CLOSE,'ORIGINAL_CHANGED_DURING_READ')
        value={'kind':'POST_EXIT_READONLY_ACCOUNTING_COMPANION_NOT_CONTROLLER','request_id':RID,
          'original_checkpoint':pin(cp_path),'original_closure':pin(closure_path),'originals_untouched':True,
          'original_faults':cp['faults'],'original_request_settled':record['settled'],
          'canonical':canonical,'core_operation':dict(op) if op else None,'native_requests':native,'native_pending_count':0,
          'native_decision_receipt_completion_asserted':False,'native_decision_receipt_scope':'Two original recovered GET snapshots SUBMITTED; no final decision receipt queried or inferred.',
          'active_owned_slots':slots,'collector_request_state_observed_post_exit':state['requests'][RID]['state'],
          'cursor':stream['cursor'],'watermark':stream['watermark'],'pages':pages,'collector_summary':summary,
          'collector_post_exit_sha256':tokens.fingerprint(state),'original_observed_increment':original['known_observed_tokens'],
          'carry_in_tokens':341276,'request14_observed_tokens':summary['known_observed_tokens'],
          'cumulative_observed_tokens':341276+summary['known_observed_tokens'],'charged_reservations':14,
          'usage_components':components,'cached_input_is_subset_of_input':True,'reasoning_output_is_subset_of_output':True,
          'refunds':0,'billing_final':False,'new_admissions_during_reconciliation':0,'request15_selected':False,
          'useful_result_confirmed':False,'report_exists':False,'m1_acceptance':False,
          'physical_exit':pin(W/'public/nexus-exit-proof.json'),'final_presence':pin(W/'public/final-presence.json'),
          'source':pin(__file__),'runtime_freeze':pin(freeze),'elapsed_seconds':time.monotonic()-start,
          'method':'mode=ro/query_only; exact session/operation and token counters; no bodies, transcript, auth or credentials',
          'bounds_seconds':{'snapshot':1,'schema_initialization':2,'post_exit_total':30},'observed_at':time.time()}
        with (H/'accounting-reconciliation.json').open('x',encoding='utf-8',newline='\n') as f:json.dump(value,f,indent=2);f.write('\n')
        print(json.dumps({k:value[k] for k in ('cumulative_observed_tokens','charged_reservations','request14_observed_tokens','usage_components','cursor','watermark')}))
    finally:reader.close();journal.close()
if __name__=='__main__':main()

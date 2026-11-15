"""Exact two closed operations, one shared token stream, read-only metadata only."""
from pathlib import Path
import hashlib,json,sys,time
H=Path(__file__).resolve().parent
B=Path('C:/Users/jpamb/AppData/Local/Temp/m1-v12-bundle-bldo9qy7');W=B/'successor14/work-revision17-recovery'
OPS={'m1v17-local-useful-15':'op_c95872f5eee66108a4aa925f224fc0d5','m1v17-local-continuation-16':'op_31d6b7d97bbbf722ddaedf4eda54a2da'}
SID='ses_ae4b9b97e3e5735bac46a73b89f71814'
CP='9e8f1ff7c8a4dbf10d428af608611ae25093898ca6562815be53a82a89c05749';CLOSE='0c4d8032ee6fdc262f1be37971ca992466cce4f94a4c00d33b5736ae1fc30fbf'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_bytes())
def pin(p):return {'path':str(p),'sha256':sha(p)}
def require(ok,code):
    if not ok:raise ValueError(code)
def main():
    cp_path=W/'private/controller.json';closure_path=W/'public/closure.json';freeze=W/'runtime-freeze.json'
    require(sha(cp_path)==CP and sha(closure_path)==CLOSE,'ORIGINAL_CHANGED')
    require(sha(freeze)=='138bbab052dae46310b53204a15e1ccc66260b9513587ce14951273198320dce','FREEZE_CHANGED')
    for item in read(freeze)['files'].values():require(sha(item['path'])==item['sha256'],'SOURCE_CHANGED')
    physical=read(W/'public/nexus-exit-proof.json');selection=read(W/'public/nexus-owner-selection.json')
    require(physical['generation']==selection['generation'] and physical['retained_handle'] is True
        and physical['exit_confirmed'] is True and physical['force_used'] is False,'EXACT_EXIT_REQUIRED')
    for role,pid,birth in [('parent',45764,134391739942993778),('launcher',17136,134391739981865173),('child',33872,134391739982406365)]:
        row=physical['processes'][role]
        require(row['pid']==pid and row['birth_filetime']==birth and row['physical_exit_confirmed'] is True
            and row['exit_code']==0 and row['terminate_right'] is False,'COHORT_EXIT_REQUIRED')
    presence=read(W/'public/final-presence.json')
    require(presence['status']=='NORMAL_CLEANUP_CONFIRMED' and all(t['absent'] for t in presence['tasks'].values()),'PRESENCE_REQUIRED')
    sys.path.insert(0,str(W/'modules'))
    import token_collector as tokens
    from independent_journal import CanonicalIntentReader,CoreJournalReader
    from legacy_controller import seal
    cp=read(cp_path);require(cp['state_sha256']==seal(cp) and set(cp['requests'])==set(OPS),'CHECKPOINT_INVALID')
    require(cp['policy']['carry_in_tokens']==460793 and cp['policy']['carry_in_admissions']==14,'CARRY_CHANGED')
    records=cp['requests'];streams={record['stream'] for record in records.values()}
    require(len(streams)==1,'EXPECTED_ONE_SHARED_STREAM');stream_id=next(iter(streams))
    record=records['m1v17-local-useful-15']
    for rid,op in OPS.items():
        row=records[rid];require(row['session']==SID and row['operation']==op and row['settled'] is True
            and row['scope']==record['scope'],'RECORD_CHANGED')
    state=tokens.restore(cp['collector']);original=tokens.summary(state)
    home=B/'campaign/nexus-home';reader=CanonicalIntentReader(B,home,server_id=record['scope']['server_id'],actor_id=record['actor_agent_id'],pre_scope=record['scope'])
    journal=CoreJournalReader(B,home,'local');start=time.monotonic()
    def bound():require(time.monotonic()-start<30,'READ_TOTAL_BOUND')
    reader.io.aggregate_check=bound;journal.io.aggregate_check=bound
    try:
        canonical={}
        for rid,op in OPS.items():
            value=reader.read(rid);canonical[rid]=value
            require(value and value['operation_id']==op and value['scope']['session_id']==SID,'CANONICAL_CHANGED')
            require(all(value['scope'][k]==v for k,v in record['scope'].items()),'SCOPE_CHANGED')
            require(value['operation_receipt']['stage']=='SUCCEEDED','TERMINAL_UNCONFIRMED')
            require(value['session_state']['lifecycle_state']=='CLOSED' and value['session_state']['lease_state']=='CLOSED','SESSION_NOT_CLOSED')
            state=tokens.bind_operation(state,request_id=rid,operation_id=op)
        scope=canonical['m1v17-local-useful-15']['scope'];epochs={v['session_state']['stream_epoch'] for v in canonical.values()}
        require(len(epochs)==1,'STREAM_EPOCH_DIVERGED');epoch=next(iter(epochs));pages=[]
        # Poll the shared stream once, not once per operation. Collector retains per-thread high water.
        for _ in range(20):
            cursor=state['streams'][stream_id]['cursor'];page=journal.read(scope,cursor)
            require(page and page['stream_epoch']==epoch,'STREAM_CHANGED')
            state=tokens.observe(state,stream=stream_id,after_sequence=cursor,page=page)
            pages.append({'after_sequence':cursor,'event_count':page['count'],'next_after_sequence':page['next_after_sequence'],
                'committed_contiguous':page['committed_contiguous'],'has_more':page['has_more'],'projection_sha256':tokens.fingerprint(page)})
            if not page['has_more']:break
        else:raise ValueError('CATCHUP_INCOMPLETE')
        key=tuple(scope[k] for k in ('server_id','executor_id','session_id'))
        with reader.io.open(reader.database) as db:
            native=[dict(row) for row in db.execute('SELECT canonical_request_id,source_operation_id,source_sequence,kind,request_revision,state FROM execution_native_requests WHERE server_id=? AND executor_id=? AND session_id=? LIMIT 20',key)]
        with journal.io.open(journal.path(scope)) as db:
            ops=[dict(row) for row in db.execute('SELECT operation_id,stage,possible_effect,retry_safe,error_code FROM operations_v2 WHERE server_id=? AND executor_id=? AND session_id=? AND operation_id IN (?,?)',(*key,*OPS.values()))]
            slots=db.execute('SELECT count(*) FROM owned_slot_reservations WHERE server_id=? AND executor_id=? AND session_id=? AND released=0',key).fetchone()[0]
        require(len(ops)==2 and all(op['stage']=='SUCCEEDED' for op in ops),'CORE_TERMINALS_REQUIRED')
        require(slots==0 and not any(n['state']=='PENDING' for n in native),'PENDING_REMAINS')
        require(all(state['requests'][rid]['state']=='settled_observed' for rid in OPS),'COLLECTOR_TERMINAL_REQUIRED')
        summary=tokens.summary(state);stream=state['streams'][stream_id];components=state['threads'][stream['thread']]['components']
        require(sha(cp_path)==CP and sha(closure_path)==CLOSE,'ORIGINAL_CHANGED_DURING_READ')
        value={'kind':'POST_EXIT_READONLY_ACCOUNTING_COMPANION_NOT_CONTROLLER','request_ids':list(OPS),
            'original_checkpoint':pin(cp_path),'original_closure':pin(closure_path),'originals_untouched':True,
            'original_faults':cp['faults'],'original_requests_settled':{rid:records[rid]['settled'] for rid in OPS},
            'canonical':canonical,'core_operations':ops,'native_requests':native,'native_pending_count':0,'active_owned_slots':slots,
            'native_decision_receipt_completion_asserted':False,'native_decision_receipt_scope':'Original recovered GET snapshot retained separately; no final delivery receipt queried or inferred.',
            'shared_stream_count':1,'same_canonical_session':True,'stream_observed_once_not_per_request':True,
            'collector_request_states':{rid:state['requests'][rid]['state'] for rid in OPS},
            'cursor':stream['cursor'],'watermark':stream['watermark'],'pages':pages,'collector_summary':summary,
            'collector_post_exit_sha256':tokens.fingerprint(state),'original_observed_increment':original['known_observed_tokens'],
            'carry_in_tokens':460793,'new_observed_tokens_once':summary['known_observed_tokens'],
            'cumulative_observed_tokens':460793+summary['known_observed_tokens'],'charged_reservations':16,
            'usage_components':components,'cached_input_is_subset_of_input':True,'reasoning_output_is_subset_of_output':True,
            'refunds':0,'billing_final':False,'new_admissions_during_reconciliation':0,'remote_selected':False,
            'acceptance_promoted':False,'physical_exit':pin(W/'public/nexus-exit-proof.json'),'final_presence':pin(W/'public/final-presence.json'),
            'source':pin(__file__),'runtime_freeze':pin(freeze),'elapsed_seconds':time.monotonic()-start,
            'method':'mode=ro/query_only; exact two operations/single session and projected token counters; no bodies/transcripts/auth',
            'bounds_seconds':{'snapshot':1,'schema_initialization':2,'post_exit_total':30},'observed_at':time.time()}
        with (H/'accounting-reconciliation.json').open('x',encoding='utf-8',newline='\n') as f:json.dump(value,f,indent=2);f.write('\n')
        print(json.dumps({k:value[k] for k in ('cumulative_observed_tokens','charged_reservations','new_observed_tokens_once','usage_components','cursor','watermark')}))
    finally:reader.close();journal.close()
if __name__=='__main__':main()

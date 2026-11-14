"""Read-only post-exit accounting, producing a separate derived checkpoint."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import time

HERE=Path(__file__).resolve().parent
B=Path('C:/Users/jpamb/AppData/Local/Temp/m1-v12-bundle-bldo9qy7')
S=B/'successor14/resume-request01'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def require(ok,code):
    if not ok:raise RuntimeError(code)
def read(p):return json.loads(Path(p).read_bytes())
def write(p,v):
    with Path(p).open('x',encoding='utf-8',newline='\n') as f:
        json.dump(v,f,indent=2,sort_keys=True);f.write('\n')

def main():
    original=S/'private/controller.json'
    require(sha(original)=='941420d2130cdda4d6ca96e2e855675c53fbe527a6f1b51c41302b940b4b8e0a','ORIGINAL_CHECKPOINT_CHANGED')
    proposal=S.parent/'draft/m1-codex-campaign-proposal-v14.json'
    require(sha(proposal)=='9238a96c01bdf5ebb65264cf4a9c4b0dd7d27caf155fafbcc136dba5e976368e','PROPOSAL_CHANGED')
    pins=read(proposal)['execution_bundle']['files']
    for entry in pins.values():
        require(sha(entry['path'])==entry['sha256'],'FROZEN_SOURCE_CHANGED')
    sys.path.insert(0,str(S.parent/'draft/controller'))
    import token_collector as tokens
    import independent_journal as journal_module
    from independent_journal import CanonicalIntentReader,CoreJournalReader
    # Offline-only, post-exit readers. No controller or admission is instantiated.
    # The live 250ms failure remains preserved; this is accounting reconciliation.
    reconciliation_started=time.monotonic()
    def total_bound():
        require(time.monotonic()-reconciliation_started<30,'POST_EXIT_RECONCILIATION_DEADLINE')
    OriginalReadOnly=journal_module.ReadOnly
    class PostExitReadOnly(OriginalReadOnly):
        def __init__(self,root):
            super().__init__(root)
            self.budget=2.0;self.initialization_budget=2.0
            self.aggregate_check=total_bound
    journal_module.ReadOnly=PostExitReadOnly
    physical_path=S/'public/nexus-exit-proof.json'
    physical=read(physical_path)
    require(physical['pid']==53004 and physical['birth_filetime']==134391534445053432
        and physical['generation']=='cfec0795237a444636046a3541a5cd7d'
        and physical['retained_handle'] is True and physical['exit_confirmed'] is True
        and physical['force_used'] is False,'EXACT_PHYSICAL_EXIT_REQUIRED')
    stop=read(HERE/'runtime/normal-stop-result.json')
    require(stop['cli_exit']==0 and stop['wrapper_exit_confirmed'] is True
        and stop['observation']['state']=='stopped','NORMAL_STOP_UNCONFIRMED')
    from legacy_controller import seal
    before=read(original);out=copy.deepcopy(before)
    require(before['state_sha256']==seal(before),'ORIGINAL_SEAL_INVALID')
    require(set(before['requests'])=={'m1v14-local-work-01'},'REQUEST_SET_CHANGED')
    request_id='m1v14-local-work-01';record=out['requests'][request_id]
    require(record['lane']=='local' and record['kind']=='work' and record['stream'],'EXISTING_LOCAL_STREAM_REQUIRED')
    home=B/'campaign/nexus-home'
    require(before['owners']['local']==str(home.resolve()),'OWNER_CHANGED')
    state=tokens.restore(before['collector'])
    reader=CanonicalIntentReader(B,home,server_id=record['scope']['server_id'],
        actor_id=record['actor_agent_id'],pre_scope=record['scope'])
    journal=CoreJournalReader(B,home,'local')
    pages=[]
    try:
        observed=reader.read(request_id)
        require(observed is not None and not observed['preopen_failed'],'CANONICAL_UNCONFIRMED')
        scope=observed['scope']
        require(all(scope[k]==v for k,v in record['scope'].items())
            and record['session']==scope['session_id']
            and record['operation']==observed['operation_id'],'SCOPE_CHANGED')
        # Bounded post-exit catch-up: 2s snapshots/initialization and 30s total, read-only.
        for _ in range(20):
            cursor=state['streams'][record['stream']]['cursor']
            page=journal.read(scope,cursor)
            require(page is not None,'CORE_JOURNAL_UNCONFIRMED')
            require((observed['session_state'] or {}).get('stream_epoch')==page['stream_epoch'],'EPOCH_CHANGED')
            state=tokens.bind_operation(state,request_id=request_id,operation_id=record['operation'])
            state=tokens.observe(state,stream=record['stream'],after_sequence=cursor,page=page)
            pages.append({'after_sequence':cursor,'page_sha256':tokens.fingerprint(page),
              'event_count':len(page['events']),'cursor_after':state['streams'][record['stream']]['cursor'],
              'page_keys':sorted(page)})
            if not page.get('has_more',False):break
        else:raise RuntimeError('BOUNDED_CATCHUP_INCOMPLETE')
        receipt=observed['operation_receipt']
        settled=(state['requests'][request_id]['state']=='settled_observed'
            and receipt is not None and receipt['stage'] in ('SUCCEEDED','FAILED','CANCELLED'))
        require(settled,'POST_EXIT_SETTLEMENT_UNCONFIRMED')
        record['settled']=True;record['canonical_stage']=receipt['stage']
        if receipt['stage']!='SUCCEEDED' and 'WORK_TERMINAL_FAILED' not in out['faults']:
            out['faults'].append('WORK_TERMINAL_FAILED');out['faults'].sort()
        out['collector']=tokens.checkpoint(state)
        out['state_sha256']=seal(out)
        require(set(before['faults']).issubset(out['faults']) and 'OBSERVATION_UNKNOWN' in out['faults'],'FAULT_LOST')
        require(out['policy']==before['policy'] and out['ancestry']==before['ancestry'],'POLICY_CHANGED')
        require(sha(original)=='941420d2130cdda4d6ca96e2e855675c53fbe527a6f1b51c41302b940b4b8e0a','ORIGINAL_CHANGED_DURING_READ')
        derived=HERE/'controller-reconciled.json';write(derived,out)
        summary=tokens.summary(state)
        evidence={'kind':'READONLY_POST_EXIT_DERIVED_CHECKPOINT','original':{'path':str(original),'sha256':sha(original)},
          'derived':{'path':str(derived),'sha256':sha(derived)},'canonical':observed,'pages':pages,
          'known_observed_tokens':before['policy']['carry_in_tokens']+summary['known_observed_tokens'],
          'reserved_requests':before['policy']['carry_in_admissions']+len(out['requests']),
          'faults':out['faults'],'settled':True,'original_untouched':True,'new_model_admissions':0,
          'observed_at':time.time(),'source_sha256':sha(__file__),
          'useful_result_acceptance_inferred':False,'closure_required_separately':True,
          'post_exit_only_observation_bounds':{'snapshot_seconds':2,'initialization_seconds':2,'total_seconds':30},
          'live_controller_bounds_unchanged':True,
          'physical_exit_proof':{'path':str(physical_path),'sha256':sha(physical_path)},
          'original_first_observation_error':before['requests'][request_id]['first_observation_error'],
          'elapsed_seconds':time.monotonic()-reconciliation_started}
        write(HERE/'accounting-reconciliation.json',evidence)
        print(json.dumps({k:evidence[k] for k in ('known_observed_tokens','reserved_requests','faults','settled','derived')}))
    finally:
        journal.close();reader.close()

if __name__=='__main__':main()

"""Read-only post-exit accounting, producing a separate derived checkpoint."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import time

HERE=Path(__file__).resolve().parent
B=Path('C:/Users/jpamb/AppData/Local/Temp/m1-v12-bundle-bldo9qy7')
S=B/'successor13'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def require(ok,code):
    if not ok:raise RuntimeError(code)
def read(p):return json.loads(Path(p).read_bytes())
def write(p,v):
    with Path(p).open('x',encoding='utf-8',newline='\n') as f:
        json.dump(v,f,indent=2,sort_keys=True);f.write('\n')

def main():
    original=S/'private/controller.json'
    require(sha(original)=='86eeda7af8851a9a39c377180a68a5e45d05f84ed349e102fac68a295be7c84c','ORIGINAL_CHECKPOINT_CHANGED')
    proposal=S/'draft/m1-codex-campaign-proposal-v13.json'
    require(sha(proposal)=='34740bded94e3ab04a5714cfdbcf5d48d83be8d0f3999cccfe99b5864947f2f2','PROPOSAL_CHANGED')
    pins=read(proposal)['execution_bundle']['files']
    for entry in pins.values():
        require(sha(entry['path'])==entry['sha256'],'FROZEN_SOURCE_CHANGED')
    sys.path.insert(0,str(S/'draft/controller'))
    import token_collector as tokens
    from independent_journal import CanonicalIntentReader,CoreJournalReader
    from legacy_controller import seal
    before=read(original);out=copy.deepcopy(before)
    require(before['state_sha256']==seal(before),'ORIGINAL_SEAL_INVALID')
    require(set(before['requests'])=={'m1v12-local-work-01'},'REQUEST_SET_CHANGED')
    request_id='m1v12-local-work-01';record=out['requests'][request_id]
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
        # Bounded catch-up, with each page using the already-qualified SQL budget.
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
        require(set(before['faults']).issubset(out['faults']) and 'DEADLINE120' in out['faults'],'FAULT_LOST')
        require(out['policy']==before['policy'] and out['ancestry']==before['ancestry'],'POLICY_CHANGED')
        require(sha(original)=='86eeda7af8851a9a39c377180a68a5e45d05f84ed349e102fac68a295be7c84c','ORIGINAL_CHANGED_DURING_READ')
        derived=HERE/'controller-reconciled.json';write(derived,out)
        summary=tokens.summary(state)
        evidence={'kind':'READONLY_POST_EXIT_DERIVED_CHECKPOINT','original':{'path':str(original),'sha256':sha(original)},
          'derived':{'path':str(derived),'sha256':sha(derived)},'canonical':observed,'pages':pages,
          'known_observed_tokens':before['policy']['carry_in_tokens']+summary['known_observed_tokens'],
          'reserved_requests':before['policy']['carry_in_admissions']+len(out['requests']),
          'faults':out['faults'],'settled':True,'original_untouched':True,'new_model_admissions':0,
          'observed_at':time.time(),'source_sha256':sha(__file__),
          'useful_result_acceptance_inferred':False,'closure_required_separately':True}
        write(HERE/'accounting-reconciliation.json',evidence)
        print(json.dumps({k:evidence[k] for k in ('known_observed_tokens','reserved_requests','faults','settled','derived')}))
    finally:
        journal.close();reader.close()

if __name__=='__main__':main()

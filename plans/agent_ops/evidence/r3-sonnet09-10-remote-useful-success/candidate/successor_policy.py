"""Pending successor authority: no active policy without the explicit new answer."""
from pathlib import Path
from copy import deepcopy
from request_context import require,read_json,pin
from sonnet_usage import restore_budget,checkpoint_budget
HERE=Path(__file__).parent
IDS={'useful':'m1-sonnet-remote-useful-09','continuation':'m1-sonnet-remote-continuation-10'}
POLICY={'limit':500000,'preventive':480000,'max_requests':5,'server_max':6,'new_requests_max':2,'continuation_input_multiplier':1}
def authorize(record,candidate):
    require(isinstance(record,dict) and record.get('explicit_user_approval') is True
        and isinstance(record.get('user_response'),str) and bool(record['user_response'].strip())
        and isinstance(record.get('response_reference'),str) and bool(record['response_reference'].strip()),'AUTHORIZATION_PENDING')
    require(record.get('policy')==POLICY and record.get('carry_tokens')==180426
        and record.get('native_charges')==3 and record.get('server_admissions')==4,'AUTHORIZATION_SCOPE_CHANGED')
    pin(candidate['proposal']);return POLICY
def convert(seed,record,candidate):
    authorize(record,candidate);budget=restore_budget(seed)
    require((budget.limit,budget.preventive,budget.max_requests,budget.known)==(500000,480000,4,180426),'CURRENT_POLICY_SEED_CHANGED')
    require(sum(len(l.reserved) for l in budget.sessions.values())==3,'CURRENT_NATIVE_CHARGES_CHANGED')
    prior=deepcopy(checkpoint_budget(budget)['state']['sessions']);budget.max_requests=5
    result=checkpoint_budget(budget);require(result['state']['sessions']==prior,'HISTORY_CHANGED');return result
def validate_history(budget,seed):
    original=restore_budget(seed)
    require((budget.limit,budget.preventive,budget.max_requests)==(500000,480000,5)
        and original.known==180426 and original.max_requests==5,'SUCCESSOR_POLICY_CHANGED')
    rows=checkpoint_budget(budget)['state']['sessions'];old=checkpoint_budget(original)['state']['sessions']
    key=lambda r:tuple(r['scope'][k] for k in ('server_id','executor_id','session_id','stream_epoch'))
    index={key(r):r for r in rows}
    require(len(old)==3 and all(index.get(key(r))==r for r in old),'HISTORICAL_ROWS_CHANGED')
    oldkeys={key(r) for r in old}
    require(all((r['limit'],r['preventive'],r['max_requests'])==(500000,480000,5) for r in rows if key(r) not in oldkeys),'NEW_LEDGER_POLICY_CHANGED')
    require(budget.known>=180426 and sum(len(l.reserved) for l in budget.sessions.values())<=5,'CUMULATIVE_LIMIT_CHANGED')
def authorize_plan(plan):
    require(Path(plan['successor_candidate']['path']).resolve()==HERE/'candidate.json','OWN_CANDIDATE_REQUIRED')
    candidate=read_json(pin(plan['successor_candidate']));record=read_json(pin(plan['budget_authorization']))
    authorize(record,candidate)
    proposal=read_json(pin(candidate['proposal']))
    require(plan['request_ids']==IDS and plan['successor']['global_max_requests']==5
        and plan['phase_reserve_policy']==proposal['proposed']['reserve_policy'],'APPROVED_PHASE_POLICY_CHANGED')
    require(read_json(pin(plan['budget_seed']))==convert(read_json(pin(candidate['current_seed'])),record,candidate),'DERIVED_SEED_CHANGED')

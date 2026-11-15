"""Local record of an explicit user answer; this module never grants authority."""
from copy import deepcopy
from pathlib import Path
import json
from request_context import require,pin,read_json,sha
from sonnet_usage import restore_budget,checkpoint_budget

HERE=Path(__file__).resolve().parent
POLICY={'limit':500000,'preventive':480000,'max_requests':4}
IDS={'useful':'m1-sonnet-remote-useful-07','continuation':'m1-sonnet-remote-continuation-08'}

def history(document):
    budget=restore_budget(document)  # Verifies the original JSON seal, without normalization/bypass.
    require(budget.known==144004 and sum(len(x.reserved) for x in budget.sessions.values())==2,
            'EXACT_HISTORICAL_CARRY_REQUIRED')
    require((budget.limit,budget.preventive,budget.max_requests)==(200000,180000,3),
            'ORIGINAL_HISTORY_POLICY_CHANGED')
    require(len(budget.sessions)==2,'HISTORICAL_SESSIONS_CHANGED')
    return budget

def authorize(record,candidate):
    # Root records the actual answer to the pending question. No user signature,
    # hash typing, new question or additional consent ceremony is required.
    require(type(record) is dict and record.get('explicit_user_approval') is True,
            'BUDGET_AUTHORIZATION_PENDING')
    require(type(record.get('user_response')) is str and bool(record['user_response'].strip())
            and type(record.get('response_reference')) is str and bool(record['response_reference'].strip()),
            'ACTUAL_USER_RESPONSE_REQUIRED')
    require(record.get('proposal_sha256')==candidate['proposal']['sha256']
            and record.get('policy')==POLICY and record.get('carry_tokens')==144004
            and record.get('charged_requests')==2 and record.get('new_requests_max')==2,
            'BUDGET_AUTHORIZATION_SCOPE_CHANGED')
    return POLICY

def convert(document,record,candidate):
    authorize(record,candidate)
    budget=history(document)
    before=deepcopy(checkpoint_budget(budget)['state']['sessions'])
    # Historical ledgers retain their exact original policy and all usage fields.
    budget.limit=500000;budget.preventive=480000;budget.max_requests=4
    result=checkpoint_budget(budget)
    require(result['state']['sessions']==before,'HISTORICAL_ROWS_CHANGED')
    return result

def validate_history(budget,seed_document):
    seed=restore_budget(seed_document)
    require((budget.limit,budget.preventive,budget.max_requests)==(500000,480000,4)
            and (seed.limit,seed.preventive,seed.max_requests)==(500000,480000,4)
            and seed.known==144004,'CUMULATIVE_POLICY_CHANGED')
    old=checkpoint_budget(seed)['state']['sessions']
    require(sum(len(row['reserved']) for row in old)==2,'HISTORICAL_CHARGES_CHANGED')
    current=checkpoint_budget(budget)['state']['sessions']
    key=lambda row:tuple(row['scope'][k] for k in ('server_id','executor_id','session_id','stream_epoch'))
    indexed={key(row):row for row in current}
    for row in old:require(indexed.get(key(row))==row,'HISTORICAL_USAGE_OR_RESERVATION_CHANGED')
    previous={key(row) for row in old}
    for row in current:
        if key(row) not in previous:
            require((row['limit'],row['preventive'],row['max_requests'])==(500000,480000,4),
                    'NEW_LEDGER_POLICY_CHANGED')
    require(budget.known>=144004 and sum(len(x.reserved) for x in budget.sessions.values())<=4,
            'CUMULATIVE_LIMIT_OR_ALLOCATION_CHANGED')

def authorize_plan(plan):
    candidate=read_json(pin(plan['successor_candidate']))
    require(Path(plan['successor_candidate']['path']).resolve()==HERE/'candidate.json','OWN_CANDIDATE_REQUIRED')
    pin(candidate['proposal']);pin(candidate['history'])
    authorize(read_json(pin(plan['budget_authorization'])),candidate)
    require(plan['request_ids']==IDS and plan['successor']['global_max_requests']==4,
            'SUCCESSOR_ALLOCATION_CHANGED')
    derived=read_json(pin(plan['budget_seed']))
    expected=convert(read_json(pin(candidate['history'])),read_json(pin(plan['budget_authorization'])),candidate)
    require(derived==expected,'SEED_NOT_AUTHORIZED_DERIVATION')


"""Canonical read-only review; no issuance, recovery, or saved checkpoint."""
from datetime import datetime,timezone
from request_context import require
from okto_nexus.application.terminal_connection import PREFIX

GRANT='grant_3fbf5b1b947f46729770b9daf0287eef'
ACTIONS={'open','send','steer','interrupt','close'}

def validate(value,scope,phase,now):
    require(phase in ('useful','continuation'),'GRANT_PHASE_CHANGED')
    require(value.get('state')=='authorization_review' and value.get('has_more_grants') is False
        and type(value.get('current_grants')) is list and len(value['current_grants'])<=50
        and value.get('total_grants')==len(value['current_grants']),'CURRENT_GRANT_REVIEW_INCOMPLETE')
    require(all(value.get('scope',{}).get(k)==v for k,v in scope.items()),'CURRENT_GRANT_SCOPE_CHANGED')
    rows=[r for r in value['current_grants'] if r.get('grant_id')==GRANT]
    require(len(rows)==1,'CURRENT_GRANT_NOT_UNIQUE');grant=rows[0]
    require(grant.get('state')=='available' and grant.get('max_executions')==3
        and type(grant.get('used_executions')) is int and 0<=grant['used_executions']<=3,'CURRENT_GRANT_UNAVAILABLE')
    require(set(grant.get('actions',[]))==set(value.get('actions',[]))==ACTIONS,'CURRENT_GRANT_ACTIONS_CHANGED')
    remaining=3-grant['used_executions']
    require(remaining>=(2 if phase=='useful' else 1),'CURRENT_GRANT_BALANCE_INSUFFICIENT')
    expires=datetime.fromisoformat(grant['expires_at'].replace('Z','+00:00'))
    require(expires.tzinfo is not None and (expires-now).total_seconds()>=600,'CURRENT_GRANT_WINDOW_INSUFFICIENT')
    return {'grant_id':GRANT,'remaining_actions':remaining,'expires_at':grant['expires_at'],'scope_matches':True}

def check(flow,scope,phase,request_id):
    value=flow.call('POST',PREFIX+'/connections/authorizations:review',{'binding_id':scope['binding_id'],
        'client_request_id':request_id+'-readonly-grant-preflight','minutes':60,'max_executions':3})
    return validate(value,scope,phase,datetime.now(timezone.utc))

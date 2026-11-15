"""Independent lifecycle/official-client GET observation; never uses WorkContext."""
from urllib.parse import quote

def require(ok,code):
    if not ok:raise ValueError(code)

def same_active_operation(operation):
    stage=operation.get('executor_stage');admission=operation.get('admission_state')
    if stage=='SUBMITTED' and admission=='DISPATCHED':return True
    if stage in ('SUCCEEDED','FAILED','CANCELLED') or admission=='RESOLVED_TERMINAL':return False
    return None  # Missing or unfamiliar states are not positive liveness evidence.

def observe(X,nexus,connector,*,expected_selections,scope,operation_id,operator_profile):
    # X is only the selected L3 RecoveryContext, not paid WorkContext. The
    # caller pins X/modules/selection receipts before importing/calling this.
    handles={};selected={}
    try:
        for name,module in (('nexus',nexus),('connector',connector)):
            current,group=module.capture(X);handles[name]=group;selected[name]=current
            require(current['cohort']==expected_selections[name]['cohort']
                and all(current.get(k)==expected_selections[name].get(k) for k in ('pid','generation','instance_id')),
                'OBSERVATION_OWNER_CHANGED')
            require(set(group)=={'parent','launcher','child'} and not any(h.exited() for h in group.values()),'SIX_LIVE_HANDLES_REQUIRED')
        from okto_nexus.adapters.outbound.operator_client import OperatorProfile
        from okto_nexus.application.terminal_connection import PREFIX
        client=OperatorProfile(X.P['paths']['operator_home'],operator_profile).client()
        client.timeout=5
        me=client.verify();require(me['server_id']==scope['server_id'],'OPERATOR_SERVER_CHANGED')
        operation=client('GET',PREFIX+'/runtime/operations/'+quote(operation_id,safe=''))
        require(operation['operation_id']==operation_id and all(operation['scope'].get(k)==v for k,v in scope.items()),
                'OBSERVATION_OPERATION_SCOPE_CHANGED')
        require(not any(h.exited() for group in handles.values() for h in group.values()),'OWNER_EXIT_DURING_GET')
        return {'operation_id':operation_id,'session_id':scope['session_id'],'scope_matches':True,
            'executor_stage':operation.get('executor_stage'),'admission_state':operation.get('admission_state'),
            'same_active_operation':same_active_operation(operation),
            'six_handles_live':True,'cohorts':{n:selected[n]['cohort'] for n in selected},
            'dashboard_closure_not_inferred':True,'http_methods':['GET'],'provider_calls':0,'work_flow_constructed':False}
    finally:
        for group in handles.values():
            for handle in group.values():handle.close()

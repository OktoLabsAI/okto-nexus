"""One explicitly selected pre-Core denial; never a general failed-request refund."""
from pathlib import Path
import hashlib,json
from request_context import require,read_json,pin,reserve
HERE=Path(__file__).parent
DENIED='m1-sonnet-remote-useful-05'
OPEN='op_1792f89b9a964b184c4a408712467bb9'
TURN='op_fac0defdf8f8b4c1b95bd8c9f73a6076'
SESSION='ses_421253fe45b0d98592fede20d45c12b6'
IDS={'useful':'m1-sonnet-remote-useful-07','continuation':'m1-sonnet-remote-continuation-08'}
POLICY={'limit':500000,'preventive':480000,'native_max':4,'server_max':5,'new_native_max':2}

def validate_evidence(d,r,a,exits,selections):
    require(r.get('request_id')==a.get('request_id')==DENIED and r.get('state')=='RESERVED_BEFORE_CLI'
        and r.get('refund_allowed') is False,'EXACT_CONSUMED_DENIAL05_REQUIRED')
    require(a.get('operation_id')==TURN and a.get('session_id')==SESSION,'DENIAL_ADMISSION_CHANGED')
    receipt=a.get('receipt',{})
    require(receipt.get('operation_id')==OPEN and receipt.get('client_intent_id')==DENIED
        and receipt.get('submission_turn_operation_id')==TURN and receipt.get('scope',{}).get('session_id')==SESSION,
        'DENIAL_OPEN_SCOPE_CHANGED')
    rows={x['operation_id']:x for x in d.get('operations',[])}
    require(set(rows)=={OPEN,TURN} and all(x.get('session_id')==SESSION and x.get('admission_state')=='RESOLVED_TERMINAL' for x in rows.values())
        and rows[OPEN].get('action')=='runtime.open' and rows[TURN].get('action')=='turn.submit','DENIAL_TERMINAL_SCOPE_REQUIRED')
    dispatch={x['operation_id']:x for x in d.get('dispatch',[])}
    require(set(dispatch)=={OPEN,TURN},'DENIAL_DISPATCH_PROOF_REQUIRED')
    for op,code in ((OPEN,'PERMISSION_DENIED'),(TURN,'INITIAL_OPEN_FAILED')):
        row=dispatch[op];error=row.get('error',{})
        require(row.get('dispatch_state')=='RESOLVED_TERMINAL' and error.get('stage')=='dispatch'
            and error.get('code')==code and error.get('possible_effect') is False
            and error.get('retry_safe') is False,'POSITIVE_NEVER_DISPATCHED_DENIAL_REQUIRED')
    require(d.get('receipts')==[] and d.get('event_count')==0 and d.get('core_operations')==[]
        and d.get('core_launches')==[] and d.get('core_events')==0,'CORE_OR_STREAM_ACTIVITY_NOT_ZERO')
    sessions=d.get('session',[])
    require(len(sessions)==1 and sessions[0].get('session_id')==SESSION and sessions[0].get('lifecycle_state')=='FAILED'
        and sessions[0].get('lease_state')=='NONE' and sessions[0].get('stream_epoch') is None,'NULL_STREAM_FAILED_SESSION_REQUIRED')
    require(exits.get('physical_exit_confirmed') is True and exits.get('force_used') is False
        and set(exits.get('cohorts',{}))==set(exits.get('exits',{}))=={'nexus','connector'},'SIX_PHYSICAL_EXITS_REQUIRED')
    for component in ('nexus','connector'):
        chosen=selections[component];cohort=chosen['cohort']
        require(exits['cohorts'][component]['cohort']==cohort,'EXIT_COHORT_CHANGED')
        group=exits['exits'][component];require(set(group)=={'parent','launcher','child'},'ALL_ROLES_REQUIRED')
        for role in group:
            actual=group[role];expected=cohort[role]
            require(actual.get('physical_exit') is True and actual.get('exit_code')==0
                and actual.get('pid')==expected['pid'] and actual.get('birth')==expected['birth'],'PHYSICAL_EXIT_IDENTITY_CHANGED')
    return {'kind':'ZERO_EFFECT_DISPATCH_DENIAL','request_id':DENIED,'server_admission_consumed':True,
        'native_forwarded_or_uncertain':False,'new_tokens_observed':0,'synthetic_stream_or_ledger_created':False,
        'operation_id':OPEN,'follow_up_operation_id':TURN,'session_id':SESSION}

def selected_proof(selection):
    require(selection.get('kind')=='ROOT_TECHNICAL_SELECTION_NOT_NEW_USER_RESPONSE'
        and selection.get('policy')==POLICY and selection.get('request_ids')==IDS
        and selection.get('carry')=={'tokens':144004,'native_historical':2,'server_historical':3},'COUNTER_SELECTION_CHANGED')
    authority=read_json(pin(selection['user_authorization']))
    require(authority.get('explicit_user_approval') is True and authority.get('carry_tokens')==144004
        and authority.get('charged_requests')==2 and authority.get('new_requests_max')==2
        and authority.get('policy')=={'limit':500000,'preventive':480000,'max_requests':4},'ORIGINAL_USER_AUTHORITY_CHANGED')
    proposal=read_json(pin(selection['selected_proposal']));refs=proposal['evidence']
    paid=read_json(pin(selection['denied_paid_plan']))
    require(selection['denied_paid_plan']['sha256']=='0f70f46dd7b4a2cefd083ecf6a83dcea896b1c3b612ed5ff99f073c39ef46be3'
        and paid['request_ids']['useful']==DENIED,'DENIED_PAID_PLAN_CHANGED')
    namespace=Path(paid['successor']['namespace']).resolve()
    require(Path(refs['reserved_attempt']['path']).resolve()==namespace/'private'/(DENIED+'-reserved.json')
        and Path(refs['admission']['path']).resolve()==namespace/'private'/(DENIED+'-admission.json')
        and Path(refs['six_physical_exit']['path']).resolve()==namespace/'public/paid-work-exit-proof.json',
        'DENIAL_EVIDENCE_NAMESPACE_CHANGED')
    d=read_json(pin(refs['diagnosis']));r=read_json(pin(refs['reserved_attempt']));a=read_json(pin(refs['admission']))
    exits=read_json(pin(refs['six_physical_exit']))
    selections={c:read_json(pin(selection['predecessor_selections'][c])) for c in ('nexus','connector')}
    expected_scope=read_json(pin(paid['prerequisites']['completed_profile']))['remote_scope']
    actual_scope=a.get('receipt',{}).get('scope',{})
    require(all(actual_scope.get(k)==expected_scope[k] for k in ('server_id','executor_id','agent_id','binding_id','workspace_id','workspace_binding_id'))
        and actual_scope.get('credential_epoch')==2,'DENIAL_PAID_SCOPE_CHANGED')
    for c in ('nexus','connector'):
        original=paid['prerequisites'][c+'_selection'];selected=selection['predecessor_selections'][c]
        require(all(original[k]==selected[k] for k in ('path','sha256')),'DENIAL_PREDECESSOR_SELECTION_CHANGED')
        pin(original)
        watch=read_json(pin(paid['prerequisites'][c+'_watch_started']))
        require(watch.get('cohort')==selections[c]['cohort']
            and watch.get('lifecycle_plan_sha256')==selections[c].get('lifecycle_plan_sha256')==paid['recovery_plan']['sha256'],
            'DENIAL_ORIGINAL_WATCH_COHORT_CHANGED')
    return validate_evidence(d,r,a,exits,selections)

def validate_receipt(plan):
    selection=read_json(pin(plan['counter_selection']));expected=selected_proof(selection)
    receipt=read_json(pin(plan['typed_denial05']))
    require(receipt.get('facts')==expected and receipt.get('root_selection_sha256')==plan['counter_selection']['sha256'],
        'TYPED_DENIAL_RECEIPT_CHANGED')
    from sonnet_usage import restore_budget
    seed=restore_budget(read_json(pin(plan['budget_seed'])))
    old_ids=[rid for item in seed.sessions.values() for rid in item.reserved]
    history=read_json(pin(plan['server_admission_history']))
    require(len(old_ids)==2 and history.get('server_admissions_consumed')==3
        and history.get('native_forwarded_or_uncertain')==2
        and history.get('rows')==[{'request_id':rid,'server_admission_consumed':True,'native_forwarded_or_uncertain':True} for rid in old_ids]
            +[{'request_id':DENIED,'server_admission_consumed':True,'native_forwarded_or_uncertain':False,
                'typed_denial_sha256':plan['typed_denial05']['sha256']}], 'HISTORICAL_SERVER_ADMISSIONS_CHANGED')
    return receipt

def counts(private,request=None):
    paths=list(Path(private).glob('server-attempt-*.json'))
    allowed=set(IDS.values());seen=set()
    for path in paths:
        value=read_json(path);rid=value.get('request_id')
        ordinal=4 if rid==IDS['useful'] else 5
        require(rid in allowed and rid not in seen and path.name=='server-attempt-'+rid+'.json'
            and value.get('state')=='NEW_NATIVE_FORWARDED_OR_UNCERTAIN'
            and value.get('server_admission_consumed') is True and value.get('native_charge_upper_bound')==1
            and value.get('server_ordinal')==ordinal and value.get('native_upper_bound')==ordinal-1
            and value.get('denial05_receipt_sha256')==hashlib.sha256((HERE/'typed-denial05.json').read_bytes()).hexdigest(),
            'SERVER_ATTEMPT_HISTORY_CHANGED')
        seen.add(rid)
    require(IDS['continuation'] not in seen or IDS['useful'] in seen,'CONTINUATION_WITHOUT_USEFUL_ATTEMPT')
    require(len(seen)<=2 and 3+len(seen)<=5 and 2+len(seen)<=4,'DUAL_COUNTER_LIMIT')
    if request is not None:
        require(request in allowed and request not in seen,'SERVER_OR_NATIVE_REQUEST_REPLAY')
        require(len(seen)<2,'NEW_NATIVE_ALLOCATION_EXHAUSTED')
        require(request!=IDS['continuation'] or IDS['useful'] in seen,'CONTINUATION_WITHOUT_USEFUL_ATTEMPT')
    return {'server_admissions':3+len(seen),'native_forwarded_or_uncertain':2+len(seen),'new_attempts':len(seen),'new_request_ids':sorted(seen)}

def reserve_attempt(plan,private,request,budget):
    validate_receipt(plan);before=counts(private,request)
    require((budget.limit,budget.preventive,budget.max_requests)==(500000,480000,4),'NATIVE_POLICY_CHANGED')
    value={'request_id':request,'state':'NEW_NATIVE_FORWARDED_OR_UNCERTAIN','server_admission_consumed':True,
        'native_charge_upper_bound':1,'refund_allowed':False,'denial05_receipt_sha256':plan['typed_denial05']['sha256'],
        'server_ordinal':before['server_admissions']+1,'native_upper_bound':before['native_forwarded_or_uncertain']+1}
    reserve(Path(private)/('server-attempt-'+request+'.json'),value)
    return value

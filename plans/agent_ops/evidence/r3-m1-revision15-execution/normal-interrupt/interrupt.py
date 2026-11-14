"""One exact canonical turn interrupt during drain; no approval, new turn, force or accounting edit."""
from pathlib import Path
from types import SimpleNamespace
import argparse,hashlib,json,sys,time
HERE=Path(__file__).resolve().parent
BASE=Path('C:/Users/jpamb/AppData/Local/Temp/m1-v12-bundle-bldo9qy7/successor14/work-revision15')
sys.path.insert(0,str(BASE))
PREFIX='/api/v1/runtime-management'
def require(value,code):
    if not value:raise RuntimeError(code)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_bytes())
def metadata(value):
    return {k:value[k] for k in ('scope','operation_id','client_intent_id','action','intent_hash','admission_state',
        'receipt_revision','possible_effect','retry_safe','executor_stage','resolution_revision','session_id','can_submit','blockers','semantic_intent') if k in value}

def execute(context,m,http,handles,save):
    from cohort import cycle,same_cycle
    expected=m['owner'];scope=m['scope']
    def boundary():
        require(not any(h.exited() for h in handles),'COHORT_EXITED_OR_CHANGED')
        same_cycle(expected['cohort'],cycle(context))
        service=http('GET','/api/v1/service')['data']
        require(all(service.get(k)==expected[k] for k in ('pid','generation','instance_id'))
            and service.get('state') == 'stopping' and service.get('ready_for_queries') is True,
            'EXACT_QUERY_READY_OWNER_REQUIRED')
        require(not any(h.exited() for h in handles),'COHORT_EXIT_DURING_OBSERVATION')
    boundary()
    session=http('GET',PREFIX+'/runtime/sessions/'+scope['session_id']+'?executor_id='+scope['executor_id'])
    require(session.get('scope')==scope and session.get('lease_state') in ('ACTIVE','REVOKED'),'EXACT_SESSION_REQUIRED')
    operation=http('GET',PREFIX+'/runtime/operations/'+m['operation_id'])
    require(operation.get('scope')==scope and operation.get('operation_id')==m['operation_id']
        and operation.get('action')=='turn.submit' and operation.get('admission_state') in ('ACCEPTED','DISPATCHED')
        and operation.get('executor_stage') not in ('SUCCEEDED','FAILED','CANCELLED'),'EXACT_ACTIVE_OPERATION_REQUIRED')
    request={k:scope[k] for k in ('agent_id','binding_id','workspace_binding_id','session_id')}
    request.update(client_intent_id=m['control_request_id'],intent='turn.interrupt',
        target={'kind':'native_turn_id','expected_turn_id':m['native_turn_id']})
    save('resolve-reserved',{'request':request,'operation_before':metadata(operation)})
    boundary()
    resolved=http('POST',PREFIX+'/runtime/intents:resolve',request)
    save('resolved',metadata(resolved))
    require(resolved.get('scope')==scope and resolved.get('client_intent_id')==request['client_intent_id']
        and resolved.get('session_id')==scope['session_id']
        and resolved.get('semantic_intent',{}).get('action')=='turn.interrupt'
        and resolved.get('semantic_intent',{}).get('target')==request['target']
        and resolved.get('can_submit') is True and resolved.get('blockers')==[], 'INTERRUPT_RESOLUTION_CHANGED')
    admission={key:resolved[key] for key in ('client_intent_id','operation_id','resolution_revision','intent_hash')}
    save('admit-reserved',admission)
    boundary()
    value=http('POST',PREFIX+'/runtime/operations',admission)
    save('admitted',metadata(value))
    require(value.get('scope')==scope and value.get('operation_id')==admission['operation_id']
        and value.get('intent_hash')==admission['intent_hash'] and value.get('action')=='turn.interrupt',
        'INTERRUPT_ADMISSION_CHANGED')
    return {'status':'INTERRUPT_ADMITTED_NOT_YET_SETTLED','operation':metadata(value),
        'model_admissions':0,'native_decisions':0,'force_used':False,'physical_exit_inferred':False}

def main():
    p=argparse.ArgumentParser();p.add_argument('--manifest-sha256',required=True);args=p.parse_args()
    require(sha(HERE/'manifest.json')==args.manifest_sha256,'MANIFEST_CHANGED');m=read(HERE/'manifest.json')
    for pin in [*m['sources'].values(),*m['before'].values()]:require(sha(pin['path'])==pin['sha256'],'PIN_CHANGED')
    from request_context import gate
    context=gate(SimpleNamespace(amendment=m['amendment']['path'],expected_amendment_sha256=m['amendment']['sha256']))
    cp_path=BASE/'private/controller.json'
    cp_raw=cp_path.read_bytes();cp=json.loads(cp_raw);record=cp['requests']['m1v15-local-useful-13']
    stop=read(m['before']['normal_stop']['path'])
    require(stop.get('state')=='RETURNED' and stop.get('action')=='stop' and stop.get('component')=='nexus'
        and stop.get('returncode')==3 and stop.get('reported_state')=='stopping'
        and stop.get('wait_timed_out') is True,'NORMAL_STOP_DRAIN_REQUIRED')
    require(record['session']==m['scope']['session_id'] and record['operation']==m['operation_id'],'REQUEST_CHANGED')
    matching=[v for v in cp['collector']['state']['turns'].values() if v['operation_id']==m['operation_id']
        and v['started'] and not v['terminal']]
    require(len(matching)==1 and matching[0]['turn_id']==m['native_turn_id'],'EXACT_NATIVE_TURN_REQUIRED')
    from cohort import Process
    from okto_nexus.adapters.outbound.terminal_http import LocalOperatorHTTP
    handles=[];ledger=HERE/'runtime';ledger.mkdir(exist_ok=True)
    def save(name,value):context.common.reserve(ledger/(name+'.json'),{**context.common.tags(context),**value,'time':time.time()})
    try:
        for role in ('parent','launcher','child'):
            expected=m['owner']['cohort'][role];h=Process(expected['pid']);handles.append(h)
            require(h.birth==expected['birth'] and not h.exited(),'COHORT_BIRTH_CHANGED')
            require(h.image in context.installed['python_images'] and sha(h.image)==context.installed['python_images'][h.image],
                'COHORT_IMAGE_CHANGED')
        save('execute-reserved',{'manifest_sha256':args.manifest_sha256,
            'controller_concurrent_before_sha256':hashlib.sha256(cp_raw).hexdigest(),
            'controller_may_continue_observation':True,'maximum_resolve_posts':1,
            'maximum_admission_posts':1,'model_admissions':0,'native_decisions':0,'force_used':False})
        try:result=execute(context,m,LocalOperatorHTTP(host='127.0.0.1',port=58631,timeout=10),handles,save)
        except BaseException as error:
            save('execute-result',{'status':'INTERRUPT_UNCONFIRMED','error_type':type(error).__name__,
                'code':getattr(error,'code',None),'automatic_retry':False,'possible_effect':'CONSULT_RESERVED_LEDGER'})
            raise
        finally:
            save('controller-concurrent-after',{'sha256':sha(cp_path),'controller_may_continue_observation':True})
            for pin in m['before'].values():require(sha(pin['path'])==pin['sha256'],'STATIC_BASIS_CHANGED')
        save('execute-result',result);print(json.dumps(result));return 0
    finally:
        for h in handles:h.close()
if __name__=='__main__':raise SystemExit(main())

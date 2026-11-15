"""One canonical Claude current_run interruption, using installed CLI handler."""
import json
import os
import time
from concurrent.futures import TimeoutError
from pathlib import Path
from sonnet_usage import Unknown,require

class PendingWorker(Unknown):
    def __init__(self,future):super().__init__('WORKER_UNCONFIRMED');self.future=future

def wait(worker,fn,*args,timeout=30,**kwargs):
    future=worker.submit(fn,*args,**kwargs)
    try:return future.result(timeout=timeout)
    except TimeoutError:raise PendingWorker(future) from None

def once(path,value):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('x',encoding='utf-8',newline='\n') as f:
        json.dump(value,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())

def interrupt_current(*,flow,worker,scope,operation_id,owner_observation,reservation_path,request_id):
    """Caller serializes all CLI work. No target substitution or POST retry."""
    owner=owner_observation()
    identity=owner.get('identity')
    require(owner.get('identity_matches') is True and type(identity) is dict
        and all(identity.get(k) is not None for k in ('pid','birth','generation')),'OWNER_IDENTITY_UNCONFIRMED')
    binding=wait(worker,flow.binding)
    op=wait(worker,flow.operation,operation_id,binding)
    require(op.get('operation_id')==operation_id and all(op.get('scope',{}).get(k)==v for k,v in scope.items() if k!='stream_epoch'),'INTERRUPT_SCOPE_CHANGED')
    if op.get('executor_stage') in ('SUCCEEDED','FAILED','CANCELLED') or op.get('admission_state')=='RESOLVED_TERMINAL':
        return {'state':'ALREADY_TERMINAL','operation_id':operation_id,'posts':0}
    session=wait(worker,flow.session,binding,scope['session_id'])
    require(session.get('lifecycle_state')=='READY' and session.get('scope',{}).get('session_id')==scope['session_id'],'INTERRUPT_SESSION_UNCONFIRMED')
    generation=op.get('scope',{}).get('session_owner_generation')
    require(type(generation) is int and session.get('scope',{}).get('session_owner_generation')==generation,'SESSION_OWNER_CHANGED_BEFORE_CONTROL')
    after=owner_observation()
    require(after.get('identity_matches') is True and after.get('identity')==identity,'OWNER_CHANGED_BEFORE_CONTROL')
    once(reservation_path,{'kind':'EXACT_CURRENT_RUN_INTERRUPT','operation_id':operation_id,'scope':scope,
        'request_id':request_id,'owner':owner,'time':time.time(),'maximum_resolve_posts':1,'maximum_admit_posts':1})
    # Installed TerminalWork maps Claude interrupt to current_run. No native ID
    # is fabricated; this campaign has one selected active operation, no queue.
    result=wait(worker,flow._execute,'interrupt',['--session-id',scope['session_id'],'--request-id',request_id],'submit')
    return {'state':'INTERRUPT_RETURNED_NOT_PHYSICAL_EXIT','receipt':result,'operation_id':operation_id}

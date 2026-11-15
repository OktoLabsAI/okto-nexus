"""Finite remote work using installed CLIFlow and campaign-only Claude accounting.

No effect on import. Context supplies reviewed remote identities and lifecycle;
this executable never creates accounts, credentials or starts services itself.
"""
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor,TimeoutError
from pathlib import Path
from urllib.parse import quote
from sonnet_usage import Ledger,CampaignBudget,AdmissionMonitor,Unknown,require,project,checkpoint_budget,restore_budget
from observe_active import observe_active
from activecontrol import once,wait,PendingWorker,interrupt_current

def atomic(path,value):
    p=Path(path);pending=p.with_suffix('.pending')
    with pending.open('w',encoding='utf-8',newline='\n') as f:
        json.dump(value,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
    os.replace(pending,p)

def reserve_before_dispatch(budget,phase,request_id,path):
    value={'request_id':request_id,'phase':phase,'state':'RESERVED_BEFORE_CLI',
        'budget':budget.check_admission(phase),'reserved_at_monotonic':time.monotonic(),'refund_allowed':False}
    once(path,value);return value

def effect_transport(call,state,*,clock=time.monotonic):
    def guarded(method,path,body=None):
        if method!='GET' and not state['containment']:
            monitor=state['monitor'];now=clock()
            observed=monitor.observed_at if monitor is not None else state['started']
            require(observed is not None and 0<=now-observed<=20,'EFFECT_OBSERVATION_STALE')
            require(now-state['started']<600,'EFFECT_DEADLINE')
            require(state['budget'].known<state['budget'].preventive and all(not item.faults for item in state['budget'].sessions.values()),'EFFECT_ADMISSION_CLOSED')
        return call(method,path,body)
    return guarded

def bind_receipt(receipt,expected_scope,request_id):
    require(type(receipt) is dict and receipt.get('operation_id'),'ADMISSION_RECEIPT_REQUIRED')
    scope=receipt.get('scope',{})
    require(all(scope.get(k)==v for k,v in expected_scope.items()),'ADMISSION_SCOPE_CHANGED')
    require(isinstance(scope.get('session_id'),str) and bool(scope['session_id']),'SESSION_REQUIRED')
    # Runtime.open initial text has a distinct initial-turn operation. No guessed ID.
    operation=receipt.get('submission_turn_operation_id') or receipt['operation_id']
    return operation,scope['session_id']

def recover_receipt(flow,worker,request,phase):
    recovered=wait(worker,flow.api,'GET','/runtime/intents/'+quote(request,safe=''))
    resolution=recovered.get('resolution',{});operation=recovered.get('operation')
    require(type(operation) is dict,'SUBMISSION_UNKNOWN_NO_REPLAY')
    require(resolution.get('client_intent_id')==request and resolution.get('operation_id')==operation.get('operation_id')
        and resolution.get('intent_hash')==operation.get('intent_hash'),'RECOVERY_CORRELATION_CHANGED')
    receipt=dict(operation)
    if phase=='useful':
        child=recovered.get('initial_turn_operation_id')
        require(isinstance(child,str) and bool(child),'INITIAL_TURN_UNCONFIRMED')
        receipt['submission_turn_operation_id']=child
    return receipt

def select_decision(choice,items,*,root,operator,worker,session):
    """An unchanged durable selection is observed, never dispatched again."""
    if choice is None:return
    approval=choice['approval_id']
    require(isinstance(approval,str) and approval and all(c.isalnum() or c in '_-' for c in approval),'APPROVAL_ID_INVALID')
    reserved=Path(root)/(approval+'-decision-reserved.json')
    returned=Path(root)/(approval+'-decision-returned.json')
    if reserved.exists():
        require(json.loads(reserved.read_bytes())==choice,'DECISION_SELECTION_CHANGED')
        require(returned.exists(),'DECISION_RETURN_UNCONFIRMED_NO_REPLAY')
        return
    # A stale file from another completed question is not a new selection.
    if not any(item.get('approval_id')==approval for item in items):return
    require(len(list(Path(root).glob('*-decision-reserved.json')))<3,'DECISION_ALLOCATION_EXHAUSTED')
    require(choice['decision'] in ('approve','deny'),'DECISION_INVALID')
    once(reserved,choice)
    result=wait(worker,operator.decide,approval,choice['decision'],reviewed_revision=choice['review_revision'],session_id=session)
    once(returned,result)

def first_stream(flow,worker,session,operation,binding,deadline,*,clock=time.monotonic,sleep=time.sleep):
    """Only passive reads while runtime.open establishes its event stream."""
    while clock()<deadline:
        value=wait(worker,flow.events,session_id=session,after_sequence=0,timeout=min(19,max(.01,deadline-clock())))
        page=value['events'];epoch=page.get('stream_epoch')
        require(not page.get('gap_pending'),'CANONICAL_EVENT_GAP')
        if isinstance(epoch,str) and epoch:return value
        op=wait(worker,flow.operation,operation,binding,timeout=min(19,max(.01,deadline-clock())))
        require(op.get('executor_stage') not in ('SUCCEEDED','FAILED','CANCELLED') and op.get('admission_state')!='RESOLVED_TERMINAL','TERMINAL_WITHOUT_USAGE_STREAM')
        sleep(.2)
    raise Unknown('STREAM_OBSERVATION_DEADLINE')

def terminal_operation(flow,worker,operation,binding,deadline,*,clock=time.monotonic,sleep=time.sleep):
    while clock()<deadline:
        value=wait(worker,flow.operation,operation,binding,timeout=min(19,max(.01,deadline-clock())))
        if value.get('executor_stage') in ('SUCCEEDED','FAILED','CANCELLED') or value.get('admission_state')=='RESOLVED_TERMINAL':return value
        sleep(.2)
    raise Unknown('CANONICAL_TERMINAL_UNCONFIRMED')

def run(X,phase):
    require(phase in ('useful','continuation'),'WORK_PHASE_INVALID');X.require_ready()
    request=X.request_ids[phase];root=Path(X.PRIVATE);public=Path(X.PUBLIC)
    budget_path=root/'sonnet-budget.json'
    require(budget_path.is_file(),'MANDATORY_RECONCILED_BUDGET_MISSING')
    budget=restore_budget(json.loads(budget_path.read_bytes()))
    X.validate_budget(budget)
    if phase=='continuation':
        prior=json.loads((public/(X.request_ids['useful']+'-result.json')).read_bytes())
        require(prior.get('useful_result_confirmed') is True and prior.get('terminal_observed') is True,'USEFUL_RESULT_REQUIRED')
    # Unfinished reservation files are never treated as absent or automatically retried.
    X.require_prior_reservations_closed(request)
    budget.check_admission(phase)
    X.reserve_server_attempt(request,budget)
    reservation=reserve_before_dispatch(budget,phase,request,root/(request+'-reserved.json'))
    flow=X.work_flow();operator=X.operator_flow();worker=ThreadPoolExecutor(max_workers=1,thread_name_prefix='sonnet-cli')
    pending_handoff=False;pending_worker=None;ledger=None;monitor=None;outcome=None;operation=None;scope=None;stop_selected=False
    effect_state={'monitor':None,'containment':False,'budget':budget,'started':reservation['reserved_at_monotonic']}
    flow.call=effect_transport(flow.call,effect_state)
    operator.call=effect_transport(operator.call,effect_state)
    def retain(future,summary):
        nonlocal pending_handoff,pending_worker
        pending_worker=future
        try:
            proof=X.handoff(future,summary)
            require(isinstance(proof,dict) and proof.get('retained') is True,'RETAINED_OWNER_HANDOFF_UNCONFIRMED')
        except Exception:
            atomic(root/(request+'-handoff-unconfirmed.json'),{'state':'HANDOFF_UNCONFIRMED','worker_pending':bool(future is not None and not future.done()),'admission_closed':True,'transfer_confirmed':False})
            if future is not None and not future.done():
                # Keep the original worker and this process; no concurrent stop.
                # If this bounded wait expires, shutdown(wait=True) below retains
                # the worker rather than pretending ownership was transferred.
                try:future.result(timeout=180)
                except TimeoutError:pass
                except Exception:pass
            raise
        pending_handoff=True
        return proof
    def contain(selected_scope,selected_operation):
        effect_state['containment']=True
        try:return interrupt_current(flow=operator,worker=worker,scope=selected_scope,operation_id=selected_operation,
            owner_observation=X.owner_observation,reservation_path=root/(request+'-interrupt-reserved.json'),request_id=request+'-interrupt')
        finally:effect_state['containment']=False
    def close_controls():
        nonlocal stop_selected
        if pending_handoff or stop_selected or pending_worker is not None and not pending_worker.done():return
        stop_selected=True
        try:
            stopped=X.normal_stop()
        except Exception:
            retain(None,{'request_id':request,'state':'NORMAL_STOP_UNCONFIRMED'});return
        if not isinstance(stopped,dict) or stopped.get('physical_exit_confirmed') is not True:
            retain(None,{'request_id':request,'state':'NORMAL_STOP_NOT_PHYSICALLY_CONFIRMED'})
    try:
        X.require_ready()
        try:
            receipt=wait(worker,flow.submit,X.prompts[phase],client_intent_id=request,new_session=phase=='useful')
        except PendingWorker as error:
            retain(error.future,{'request_id':request,'state':'SUBMISSION_UNCONFIRMED','budget':reservation['budget']});raise
        except Exception:
            # Exact GET-only recovery. Never TerminalWork.resume, which can admit.
            receipt=recover_receipt(flow,worker,request,phase)
        operation,session=bind_receipt(receipt,X.expected_scope,request)
        scope={k:receipt['scope'][k] for k in ('server_id','executor_id','session_id')}
        if phase=='continuation':require(session==prior['session_id'],'CONTINUATION_SESSION_CHANGED')
        once(root/(request+'-admission.json'),{'request_id':request,'operation_id':operation,'session_id':session,'receipt':receipt})
        # First page binds the durable stream; any unknown return remains charged.
        binding=wait(worker,flow.binding)
        first=first_stream(flow,worker,session,operation,binding,reservation['reserved_at_monotonic']+600)
        page=first['events'];epoch=page.get('stream_epoch')
        require(isinstance(epoch,str) and bool(epoch) and not page.get('gap_pending'),'STREAM_NOT_CONFIRMED')
        scope['stream_epoch']=epoch
        key=tuple(scope[k] for k in ('server_id','executor_id','session_id','stream_epoch'))
        ledger=budget.sessions.get(key)
        if ledger is None:ledger=Ledger(scope,limit=budget.limit,preventive=budget.preventive,max_requests=budget.max_requests);budget.attach(ledger)
        # Allocation was durably reserved before submit; this binds that one charge.
        budget.reserve(ledger,operation,phase=phase)
        monitor=AdmissionMonitor(ledger,time.monotonic,budget=budget)
        effect_state['monitor']=monitor
        monitor.started_at=reservation['reserved_at_monotonic'];monitor.observed()
        def publish(summary):
            atomic(budget_path,checkpoint_budget(budget));X.publish(dict(summary,campaign_observed_tokens=budget.known))
        def pending(value):
            items=value.get('requests',{}).get('items',[])
            X.publish_pending(items,session)
            decision_root=root/(request+'-decisions');decision_root.mkdir(exist_ok=True)
            select_decision(X.selected_decision(),items,root=decision_root,operator=operator,worker=worker,session=session)
        # Replay first page through the same collector; no raw output is retained.
        for event in page['events']:ledger.ingest(project(event))
        publish(ledger.summary())
        if ledger.active is None:outcome={'state':'TERMINAL_OBSERVED','summary':ledger.summary()}
        else:outcome=observe_active(flow=flow,worker=worker,ledger=ledger,monitor=monitor,owner_observation=X.owner_observation,
            interrupt=contain,publish=publish,retain_handoff=retain,on_page=pending)
        terminal=outcome['state']=='TERMINAL_OBSERVED'
        if not terminal:close_controls()
        canonical=terminal_operation(flow,worker,operation,binding,reservation['reserved_at_monotonic']+600) if terminal else None
        succeeded=bool(terminal and ledger.finished[-1]['outcome']=='success' and canonical.get('executor_stage')=='SUCCEEDED')
        useful=bool(succeeded and X.verify_useful()) if phase=='useful' else None
        result={'request_id':request,'operation_id':operation,'session_id':session,'terminal_observed':terminal,
            'useful_result_confirmed':useful,'summary':ledger.summary(),'campaign_observed_tokens':budget.known,
            'canonical_succeeded':succeeded,'canonical_executor_stage':canonical.get('executor_stage') if canonical else None,
            'state':outcome['state'],'no_atomic_token_cap_claim':True}
        once(public/(request+'-result.json'),result);return result
    except PendingWorker as error:
        if not pending_handoff:retain(error.future,{'request_id':request,'state':'WORKER_UNCONFIRMED'})
        raise
    except Exception as error:
        # Preserve original primary exception. Context retains exact owner handles
        # and executes only its reviewed normal containment, never force/replay.
        if ledger is not None and 'WORK_OBSERVATION_UNKNOWN' not in ledger.faults:ledger.faults.append('WORK_OBSERVATION_UNKNOWN')
        if not pending_handoff and (pending_worker is None or pending_worker.done()):
            try:
                if operation and scope and not (root/(request+'-interrupt-reserved.json')).exists():contain(scope,operation)
            except PendingWorker as control_error:retain(control_error.future,{'request_id':request,'state':'CONTROL_UNCONFIRMED','primary_error_type':type(error).__name__})
            except Exception:
                # Exact identity uncertainty forbids interrupt; retain it as unknown.
                pass
            close_controls()
        raise
    finally:
        if ledger is not None:atomic(budget_path,checkpoint_budget(budget))
        worker.shutdown(wait=not pending_handoff,cancel_futures=False)

if __name__=='__main__':
    from remote_context import load
    context=load();run(context,context.remaining[0])

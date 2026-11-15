"""Executable active observation using existing installed CLIFlow, no new admission.

Caller supplies the admitted exact operation/scope and one serial worker; this
module never invokes setup/send/start. Root selection and canonical receipt must
precede it. Optional controls are only exact-current-operation containment.
"""
from concurrent.futures import TimeoutError
import time
from sonnet_usage import Unknown,project
from fast_approval import exception_metadata

def observe_active(*,flow,worker,ledger,monitor,owner_observation,interrupt,
                   publish,clock=time.monotonic,sleep=time.sleep,max_seconds=600,
                   pending_wait_seconds=180,retain_handoff=None,on_page=None,error_sink=None):
    started=monitor.started_at if monitor.started_at is not None else clock()
    cursor=ledger.cursor;selected=ledger.active
    if selected is None:raise Unknown('ADMITTED_OPERATION_REQUIRED')
    while clock()-started<max_seconds:
        tick=clock()
        if monitor.observed_at is None or tick-monitor.observed_at>monitor.freshness:
            ledger.faults.append('OBSERVATION_STALE')
            break
        pending=worker.submit(flow.events,session_id=ledger.scope['session_id'],
                              stream_epoch=ledger.scope['stream_epoch'],after_sequence=cursor)
        callback_stage="events_wait"
        try:
            value=pending.result(timeout=min(19,max(.01,max_seconds-(clock()-started))))
            page=value['events']
            if page.get('gap_pending'):raise Unknown('CANONICAL_EVENT_GAP')
            callback_stage='event_ingest'
            for event in page['events']:ledger.ingest(project(event))
            cursor=ledger.cursor;monitor.observed();publish(ledger.summary())
            if ledger.active is None:
                if clock()-started>=max_seconds:
                    ledger.faults.append('EXECUTION_DEADLINE');publish(ledger.summary())
                    return {'state':'TERMINAL_OBSERVED_AFTER_DEADLINE','summary':ledger.summary()}
                return {'state':'TERMINAL_OBSERVED','summary':ledger.summary()}
            current=ledger.known if monitor.budget is None else monitor.budget.known
            threshold=ledger.preventive if monitor.budget is None else monitor.budget.preventive
            callback_stage='page_callback'
            if on_page is not None and not ledger.faults and current<threshold and clock()-started<max_seconds:on_page(value)
        except Exception as error:
            if error_sink is not None:
                try:error_sink(exception_metadata(error,callback_stage))
                except Exception:pass  # Evidence IO must not bypass containment.
            pending=getattr(error,'future',pending)
            if 'ACTIVE_OBSERVATION_UNKNOWN' not in ledger.faults:ledger.faults.append('ACTIVE_OBSERVATION_UNKNOWN')
            publish(ledger.summary())
            if not pending.done():
                # No other CLI/POST while this worker may still execute. The
                # process stays here through a bounded observation window.
                wait_end=clock()+pending_wait_seconds
                while not pending.done() and clock()<wait_end:
                    try:pending.result(timeout=min(1,max(.01,wait_end-clock())))
                    except TimeoutError:continue
                    except Exception:break
                if not pending.done():
                    if retain_handoff is None:raise Unknown('RETAINED_OWNER_HANDOFF_REQUIRED')
                    proof=retain_handoff(pending,ledger.summary())
                    if not isinstance(proof,dict) or proof.get('retained') is not True:
                        raise Unknown('RETAINED_OWNER_HANDOFF_UNCONFIRMED')
                    return {'state':'WORKER_UNCONFIRMED_RETAINED_HANDOFF','future':pending,'handoff':proof,'summary':ledger.summary()}
        observed=ledger.known if monitor.budget is None else monitor.budget.known
        threshold=ledger.preventive if monitor.budget is None else monitor.budget.preventive
        if monitor.observed_at is None or clock()-monitor.observed_at>monitor.freshness:
            if 'OBSERVATION_STALE' not in ledger.faults:ledger.faults.append('OBSERVATION_STALE')
        if ledger.faults or observed>=threshold or clock()-started>=max_seconds:
            owner=owner_observation()
            control=monitor.containment(canonical_operation=owner.get('operation_id'),
                owner_matches=owner.get('identity_matches') is True,
                select_interrupt=lambda scope,op:interrupt(scope,op))
            publish(ledger.summary())
            return {'state':'OBSERVATION_FAULT','control':control,'summary':ledger.summary()}
        # A target interval, not a promise that IO can meet it. All page paths
        # cross the same accounting/deadline gate before another read.
        sleep(max(0,.2-(clock()-tick)))
    if clock()-started>=max_seconds:ledger.faults.append('EXECUTION_DEADLINE')
    owner=owner_observation()
    control=monitor.containment(canonical_operation=owner.get('operation_id'),
        owner_matches=owner.get('identity_matches') is True,select_interrupt=interrupt)
    publish(ledger.summary())
    return {'state':'DEADLINE','control':control,'summary':ledger.summary()}

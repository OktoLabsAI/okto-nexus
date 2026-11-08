"""Retained transfer worker; only the calling thread may poll or touch Controller."""
from dataclasses import dataclass, field
import queue
import re
import threading
import time


@dataclass
class _Gate:
    phase: str
    answer: bool = False
    ready: threading.Event = field(default_factory=threading.Event)


class RemoteTransferRefused(RuntimeError):
    pass


def public_transfer_result(result):
    """Closed nonsecret projection; terminal text/unknown helper fields are dropped."""
    selected={}
    for key in ('status','reason','error_type'):
        value=result.get(key)
        if type(value) is str and re.fullmatch('[A-Za-z_][A-Za-z0-9_]{0,95}',value):
            selected[key]=value
    for key in ('producer_started','consumer_started','delivery_attempted','possible_effect',
                'possible_consumer_effect','consumer_io_completed','forced_owned_cleanup',
                'worker_assigned_before_gate','producer_alive_at_consumer_start',
                'consumer_ready_marker_observed','material_block_observed',
                'material_seen_before_ready_marker','material_in_public_result',
                'material_in_argv_or_env','consumer_did_not_echo','effect_guard_required',
                'public_ipc_readers_joined','worker_stderr_observed'):
        value=result.get(key)
        if value is None or type(value) is bool:selected[key]=value
    for key in ('worker_pid','worker_birth_filetime','producer_exit','consumer_exit','worker_exit',
                'consumer_start_count','active_job_processes_after'):
        value=result.get(key)
        if type(value) is int and -(2**31)<=value<2**64:selected[key]=value
    for key in ('producer','consumer'):
        value=result.get(key)
        if type(value) is not dict:continue
        pid,born,member=value.get('pid'),value.get('birth_filetime'),value.get('exact_job_member')
        if type(pid) is int and 0<pid<2**32 and type(born) is int and 0<born<2**64 and type(member) is bool:
            selected[key]={'pid':pid,'birth_filetime':born,'exact_job_member':member}
    for key in ('effect_gates_requested','effect_gates_allowed'):
        value=result.get(key)
        if type(value) is list and len(value)<=2 and all(p in ('producer','consumer') for p in value):
            selected[key]=list(value)
    value=result.get('effect_guard_decisions')
    if type(value) is list and len(value)<=2:
        decisions=[]
        for item in value:
            if type(item) is not dict or item.get('phase') not in ('producer','consumer') or type(item.get('allowed')) is not bool:
                continue
            entry={'phase':item['phase'],'allowed':item['allowed']}
            if item.get('deadline_expired') is True:entry['deadline_expired']=True
            error=item.get('error_type')
            if type(error) is str and re.fullmatch('[A-Za-z_][A-Za-z0-9_]{0,95}',error):entry['error_type']=error
            decisions.append(entry)
        selected['effect_guard_decisions']=decisions
    return selected


def transfer_with_monitor(*, controller, transfer, poll, timeout_seconds=120,
                          clock=time.monotonic, interval=.2):
    """No admission or HTTP here. `transfer` receives only an effect_guard callback.

    The callback queues public phases; the owner refreshes observation before
    approving each phase. A selected fault/deadline is permanent for this call.
    The worker is always joined; an OS stall is not claimed to have a hard bound.
    """
    if type(timeout_seconds) not in (int, float) or not 0 < timeout_seconds <= 120:
        raise ValueError('REMOTE_TRANSFER_DEADLINE_INVALID')
    if not 0 < interval <= .2:
        raise ValueError('REMOTE_TRANSFER_POLL_INTERVAL_INVALID')
    owner=threading.get_ident()
    deadline=clock()+timeout_seconds
    requests=queue.Queue(maxsize=1)
    cancelled=threading.Event()
    dispatch_closed=threading.Event()
    done=threading.Event()
    private={}
    gates=[]
    metadata={'poll_count':0,'maximum_poll_start_interval_seconds':0,
              'maximum_poll_duration_seconds':0,'cadence_miss':False,
              'phase_deadline_monotonic':deadline,
              'observation_error_type':None,'worker_error_type':None,
              'deadline_exceeded':False,'worker_joined':False,'gates':gates,
              'fault_persistence_error_type':None,'effect_grants':0}
    previous=None
    fault_selected=False

    def select_fault(code):
        nonlocal fault_selected
        assert threading.get_ident()==owner
        cancelled.set()
        if not fault_selected:
            fault_selected=True
            try:controller.fault(code)
            except BaseException as error:
                metadata['fault_persistence_error_type']=type(error).__name__

    def fresh_poll():
        nonlocal previous
        assert threading.get_ident()==owner
        now=clock()
        if previous is not None:
            metadata['maximum_poll_start_interval_seconds']=max(
                metadata['maximum_poll_start_interval_seconds'],now-previous)
            if now-previous>1 and now<deadline:
                metadata['cadence_miss']=True
                select_fault('REMOTE_MONITOR_CADENCE_EXCEEDED')
        previous=now
        metadata['poll_count']+=1
        summary=poll()
        ended=clock()
        metadata['maximum_poll_duration_seconds']=max(metadata['maximum_poll_duration_seconds'],ended-now)
        if ended-now>1 and ended<deadline:
            metadata['cadence_miss']=True
            select_fault('REMOTE_MONITOR_CADENCE_EXCEEDED')
        return summary

    # This refuses before even invoking the auxiliary transfer helper.
    summary=fresh_poll()
    if cancelled.is_set() or summary.get('can_admit') is not True or summary.get('current') or clock()>=deadline:
        raise RemoteTransferRefused('REMOTE_TRANSFER_NOT_ADMISSIBLE')
    # A completed prior request's deadline is not the new nonproductive phase's
    # deadline. arm() refuses an already closed fence; it never clears a fault.
    controller.fence.arm(deadline)
    controller.fence.require('POST')
    if clock()>=deadline:
        raise RemoteTransferRefused('REMOTE_TRANSFER_DEADLINE')

    def effect_guard(phase):
        # No controller/checkpoint access is permitted on this worker thread.
        if cancelled.is_set() or dispatch_closed.is_set() or clock()>=deadline:
            return False
        gate=_Gate(phase if type(phase) is str and phase in ('producer','consumer') else 'INVALID')
        try:requests.put_nowait(gate)
        except queue.Full:return False
        while not gate.ready.wait(.05):
            if cancelled.is_set() or dispatch_closed.is_set() or clock()>=deadline:
                return False
        return gate.answer is True and not cancelled.is_set() and not dispatch_closed.is_set() and clock()<deadline

    def work():
        try:private['result']=transfer(effect_guard=effect_guard,deadline_monotonic=deadline)
        except BaseException as error:
            # Keep no raw exception message/trace, material or terminal text.
            private['error_type']=type(error).__name__
        finally:done.set()

    worker=threading.Thread(target=work,name='m1-remote-transfer',daemon=False)
    try:
        worker.start()
        while True:
            try:
                try:summary=fresh_poll()
                except BaseException as error:
                    metadata['observation_error_type']=type(error).__name__
                    summary={}
                    select_fault('REMOTE_OBSERVATION_UNCONFIRMED')
                if clock()>=deadline:
                    metadata['deadline_exceeded']=True
                    select_fault('REMOTE_TRANSFER_DEADLINE')
                elif summary.get('can_admit') is not True or summary.get('current'):
                    select_fault('REMOTE_TRANSFER_BLOCKED')
                try:gate=requests.get_nowait()
                except queue.Empty:gate=None
                if gate is not None:
                    expected=('producer','consumer')[len(gates)] if len(gates)<2 else None
                    approved=False
                    if gate.phase!=expected:
                        select_fault('REMOTE_TRANSFER_GATE_SEQUENCE')
                    elif not cancelled.is_set():
                        # A fresh owner observation was taken directly above. The
                        # fence and deadline are rechecked at the grant boundary.
                        try:
                            controller.fence.require('POST')
                            approved=clock()<deadline
                        except BaseException as error:
                            metadata['observation_error_type']=type(error).__name__
                            select_fault('REMOTE_TRANSFER_FENCE_CLOSED')
                    gates.append({'phase':gate.phase,'approved':approved})
                    gate.answer=approved
                    metadata['effect_grants']+=int(approved)
                    gate.ready.set()
                if done.is_set():
                    break
                done.wait(interval)
            except BaseException as error:
                metadata['observation_error_type']=type(error).__name__
                select_fault('REMOTE_TRANSFER_MONITOR_EXCEPTION')
                # Never abandon a possibly admitted transfer/owned helper worker.
    finally:
        dispatch_closed.set()
        # Resolve all pending callbacks even after cancellation outside a tick.
        # Retain the worker and keep owner observation alive until it returns.
        while worker.ident is not None and not done.is_set():
            try:
                select_fault('REMOTE_TRANSFER_MONITOR_EXCEPTION')
                try:fresh_poll()
                except BaseException as error:metadata['observation_error_type']=type(error).__name__
                while True:
                    try:pending=requests.get_nowait()
                    except queue.Empty:break
                    pending.answer=False;pending.ready.set()
                done.wait(interval)
            except BaseException as error:
                metadata['observation_error_type']=type(error).__name__
                cancelled.set()
        while True:
            try:pending=requests.get_nowait()
            except queue.Empty:break
            pending.answer=False;pending.ready.set()
        if worker.ident is not None:
            worker.join()
            metadata['worker_joined']=True
    metadata['worker_error_type']=private.get('error_type')
    metadata['fence_selected']=cancelled.is_set()
    metadata['ordered_effect_gates_passed']=(gates==[
        {'phase':'producer','approved':True},{'phase':'consumer','approved':True}])
    result=private.get('result')
    if type(result) is not dict:
        result={'status':'TRANSFER_UNCONFIRMED','possible_effect':True,
                'error_type':private.get('error_type','InvalidTransferResult')}
    return result,metadata

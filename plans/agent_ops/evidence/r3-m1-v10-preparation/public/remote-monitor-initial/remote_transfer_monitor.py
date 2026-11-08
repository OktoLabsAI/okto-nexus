"""Retained transfer worker; only the calling thread may poll or touch Controller."""
from dataclasses import dataclass, field
import queue
import threading
import time


@dataclass
class _Gate:
    phase: str
    answer: bool = False
    ready: threading.Event = field(default_factory=threading.Event)


class RemoteTransferRefused(RuntimeError):
    pass


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
    done=threading.Event()
    private={}
    gates=[]
    metadata={'poll_count':0,'maximum_poll_start_interval_seconds':0,
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
        previous=now
        metadata['poll_count']+=1
        return poll()

    # This refuses before even invoking the auxiliary transfer helper.
    summary=fresh_poll()
    if summary.get('can_admit') is not True or summary.get('current') or clock()>=deadline:
        raise RemoteTransferRefused('REMOTE_TRANSFER_NOT_ADMISSIBLE')
    controller.fence.require('POST')
    if clock()>=deadline:
        raise RemoteTransferRefused('REMOTE_TRANSFER_DEADLINE')

    def effect_guard(phase):
        # No controller/checkpoint access is permitted on this worker thread.
        if cancelled.is_set() or clock()>=deadline:
            return False
        gate=_Gate(phase if type(phase) is str and phase in ('producer','consumer') else 'INVALID')
        try:requests.put_nowait(gate)
        except queue.Full:return False
        while not gate.ready.wait(.05):
            if cancelled.is_set() or clock()>=deadline:
                return False
        return gate.answer is True and not cancelled.is_set() and clock()<deadline

    def work():
        try:private['result']=transfer(effect_guard=effect_guard)
        except BaseException as error:
            # Keep no raw exception message/trace, material or terminal text.
            private['error_type']=type(error).__name__
        finally:done.set()

    worker=threading.Thread(target=work,name='m1-remote-transfer',daemon=False)
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

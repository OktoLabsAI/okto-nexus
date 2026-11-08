"""Synthetic threads only: no helper process, product, provider, service or vault."""
import importlib.util
import json
from pathlib import Path
import sys
import threading

import pytest

spec=importlib.util.spec_from_file_location('remote_transfer_monitor',Path(__file__).with_name('remote_transfer_monitor.py'))
m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)


class Controller:
    def __init__(self):
        self.owner=threading.get_ident()
        self.closed=False
        self.faults=[]
        self.fence=self
        self.checks=[]
    def require(self,verb):
        assert threading.get_ident()==self.owner
        self.checks.append(verb)
        if self.closed:raise RuntimeError('FENCE_CLOSED')
    def fault(self,code):
        assert threading.get_ident()==self.owner
        self.closed=True;self.faults.append(code)


def ready():return {'can_admit':True,'current':None}


def test_both_gates_refresh_on_owner_and_join_exact_worker():
    c=Controller();poll_threads=[];workers=[];phases=[]
    def poll():
        poll_threads.append(threading.get_ident());return ready()
    def transfer(*,effect_guard):
        workers.append(threading.current_thread())
        for phase in ('producer','consumer'):
            phases.append((phase,effect_guard(phase)))
        return {'status':'TRANSFERRED_ONCE'}
    result,proof=m.transfer_with_monitor(controller=c,transfer=transfer,poll=poll,interval=.001)
    assert result['status']=='TRANSFERRED_ONCE'
    assert phases==[('producer',True),('consumer',True)]
    assert set(poll_threads)=={c.owner} and workers[0].ident!=c.owner
    assert not workers[0].is_alive() and proof['worker_joined']
    assert proof['ordered_effect_gates_passed'] and proof['effect_grants']==2


@pytest.mark.parametrize('summary',[{'can_admit':False,'current':None},{'can_admit':True,'current':'previous'},{}])
def test_initial_fresh_refusal_never_calls_transfer(summary):
    called=[]
    with pytest.raises(m.RemoteTransferRefused):
        m.transfer_with_monitor(controller=Controller(),transfer=lambda **kw:called.append(kw),poll=lambda:summary)
    assert called==[]


def test_late_usage_selects_one_fault_and_denies_consumer_without_replay():
    c=Controller();producer_admitted=threading.Event();calls=[];grants=[]
    def poll():
        return {'can_admit':not producer_admitted.is_set(),'current':None}
    def transfer(*,effect_guard):
        calls.append('once')
        grants.append(effect_guard('producer'))
        producer_admitted.set()
        grants.append(effect_guard('consumer'))
        return {'status':'UNCONFIRMED','producer_started':True,'consumer_started':False,'possible_effect':True}
    result,proof=m.transfer_with_monitor(controller=c,transfer=transfer,poll=poll,interval=.001)
    assert grants==[True,False] and calls==['once']
    assert result['possible_effect'] and not result['consumer_started']
    assert c.faults==['REMOTE_TRANSFER_BLOCKED'] and proof['fence_selected']


@pytest.mark.parametrize('phases',[('consumer',),('producer','producer'),('unexpected',)])
def test_out_of_order_duplicate_or_unknown_phase_is_denied(phases):
    c=Controller();answers=[]
    def transfer(*,effect_guard):
        answers.extend(effect_guard(p) for p in phases)
        return {'status':'UNCONFIRMED'}
    _,proof=m.transfer_with_monitor(controller=c,transfer=transfer,poll=ready,interval=.001)
    assert answers[-1] is False
    assert c.faults==['REMOTE_TRANSFER_GATE_SEQUENCE']
    assert not proof['ordered_effect_gates_passed'] and proof['worker_joined']


def test_owner_continues_poll_and_retains_worker_after_observation_exception():
    c=Controller();entered=threading.Event();release=threading.Event();workers=[];after_failure=[]
    def poll():
        if entered.is_set():
            after_failure.append(1)
            if len(after_failure)==1:raise OSError('synthetic private message must not be published')
            if len(after_failure)==4:release.set()
        return ready()
    def transfer(*,effect_guard):
        workers.append(threading.current_thread())
        assert effect_guard('producer')
        entered.set()
        assert release.wait(2),'owner abandoned pump'
        assert not effect_guard('consumer')
        return {'status':'UNCONFIRMED','possible_effect':True}
    _,proof=m.transfer_with_monitor(controller=c,transfer=transfer,poll=poll,interval=.001)
    assert len(after_failure)>=4 and not workers[0].is_alive()
    assert c.faults==['REMOTE_OBSERVATION_UNCONFIRMED']
    assert proof['observation_error_type']=='OSError'
    assert 'synthetic private' not in json.dumps(proof)


def test_worker_exception_message_is_not_copied_to_metadata():
    c=Controller()
    def transfer(*,effect_guard):
        assert effect_guard('producer')
        raise ValueError('private material that is never included in output')
    result,proof=m.transfer_with_monitor(controller=c,transfer=transfer,poll=ready,interval=.001)
    assert result=={'status':'TRANSFER_UNCONFIRMED','possible_effect':True,'error_type':'ValueError'}
    assert proof['worker_error_type']=='ValueError' and proof['worker_joined']
    assert 'private material' not in json.dumps([result,proof])


def test_deadline_after_producer_refuses_consumer_and_joins():
    c=Controller();ticks=[0.0];producer=threading.Event();grants=[]
    def clock():return ticks[0]
    def poll():
        if producer.is_set():ticks[0]=2.0
        return ready()
    def transfer(*,effect_guard):
        grants.append(effect_guard('producer'));producer.set()
        grants.append(effect_guard('consumer'))
        return {'status':'UNCONFIRMED','consumer_started':False}
    _,proof=m.transfer_with_monitor(controller=c,transfer=transfer,poll=poll,clock=clock,timeout_seconds=1,interval=.001)
    assert grants==[True,False]
    assert proof['deadline_exceeded'] and proof['worker_joined']
    assert c.faults==['REMOTE_TRANSFER_DEADLINE']


def test_failed_fault_persistence_does_not_reopen_gate_or_abandon_worker():
    c=Controller();producer=threading.Event();grants=[]
    def failing_fault(code):
        assert threading.get_ident()==c.owner
        raise OSError('synthetic checkpoint failure')
    c.fault=failing_fault
    def transfer(*,effect_guard):
        grants.append(effect_guard('producer'));producer.set()
        grants.append(effect_guard('consumer'))
        return {'status':'UNCONFIRMED'}
    result,proof=m.transfer_with_monitor(controller=c,transfer=transfer,
        poll=lambda:{'can_admit':not producer.is_set(),'current':None},interval=.001)
    assert grants==[True,False] and result['status']=='UNCONFIRMED'
    assert proof['fault_persistence_error_type']=='OSError' and proof['worker_joined']

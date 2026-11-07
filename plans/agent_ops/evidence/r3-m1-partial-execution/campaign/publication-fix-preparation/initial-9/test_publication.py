import pytest
from publication import publish_live,poll_and_publish

class Clock:
    def __init__(self):self.now=0
    def clock(self):return self.now
    def sleep(self,seconds):self.now+=seconds

def denied(code=5):
    error=PermissionError('synthetic publication collision')
    error.winerror=code
    return error

@pytest.mark.parametrize('code',[5,32])
def test_transient_windows_error_recovers_bounded(code):
    clock=Clock();calls=[];stats={}
    def write(value):
        calls.append(value)
        if len(calls)<3:raise denied(code)
    assert publish_live(write,{'count':1},stats,clock=clock.clock,sleep=clock.sleep)
    assert len(calls)==3 and clock.now==.02
    assert stats['windows_publication_errors']==2 and stats['published_snapshots']==1

@pytest.mark.parametrize('code',[5,32])
def test_persistent_public_failure_keeps_polling_and_budget_stop(code):
    clock=Clock();stats={};writes=[]
    class Controller:
        polls=0
        def poll(self):
            self.polls+=1
            total=self.polls*50000
            return {'known_observed_tokens':total,'can_admit':total<100000,'stop_selected':total>=100000}
    controller=Controller()
    def write(value):writes.append(value);raise denied(code)
    first=poll_and_publish(controller,write,stats,'own',clock=clock.clock,sleep=clock.sleep)
    second=poll_and_publish(controller,write,stats,'own',clock=clock.clock,sleep=clock.sleep)
    assert first['can_admit'] and second['stop_selected'] and not second['can_admit']
    assert controller.polls==2 and stats['deferred_snapshots']==2
    assert clock.now<=.161 and len(writes)>=2
    # A later poll can publish the current state; no old snapshot replaces it.
    final=[]
    third=poll_and_publish(controller,final.append,stats,'own',clock=clock.clock,sleep=clock.sleep)
    assert third['known_observed_tokens']==150000 and final[0]['summary']==third

@pytest.mark.parametrize('failure',[denied(5),RuntimeError('critical checkpoint unavailable')])
def test_critical_poll_failure_is_not_swallowed(failure):
    class Controller:
        def poll(self):raise failure
    published=[];stats={}
    with pytest.raises(type(failure)) as raised:
        poll_and_publish(Controller(),published.append,stats,'own')
    assert raised.value is failure and not published and not stats

@pytest.mark.parametrize('failure',[denied(13),OSError('disk full'),ValueError('invalid diagnostic serialization')])
def test_other_publication_errors_propagate(failure):
    clock=Clock();stats={}
    def write(value):raise failure
    with pytest.raises(type(failure)) as raised:
        publish_live(write,{},stats,clock=clock.clock,sleep=clock.sleep)
    assert raised.value is failure and clock.now==0 and stats['attempts']==1

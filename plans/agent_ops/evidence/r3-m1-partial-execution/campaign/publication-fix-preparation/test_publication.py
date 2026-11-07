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

def test_real_windows_read_handle_denies_replace_but_budget_monitor_continues(tmp_path):
    import ctypes,json,os,time
    from ctypes import wintypes
    path=tmp_path/'live.json'; pending=tmp_path/'live.pending'
    path.write_text(json.dumps({'old':True}))
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.CreateFileW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,wintypes.LPVOID,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE]
    kernel.CreateFileW.restype=wintypes.HANDLE
    kernel.CloseHandle.argtypes=[wintypes.HANDLE];kernel.CloseHandle.restype=wintypes.BOOL
    handle=kernel.CreateFileW(str(path),0x80000000,3,None,3,128,None)
    assert handle not in (None,ctypes.c_void_p(-1).value)
    class Controller:
        polls=1
        def poll(self):
            self.polls+=1
            return {'known_observed_tokens':self.polls*50000,'stop_selected':self.polls>=2,'can_admit':self.polls<2}
    controller=Controller();stats={};delays=[]
    def write(value):
        pending.write_text(json.dumps(value))
        os.replace(pending,path)
    def sleep(seconds):delays.append(seconds);time.sleep(seconds)
    try:
        summary=poll_and_publish(controller,write,stats,'owned-win32-test',sleep=sleep)
        assert summary['stop_selected'] and not summary['can_admit']
        assert controller.polls==2 and stats['deferred_snapshots']==1
        assert stats['last_winerror'] in (5,32) and sum(delays)<=.080001
        assert json.loads(path.read_text())=={'old':True}
    finally:
        assert kernel.CloseHandle(handle)
    latest=poll_and_publish(controller,write,stats,'owned-win32-test')
    assert controller.polls==3 and latest['known_observed_tokens']==150000
    assert json.loads(path.read_text())['summary']==latest
    assert stats['published_snapshots']==1

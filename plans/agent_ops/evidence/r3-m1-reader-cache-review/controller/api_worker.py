"""Single serialized API worker fenced by the one global controller authority.

No alternate token ledger, baseline reset, CLI, HTTP, provider, credential or
service implementation lives here. The caller supplies the canonical flow.
"""
import threading
import time

from observation_guard import FailureHistory
from independent_journal import require


class Fenced(RuntimeError):
    pass


class EffectFence:
    def __init__(self,clock=time.monotonic):
        self.event=threading.Event()
        self.clock=clock;self.deadline=None;self.known_tokens=0;self.threshold=200000
        self.lock=threading.Lock();self.reason=None

    def arm(self,deadline):
        with self.lock:
            if self.event.is_set():raise Fenced('EFFECTS_FENCED')
            self.deadline=deadline

    def accounting(self,total):
        with self.lock:
            if total<self.known_tokens:raise Fenced('USAGE_REGRESSION')
            self.known_tokens=total
            if total>=self.threshold:self.reason='PREVENTIVE_THRESHOLD';self.event.set()

    def close(self):self.event.set()

    def require(self,method):
        if method=='GET':return
        with self.lock:
            # Recheck at every actual effect boundary, even if the owner tick
            # was delayed. A request already in flight is not cancelled/replayed.
            if self.deadline is not None and self.clock()>=self.deadline:
                self.reason='DEADLINE120';self.event.set()
            if self.known_tokens>=self.threshold:
                self.reason='PREVENTIVE_THRESHOLD';self.event.set()
            if self.event.is_set():raise Fenced('EFFECTS_FENCED')


class SerialAPI:
    """Exactly one worker task, no pending queue, one owner consumes its result."""
    def __init__(self,fence):
        self.fence=fence
        self.owner=threading.get_ident()
        self.thread=None
        self.done=threading.Event()
        self.result=None
        self.history=FailureHistory()
        self.history_lock=threading.Lock()
        self.started=0

    def owned(self):require(threading.get_ident()==self.owner,'API_OWNER_CHANGED')

    def transport(self,raw):
        def call(method,path,body=None):
            require(self.thread is threading.current_thread(),'API_OUTSIDE_SERIAL_WORKER')
            self.fence.require(method)
            try:return raw(method,path,body)
            except Exception as error:
                with self.history_lock:self.history.record(error,method,path)
                raise
        return call

    def submit(self,label,job,*,productive=False):
        self.owned()
        require(self.thread is None,'API_TASK_ALREADY_IN_FLIGHT')
        if productive:self.fence.require('POST')
        self.done.clear();self.result=None;self.started+=1
        def run():
            try:self.result={'label':label,'ok':True,'value':job()}
            except BaseException as error:
                # Retain the exception object privately; never serialize its message/body.
                self.result={'label':label,'ok':False,'error':error}
            finally:self.done.set()
        self.thread=threading.Thread(target=run,name='m1-serial-api')
        self.thread.start()

    def take(self):
        self.owned()
        if self.thread is None or not self.done.is_set():return None
        self.thread.join();self.thread=None
        result,self.result=self.result,None
        return result

    def diagnostics(self):
        with self.history_lock:return self.history.snapshot()



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
        self.clock=clock;self.deadline=None;self.known_tokens=0;self.threshold=500000
        self.lock=threading.Lock();self.reason=None
        self.observation_required=False;self.fresh_until=None;self.poll_deadline=None
        self.observation_updated=threading.Event();self.dispatched_effects=0
        self.freshness_waits=0
        self.before_first_effect=None

    def begin_poll(self,started,budget):
        with self.lock:self.poll_deadline=started+budget

    def end_poll(self,started,successful):
        with self.lock:
            self.poll_deadline=None
            if successful:self.fresh_until=started+1
        self.observation_updated.set()

    def arm(self,deadline):
        with self.lock:
            if self.event.is_set():raise Fenced('EFFECTS_FENCED')
            self.deadline=deadline

    def accounting(self,total):
        with self.lock:
            if total<self.known_tokens:raise Fenced('USAGE_REGRESSION')
            self.known_tokens=total
            if total>=self.threshold:self.reason='PREVENTIVE_THRESHOLD';self.event.set()

    def close(self):
        self.event.set();self.observation_updated.set()

    def require(self,method,*,wait_for_fresh=False,observation=True):
        if method=='GET':return
        while True:
            # The API worker may wait; the owner remains free to poll.
            self.observation_updated.clear()
            with self.lock:
                now=self.clock()
                if self.deadline is not None and now>=self.deadline:
                    self.reason='DEADLINE600';self.event.set()
                if self.known_tokens>=self.threshold:
                    self.reason='PREVENTIVE_THRESHOLD';self.event.set()
                if self.observation_required and observation:
                    if self.poll_deadline is not None and now>=self.poll_deadline:
                        self.reason='OBSERVATION_POLL_BUDGET_EXCEEDED';self.event.set()
                if self.event.is_set():raise Fenced('EFFECTS_FENCED')
                stale=(observation and self.observation_required
                       and (self.fresh_until is None or now>=self.fresh_until))
                if not stale:return
                if not wait_for_fresh:raise Fenced('FRESH_OBSERVATION_REQUIRED')
                self.freshness_waits+=1
            # No HTTP has been entered. Poll success wakes this worker; hard
            # deadline/token/fault limits remain checked during every wait.
            self.observation_updated.wait(.05)

    def dispatch_boundary(self,method):
        self.require(method,wait_for_fresh=True)
        if method!='GET':
            if self.dispatched_effects==0 and self.before_first_effect is not None:
                # A sole worker reserves its first dispatch durably. The callback
                # cannot submit HTTP and must finish before freshness is rechecked.
                deadline=self.before_first_effect(self.clock())
                with self.lock:self.deadline=deadline
                self.require(method,wait_for_fresh=True)
            with self.lock:self.dispatched_effects+=1


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
            self.fence.dispatch_boundary(method)
            try:return raw(method,path,body)
            except Exception as error:
                with self.history_lock:self.history.record(error,method,path)
                raise
        return call

    def submit(self,label,job,*,productive=False):
        self.owned()
        require(self.thread is None,'API_TASK_ALREADY_IN_FLIGHT')
        if productive:self.fence.require('POST',observation=False)
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



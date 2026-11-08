"""Select normal stops immediately, dispatch only after the transfer Job is empty.

The auxiliary Job does not own services. Job0 only excludes a still-running
consumer that could rewrite desired=running; canonical service exit is separate.
"""
from copy import deepcopy
import threading


class DeferredRemoteStops:
    def __init__(self, *, persist, dispatch, existing_receipt):
        self.owner=threading.get_ident()
        self.persist=persist;self.dispatch=dispatch;self.existing_receipt=existing_receipt
        self.data={'readiness_verified':False,'helper_started':False,
                   'helper_drained':False,'service_exit_confirmed':False,'stops':{}}

    def _save(self):
        assert threading.get_ident()==self.owner
        self.persist(deepcopy(self.data))

    def ready(self):
        self.data['readiness_verified']=True;self._save()

    def helper_started(self):
        self.data['helper_started']=True;self._save()

    def select(self,lane):
        assert lane in ('local','connector')
        if lane not in self.data['stops']:
            self.data['stops'][lane]={'state':'SELECTED_DEFERRED','force_used':False}
            self._save()
        return {'selected':True,'deferred':True,'service_exit_confirmed':False}

    def select_both(self):
        if self.data['readiness_verified']:
            for lane in ('local','connector'):self.select(lane)

    def finish(self,result=None,monitor=None):
        assert threading.get_ident()==self.owner
        if not self.data['helper_started']:
            drained=True;basis='HELPER_NOT_INVOKED'
        else:
            result=result or {};monitor=monitor or {}
            drained=(monitor.get('worker_joined') is True
                and result.get('worker_assigned_before_gate') is True
                and type(result.get('worker_exit')) is int
                and type(result.get('active_job_processes_after')) is int
                and result['active_job_processes_after']==0
                and result.get('public_ipc_readers_joined') is True)
            basis='OWNED_HELPER_JOB_EMPTY' if drained else 'HELPER_JOB_UNCONFIRMED'
        self.data['helper_drained']=drained;self.data['drain_basis']=basis;self._save()
        return drained

    def dispatch_selected(self):
        assert threading.get_ident()==self.owner
        if not self.data['helper_drained']:return
        for lane in ('local','connector'):
            record=self.data['stops'].get(lane)
            if not record or record['state']!='SELECTED_DEFERRED':continue
            if self.existing_receipt(lane):
                record['state']='EXISTING_RESERVATION_RECONCILE_ONLY';self._save();continue
            record['state']='DISPATCH_RESERVED';self._save()  # before Popen
            try:
                self.dispatch(lane)
                record['state']='WRAPPER_STARTED'
            except BaseException as error:
                record['state']='DISPATCH_UNCONFIRMED';record['error_type']=type(error).__name__
                self._save();raise
            self._save()

    def snapshot(self):return deepcopy(self.data)

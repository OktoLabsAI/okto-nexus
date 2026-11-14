"""Canonical flow facade: every API operation stays on the sole API worker.

The owner pumps global accounting while awaiting it. This is deliberately not a
retry wrapper. One callable is submitted once and its exception is re-raised.
"""
from copy import deepcopy
import time


class SerialFlow:
    READ_METHODS=frozenset(('binding','observe','events','operation','api','decision_detail','sessions','session'))

    def __init__(self,controller,flow,lane,poll,*,sleep=time.sleep):
        self.controller,self.flow,self.lane,self.poll=controller,flow,lane,poll
        self.sleep=sleep;self.sequence=0

    @property
    def document(self):
        if self.controller.api.thread is not None:raise RuntimeError('API_WORKER_OWNS_DOCUMENT')
        return deepcopy(self.flow.document)

    def _invoke(self,method,args,kwargs):
        self.sequence+=1
        label='observer-'+self.lane+'-'+method+'-'+str(self.sequence)
        job=lambda:getattr(self.flow,method)(*args,**kwargs)
        if method=='decide':self.controller.schedule_decision(label,job)
        else:
            if method not in self.READ_METHODS:raise ValueError('UNAPPROVED_FLOW_METHOD')
            if method=='api' and (not args or args[0]!='GET'):raise ValueError('READ_ONLY_API_REQUIRED')
            self.controller.schedule_read(label,job)
        while True:
            poll_started=time.monotonic()
            self.poll()
            result=self.controller.take_api_result()
            if result is not None:
                if result['label']!=label:raise RuntimeError('API_RESULT_MISMATCH')
                if not result['ok']:raise result['error']
                return result['value']
            self.sleep(max(0,.2-(time.monotonic()-poll_started)))

    def __getattr__(self,name):
        if name not in self.READ_METHODS|{'decide'}:raise AttributeError(name)
        return lambda *args,**kwargs:self._invoke(name,args,kwargs)

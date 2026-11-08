"""Existing global Controller ledger, with no HTTP on its accounting tick.

Setup and both work lanes retain one policy, ancestry, collector and reservation
map. API jobs use one separate worker; the owner alone changes controller state.
Containment selects each supplied normal owner-stop capability at most once.
"""
from copy import deepcopy
import threading
import time
import sqlite3

from legacy_controller import Controller as LegacyController, POLICY, ANCESTRY, Refused
import token_collector as tokens
import setup_journal
from api_worker import SerialAPI, EffectFence
from independent_journal import JournalUnknown


class Controller(LegacyController):
    def __init__(self,*args,monotonic=time.monotonic,**kwargs):
        self._owner=threading.get_ident()
        self._monotonic=monotonic
        self._last_poll=None
        self._max_poll_interval=0
        self._readers={};self._journals={}
        self.fence=EffectFence(monotonic);self.api=SerialAPI(self.fence)
        self.api_result=None
        super().__init__(*args,**kwargs)
        self.fence.accounting(self.summary()['known_observed_tokens'])

    def _owned(self):
        if threading.get_ident()!=self._owner:raise Refused('CONTROLLER_OWNER_CHANGED')

    def persist(self,accounting=None):
        self._owned()
        return super().persist(accounting)

    def drain_api(self):
        self._owned()
        # A returned stop wrapper is not proof of native exit. Keep the same
        # owner accounting tick while a retained bounded API task finishes;
        # never reintroduce a blocking join into an uncertain shutdown window.
        while self.api.thread is not None:
            try:self.poll()
            except BaseException as error:
                self.fence.close()
                self.close_error_type=type(error).__name__
                if self.api.done.is_set():
                    self.api_result=self.api.take()
            if self.api.thread is not None:time.sleep(.2)
        return self.api_result

    def close(self):
        self.drain_api()
        return super().close()

    def attach_observer(self,lane,canonical_reader,journal_reader):
        self._owned()
        if lane not in ('local','connector'):raise Refused('LANE_INVALID')
        if lane in self._readers:raise Refused('OBSERVER_ALREADY_ATTACHED')
        self._readers[lane]=canonical_reader;self._journals[lane]=journal_reader

    def attach_api_flow(self,lane,flow):
        self._owned()
        if lane in self.flows:raise Refused('FLOW_ALREADY_ATTACHED')
        flow.call=self.api.transport(flow.call)
        self.attach(lane,flow)

    def schedule_read(self,label,job):
        self._owned()
        if self.api_result is not None:raise Refused('API_RESULT_NOT_CONSUMED')
        self.api.submit(label,job)

    def schedule_decision(self,label,job):
        self._owned();self._require_authorized()
        if self.data['faults'] or self.fence.event.is_set():raise Refused('DECISION_FENCED')
        if self.api_result is not None:raise Refused('API_RESULT_NOT_CONSUMED')
        # The canonical flow still validates review revision, recipient and scope.
        self.api.submit(label,job,productive=True)

    def take_api_result(self):
        self._owned()
        value,self.api_result=self.api_result,None
        return value

    def _reserve(self,request_id,record):
        self._owned()
        super()._reserve(request_id,record)
        record['started_monotonic']=self._monotonic()
        self.fence.arm(record['started_monotonic']+POLICY['deadline_seconds'])

    def work(self,*args,**kwargs):
        raise Refused('USE_RESERVED_SERIAL_API_DISPATCH')

    def start_work(self,request_id,lane,text,*,binding,checkpoint,stage='useful_work'):
        self._owned();self._require_authorized()
        if self.api_result is not None or self.api.thread is not None:raise Refused('API_TASK_ALREADY_IN_FLIGHT')
        if lane not in self._readers or lane not in self._journals:raise Refused('OBSERVER_REQUIRED')
        scope={k:binding[k] for k in tokens.PRE_SCOPE}
        if scope!=self._readers[lane].pre_scope:raise Refused('OBSERVER_SCOPE_MISMATCH')
        # Positive canonical freshness before creating any new reservation/effect.
        if self._readers[lane].read(request_id) is not None:raise Refused('EXISTING_INTENT_NO_REPLAY')
        current_session=checkpoint.get('session_id')
        known=[key for key,stream in self.accounting['streams'].items() if stream['scope']['session_id']==current_session
               and all(stream['scope'][name]==value for name,value in scope.items())]
        if current_session is not None and (len(known)!=1 or self.accounting['streams'][known[0]]['retired']):
            raise Refused('SESSION_NOT_OWNED_BY_CONTROLLER')
        self._reserve(request_id,{'kind':'work','lane':lane,'stage':stage,'operation':None,'session':None,
            'stream':known[0] if known else None,'recover':False,'scope':scope,
            'actor_agent_id':self._readers[lane].actor_id})
        state,allowed=(tokens.reserve(self.accounting,request_id=request_id,stream=known[0],stage=stage) if known else
            tokens.prearm(self.accounting,request_id=request_id,scope=scope,stage=stage))
        if not allowed:
            self.fault('COLLECTOR_RESERVATION_REFUSED');raise Refused('COLLECTOR_RESERVATION_REFUSED')
        self.persist(state) # One global ledger durable before the sole API job.
        flow=self.flows[lane]
        self.api.submit(request_id,lambda:flow.submit(text,client_intent_id=request_id,new_session=not current_session),productive=True)

    def _collect_api(self):
        completed=self.api.take()
        if completed is None:return
        if self.api_result is not None:raise Refused('API_RESULT_OVERWRITE')
        self.api_result=completed
        request=self.data['requests'].get(completed['label'])
        if request is not None:
            request['api_returned']=True
            if not completed['ok']:
                error=completed['error'];request['recover']=True
                if getattr(error,'stage',None)=='m1_response_loss':
                    self.persist(tokens.response_lost(self.accounting,request_id=completed['label']))
                else:self.fault('WORK_RESPONSE_UNKNOWN')
        elif not completed['ok'] and getattr(completed['error'],'stage',None)!='m1_response_loss':
            self.fault('API_OBSERVATION_UNKNOWN')

    def _poll_work(self,request_id,record):
        if record['lane'] not in self._readers:raise Refused('OBSERVER_REQUIRED')
        observed=self._readers[record['lane']].read(request_id)
        if observed is None:return
        scope=observed['scope'];session=scope['session_id'];operation=observed['operation_id']
        if any(scope[k]!=v for k,v in record['scope'].items()):raise Refused('RECOVERY_SCOPE_MISMATCH')
        if record['session'] not in (None,session) or record['operation'] not in (None,operation):
            raise Refused('RECOVERY_ID_MISMATCH')
        record['session']=session;record['operation']=operation;record['recover']=False
        if observed['preopen_failed']:
            record['preopen_failure']={'opening_operation_id':observed['opening_operation_id'],
                'initial_turn_operation_id':operation,'code':'PREPARATION_FAILED','possible_effect':False,
                'useful_result_confirmed':False,'native_exit_confirmed':False,'billed_tokens':None}
            self.fault('WORK_OPEN_FAILED_BEFORE_STREAM')
            return
        after=self.accounting['streams'][record['stream']]['cursor'] if record['stream'] else 0
        page=self._journals[record['lane']].read(scope,after)
        if page is None:return
        canonical_epoch=(observed['session_state'] or {}).get('stream_epoch')
        if canonical_epoch is not None and canonical_epoch!=page['stream_epoch']:
            raise Refused('CANONICAL_CORE_EPOCH_MISMATCH')
        state=self.accounting
        if record['stream'] is None:
            native={event['payload'].get('thread_id') for event in page['events'] if event['payload'].get('thread_id')}
            if not native:return
            if len(native)!=1:raise Refused('AMBIGUOUS_NATIVE_THREAD')
            state=tokens.bind_stream(state,request_id=request_id,scope=scope,epoch=page['stream_epoch'],
                native_thread_id=native.pop(),baseline_total=0,baseline_basis='confirmed_fresh_thread')
            record['stream']=tokens.stream_id(scope,page['stream_epoch'])
        state=tokens.bind_operation(state,request_id=request_id,operation_id=operation)
        state=tokens.observe(state,stream=record['stream'],after_sequence=after,page=page)
        self.persist(state)
        receipt=observed['operation_receipt']
        record['settled']=(state['requests'][request_id]['state']=='settled_observed' and receipt is not None
            and receipt['stage'] in ('SUCCEEDED','FAILED','CANCELLED'))
        if record['settled']:
            record['canonical_stage']=receipt['stage']
            if receipt['stage']!='SUCCEEDED':self.fault('WORK_TERMINAL_FAILED')

    def _stop_owner_once(self,lane,reason):
        stops=self.data.setdefault('independent_owner_stops',{})
        if lane in stops:return
        stops[lane]={'reason':reason,'state':'DISPATCH_RESERVED','native_exit_confirmed':False,'force_used':False}
        self.persist() # Shared reservation for accounting, fault and deadline containment.
        try:
            self.stops[lane]() # Must only launch the retained normal-stop wrapper, not wait.
        except BaseException as error:
            stops[lane]['error_type']=type(error).__name__
            self.fault('OWNER_STOP_UNCONFIRMED')

    def poll(self):
        self._owned()
        now=self._monotonic()
        if self._last_poll is not None:
            gap=now-self._last_poll
            if gap<0:self.fault('CLOCK_REGRESSION')
            self._max_poll_interval=max(self._max_poll_interval,gap)
            if gap>1 and any(not r['settled'] for r in self.data['requests'].values()):
                self.fault('MONITOR_CADENCE_EXCEEDED')
        self._last_poll=now
        for record in self.data['requests'].values():
            if not record['settled'] and record.get('started_monotonic') is not None and now-record['started_monotonic']>=POLICY['deadline_seconds']:
                self.fault('DEADLINE120')
        if self.fence.event.is_set() and self.fence.reason:self.fault(self.fence.reason)
        self._collect_api()
        # Work API is never invoked in this loop. Setup retains its original
        # private setup-journal namespace and is not counted as Server history.
        for key,record in self.data['requests'].items():
            if not record['settled'] and record['lane'] not in self.stops:
                self.fault('OWNER_STOP_NOT_ATTACHED');raise Refused('OWNER_STOP_NOT_ATTACHED')
            try:
                if record['kind']=='setup':
                    related=[v['monitor'] for v in self.data['requests'].values() if v['kind']=='setup'
                        and v['monitor']['home']==record['monitor']['home']]
                    record['monitor']=setup_journal.poll(deepcopy(record['monitor']),
                        [v['journal'] for v in related if v['journal']],any(v['journal'] is None for v in related))
                    record['settled']=setup_journal.settled(record['monitor'])
                    if record['monitor']['terminal'] and not record['monitor']['usage_seen']:
                        self.fault('SETUP_TERMINAL_USAGE_MISSING')
                else:self._poll_work(key,record)
            except Exception as error:
                details={'exception_type':type(error).__name__}
                if isinstance(error,sqlite3.Error):
                    code=getattr(error,'sqlite_errorcode',None)
                    name=getattr(error,'sqlite_errorname',None)
                    if type(code) is int:details['sqlite_errorcode']=code
                    if name in ('SQLITE_BUSY','SQLITE_LOCKED','SQLITE_INTERRUPT','SQLITE_CORRUPT',
                                'SQLITE_NOTADB','SQLITE_IOERR','SQLITE_CANTOPEN','SQLITE_SCHEMA','SQLITE_ERROR'):
                        details['sqlite_errorname']=name
                if isinstance(error,(JournalUnknown,Refused)):
                    value=str(error)
                    if value and len(value)<=80 and all(c.isupper() or c.isdigit() or c=='_' for c in value):details['reason']=value
                record.setdefault('first_observation_error',details)
                self.fault('OBSERVATION_UNKNOWN')
        summary=self.summary();state=self.accounting
        if state['faults'] or any(v['gap'] for v in state['streams'].values()):self.fault('ACCOUNTING_UNKNOWN')
        if any(t['terminal'] and not t['usage_seen'] for t in state['turns'].values()):self.fault('WORK_TERMINAL_USAGE_MISSING')
        threshold=summary['known_observed_tokens']>=POLICY['preventive_cumulative_tokens']
        self.fence.accounting(summary['known_observed_tokens'])
        if threshold:self.fault('PREVENTIVE_THRESHOLD')
        expired=False
        for record in self.data['requests'].values():
            if not record['settled']:
                began=record.get('started_monotonic')
                if began is None or now<began:self.fault('REQUEST_CLOCK_UNCONFIRMED')
                elif now-began>=POLICY['deadline_seconds']:expired=True
        if expired:self.fault('DEADLINE120')
        if self.data['faults']:
            self.fence.close()
            reason=self.data['faults'][0]
            # Stop every attached owned lane with admitted history. Each exact
            # component shares its one reservation across all failure paths.
            for record in self.data['requests'].values():
                if not record['settled'] and record['stop_selected'] is None:
                    record['stop_selected']={'reason':reason,'action':'stop_owner'}
            self.persist()
            for lane in sorted({r['lane'] for r in self.data['requests'].values()}):
                if lane in self.stops:self._stop_owner_once(lane,reason)
        self.data['independent_observation']={'maximum_poll_start_interval_seconds':self._max_poll_interval,
            'transport_failures':self.api.diagnostics(),'source':'CORE_LOCAL_PROJECTION_NOT_SERVER_PUBLICATION',
            'worker_in_flight':self.api.thread is not None}
        self.persist()
        return self.summary()

"""Finite serial campaign control; supplied transports retain authentication.

No provider launcher, credentials, service registration or automatic approval.
Caller must poll at <=1s while effects can be active. Only own canonical work
controls or an exact pre-reviewed owner service stop callback may be selected.
"""
from copy import deepcopy
import json
import os
from pathlib import Path
import time
from urllib.parse import quote
import msvcrt

import token_collector as tokens
import setup_journal
from okto_nexus.application.terminal_connection import ConnectionError


class Refused(RuntimeError):
    pass


class Controller:
    def __init__(self, path, campaign_root, *, create=False, clock=time.time):
        self.path, self.root, self.clock = Path(path), Path(campaign_root).resolve(), clock
        self.flows, self.stops = {}, {}
        self._lock = self.path.with_name(self.path.name+'.lock').open('a+b')
        if self._lock.tell()==0:
            self._lock.write(b'0'); self._lock.flush()
        self._lock.seek(0)
        try: msvcrt.locking(self._lock.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:
            self._lock.close(); self._lock=None
            raise Refused('CONTROLLER_ALREADY_OWNED') from None
        if create:
            self.data = {'format':1, 'collector': tokens.checkpoint(tokens.initial_state()),
                         'requests':{}, 'owners':{}, 'faults':[], 'last_clock':clock()}
            with self.path.open('x', encoding='utf-8') as stream:
                json.dump(self.data, stream)
                stream.flush(); os.fsync(stream.fileno())
        self.raw = self.path.read_bytes()
        self.data = json.loads(self.raw)
        tokens.restore(self.data['collector'])
        if self.data.get('format') != 1 or len(self.data['requests']) > 6:
            raise Refused('CONTROLLER_STATE_INVALID')

    def close(self):
        if self._lock is not None:
            self._lock.close(); self._lock=None

    def __del__(self):
        if getattr(self,'_lock',None) is not None: self.close()

    @property
    def accounting(self):
        return tokens.restore(self.data['collector'])

    def persist(self, accounting=None):
        if self._lock is None: raise Refused('CONTROLLER_NOT_OWNED')
        if self.path.read_bytes() != self.raw:
            raise Refused('CONTROLLER_CHANGED')
        if accounting is not None:
            self.data['collector'] = tokens.checkpoint(accounting)
        raw = (json.dumps(self.data, sort_keys=True, indent=2)+'\n').encode()
        pending = self.path.with_name(self.path.name+'.pending')
        with pending.open('xb') as stream:
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        os.replace(pending, self.path)
        self.raw = raw

    def fault(self, reason):
        if reason not in self.data['faults']:
            self.data['faults'].append(reason)
        self.persist()

    def summary(self):
        work = tokens.summary(self.accounting)
        setup = sum(r['monitor']['high_water'] for r in self.data['requests'].values() if r['kind']=='setup')
        total = setup + work['known_observed_tokens']
        current = [k for k,r in self.data['requests'].items() if not r.get('settled')]
        reasons = list(self.data['faults'])
        if any(r['kind']=='work' for r in self.data['requests'].values()):
            reasons += work['reasons']
        if current: reasons.append('SERIAL_REQUEST_UNSETTLED')
        if len(self.data['requests']) >= 6: reasons.append('GLOBAL_ALLOCATION_EXHAUSTED')
        if total >= 100000: reasons.append('PREVENTIVE_THRESHOLD_REACHED')
        return {'known_observed_tokens':total, 'reserved_requests':len(self.data['requests']),
                'current':current, 'can_admit':not reasons, 'reasons':sorted(set(reasons)),
                'final_or_billed_usage':False, 'operational_tolerance':700000}

    def attach(self, lane, flow):
        if lane not in ('local','connector'): raise Refused('LANE_INVALID')
        self.flows[lane] = flow

    def attach_owner(self,lane,owner_home,stop):
        if lane not in ('local','connector'): raise Refused('LANE_INVALID')
        home=str(setup_journal.safe_path(owner_home,self.root))
        if lane in self.data['owners'] and self.data['owners'][lane]!=home:
            raise Refused('OWNER_HOME_CHANGED')
        if not Path(home).is_dir() or not callable(stop): raise Refused('OWNER_CAPABILITY_REQUIRED')
        self.data['owners'][lane]=home
        self.stops[lane]=stop
        self.persist()

    def attach_setup_stop(self,request_id,owner_home,stop):
        r=self.data['requests'].get(request_id)
        if not r or r['kind']!='setup' or str(Path(owner_home).resolve())!=r['monitor']['home']:
            raise Refused('SETUP_OWNER_CHANGED')
        self.attach_owner(r['lane'],owner_home,stop)

    def _reserve(self, request_id, record):
        if record['lane'] not in self.stops: raise Refused('OWNER_STOP_NOT_ATTACHED')
        self.poll()
        if request_id in self.data['requests'] or not self.summary()['can_admit']:
            raise Refused('NEW_DISPATCH_NOT_PERMITTED')
        record.update(started=self.clock(), settled=False, stop_selected=None)
        self.data['requests'][request_id] = record

    def setup(self, request_id, lane, owner_home, dispatch, stop_owner):
        if lane not in ('local','connector'): raise Refused('LANE_INVALID')
        self.attach_owner(lane,owner_home,stop_owner)
        prior=[r['monitor'] for r in self.data['requests'].values()
               if r['kind']=='setup' and r['monitor']['home']==str(Path(owner_home).resolve())]
        monitor = setup_journal.arm(owner_home, self.root,prior)
        self._reserve(request_id, {'kind':'setup', 'lane':lane, 'monitor':monitor})
        self.persist()  # global reservation is durable before setup:test
        try:
            return dispatch()
        except BaseException:
            self.fault('SETUP_RESPONSE_UNKNOWN')
            raise

    def work(self, request_id, lane, text, *, stage='useful_work'):
        flow = self.flows[lane]
        binding = flow.binding()
        scope = {k:binding[k] for k in tokens.PRE_SCOPE}
        current_session = flow.document.get('session_id')
        known = [k for k,s in self.accounting['streams'].items()
                 if s['scope']['session_id'] == current_session and all(s['scope'][n]==v for n,v in scope.items())]
        self._reserve(request_id, {'kind':'work', 'lane':lane, 'stage':stage, 'operation':None,
                                 'session':None, 'stream':None, 'recover':False,'scope':scope})
        state, allowed = (tokens.reserve(self.accounting, request_id=request_id, stream=known[0], stage=stage)
                          if len(known)==1 else tokens.prearm(self.accounting,request_id=request_id,scope=scope,stage=stage))
        if not allowed:
            self.fault('COLLECTOR_RESERVATION_REFUSED')
            raise Refused('COLLECTOR_RESERVATION_REFUSED')
        self.persist(state)
        try:
            operation = flow.submit(text, client_intent_id=request_id, new_session=not current_session)
        except ConnectionError as error:
            if error.stage == 'm1_response_loss':
                self.data['requests'][request_id]['recover'] = True
                self.persist(tokens.response_lost(self.accounting, request_id=request_id))
            else:
                self.data['requests'][request_id]['recover'] = True
                self.fault('WORK_RESPONSE_UNKNOWN')
            raise
        self._bind_operation_result(request_id, operation)
        return operation

    def _bind_operation_result(self, request_id, operation):
        r = self.data['requests'][request_id]
        r['session'] = operation['scope']['session_id']
        r['operation'] = operation.get('submission_turn_operation_id') or operation['operation_id']
        r['recover'] = False
        self.persist()

    def _poll_work(self, request_id, r):
        flow = self.flows[r['lane']]
        if r['recover']:
            # GET only: never call resume() here, because unresolved admission
            # could make that method issue a new POST.
            receipt=flow.api('GET','/runtime/intents/'+quote(request_id,safe=''))
            resolution=receipt['resolution']; operation=receipt.get('operation')
            if resolution.get('client_intent_id')!=request_id: raise Refused('RECOVERY_ID_MISMATCH')
            if operation is None: return
            if (operation.get('operation_id')!=resolution.get('operation_id') or
                    any(operation.get('scope',{}).get(k)!=v for k,v in r['scope'].items())):
                raise Refused('RECOVERY_SCOPE_MISMATCH')
            self._bind_operation_result(request_id,operation|{'submission_turn_operation_id':receipt.get('initial_turn_operation_id')})
        if r['session'] is None: return
        after = self.accounting['streams'][r['stream']]['cursor'] if r['stream'] else 0
        for _ in range(100):
            value = flow.observe(session_id=r['session'], after_sequence=after)
            page = value['events']
            state = self.accounting
            if r['stream'] is None:
                native = {e['payload'].get('thread_id') for e in page['events'] if e['payload'].get('thread_id')}
                if not native: return
                if len(native)!=1: raise Refused('AMBIGUOUS_NATIVE_THREAD')
                if state['requests'][request_id]['stream'] is None:
                    state = tokens.bind_stream(state, request_id=request_id, scope=page['scope'],epoch=page['stream_epoch'],
                        native_thread_id=native.pop(),baseline_total=0,baseline_basis='confirmed_fresh_thread')
                r['stream'] = tokens.stream_id(page['scope'],page['stream_epoch'])
                state = tokens.bind_operation(state,request_id=request_id,operation_id=r['operation'])
            state = tokens.observe(state,stream=r['stream'],after_sequence=after,page=page)
            self.persist(state)
            r['settled'] = state['requests'][request_id]['state']=='settled_observed'
            if not page['has_more']: break
            after = page['next_after_sequence']

    def poll(self):
        now = self.clock()
        if now < self.data['last_clock']: self.fault('CLOCK_REGRESSION')
        self.data['last_clock'] = now
        for key,r in self.data['requests'].items():
            if not r['settled'] and r['lane'] not in self.stops:
                self.fault('OWNER_STOP_NOT_ATTACHED')
                raise Refused('OWNER_STOP_NOT_ATTACHED')
            try:
                if r['kind']=='setup':
                    related=[v['monitor'] for v in self.data['requests'].values()
                             if v['kind']=='setup' and v['monitor']['home']==r['monitor']['home']]
                    r['monitor'] = setup_journal.poll(deepcopy(r['monitor']),
                        [m['journal'] for m in related if m['journal']],any(m['journal'] is None for m in related))
                    r['settled'] = setup_journal.settled(r['monitor'])
                    if r['monitor']['terminal'] and not r['monitor']['usage_seen']:
                        self.fault('SETUP_TERMINAL_USAGE_MISSING')
                else:
                    self._poll_work(key,r)
            except Exception:
                self.fault('OBSERVATION_UNKNOWN')
        total = self.summary()['known_observed_tokens']
        token_state = self.accounting
        bad_work = bool(token_state['faults']) or any(s['gap'] for s in token_state['streams'].values())
        missing_usage = any(t['terminal'] and not t['usage_seen'] for t in token_state['turns'].values())
        if missing_usage: self.fault('WORK_TERMINAL_USAGE_MISSING')
        for key,r in self.data['requests'].items():
            reason = ('OBSERVATION_UNKNOWN' if self.data['faults'] or bad_work else
                      'PREVENTIVE_THRESHOLD' if total>=100000 else
                      'DEADLINE120' if not r['settled'] and now-r['started']>=120 else None)
            if reason and not r['settled'] and r['stop_selected'] is None:
                terminal = any(t['operation_id']==r.get('operation') and t['stream']==r.get('stream') and t['terminal']
                               for t in token_state['turns'].values())
                action = 'stop_owner' if r['kind']=='setup' or r.get('session') is None else 'close' if terminal else 'interrupt'
                r['stop_selected'] = {'reason':reason, 'action':action}
                self.persist()  # no automatic retry if the stop response is lost
                try:
                    if action=='stop_owner':
                        self.stops[r['lane']]()
                    elif r['session'] is not None:
                        self.flows[r['lane']].submit(action=action,session_id=r['session'],
                            client_intent_id='m1-stop-'+key)
                    else:
                        self.fault('OWNED_SESSION_NOT_YET_RESOLVED')
                except Exception:
                    self.fault('STOP_UNCONFIRMED')
        self.persist()
        return self.summary()

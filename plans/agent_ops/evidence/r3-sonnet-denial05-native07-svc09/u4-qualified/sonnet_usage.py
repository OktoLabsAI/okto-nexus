"""Campaign-only Claude stream accounting. No IO, provider or credential access."""
import hashlib
import json
import re

FIELDS=('input_tokens','cache_read_input_tokens','cache_creation_input_tokens','output_tokens')
MODEL_FIELDS=('inputTokens','cacheReadInputTokens','cacheCreationInputTokens','outputTokens')

class Unknown(RuntimeError):pass

def require(ok,reason):
    if not ok:raise Unknown(reason)

def counters(value,fields=FIELDS):
    require(type(value) is dict,'USAGE_MISSING')
    out={}
    for key in fields:
        n=value.get(key)
        require(type(n) is int and 0<=n<2**53,'USAGE_COUNTER_INVALID')
        out[key]=n
    return out

def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def project_usage(value,fields=FIELDS):
    if type(value) is not dict:return None
    return {k:value[k] if type(value[k]) is int else None for k in fields if k in value}

def project_models(value):
    if type(value) is not dict:return None
    require(len(value)<=8,'MODEL_MAP_UNBOUNDED')
    require(all(isinstance(k,str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,119}',k) for k in value),'MODEL_NAME_INVALID')
    return {k:project_usage(v,MODEL_FIELDS) for k,v in value.items()}

def project(event):
    """Allowlist preserved Core event fields, excluding text/tools/commands/auth."""
    p=event['payload'];kind=event.get('native_type') or ''
    out={k:event.get(k) for k in ('server_id','executor_id','session_id','stream_epoch','sequence','operation_id','category','native_type')}
    body={k:p[k] for k in ('session_id','uuid','parent_tool_use_id','delivery_phase','delivery_outcome') if k in p}
    if kind=='system:init':body['model']=p.get('model')
    elif kind.startswith('stream_event:'):
        e=p.get('event') or {};body['event']={'type':e.get('type')}
        if e.get('type')=='message_start':
            m=e.get('message') or {};body['event']['message']={k:m.get(k) for k in ('id','model')};body['event']['message']['usage']=project_usage(m.get('usage'))
        elif e.get('type')=='message_delta':body['event']['usage']=project_usage(e.get('usage'))
    elif kind=='assistant':
        raw=p.get('raw') or {};m=raw.get('message') or {}
        body.update(parent_tool_use_id=raw.get('parent_tool_use_id'),message={k:m.get(k) for k in ('id','model')});body['message']['usage']=project_usage(m.get('usage'))
    elif kind.startswith('result:') and kind!='result:output':
        body.update(usage=project_usage(p.get('usage')),modelUsage=project_models(p.get('modelUsage')),is_error=p.get('is_error'),subtype=p.get('subtype'))
    elif kind in ('system:compact_boundary','system:conversation_reset'):
        body['reset']=True
    out['payload']=body
    require(len(json.dumps(out).encode())<=32768,'PROJECTION_TOO_LARGE')
    return out

class Ledger:
    """One new Claude native session. Cumulative modelUsage; no resume/reset."""
    def __init__(self,scope,*,limit=200000,preventive=150000,max_requests=3):
        require(set(scope)=={'server_id','executor_id','session_id','stream_epoch'},'SCOPE_INVALID')
        require((limit,preventive,max_requests) in ((200000,150000,3),(200000,180000,3),(500000,480000,4)),'POLICY_INVALID')
        self.scope=dict(scope);self.limit=limit;self.preventive=preventive;self.max_requests=max_requests
        self.cursor=0;self.seen={};self.faults=[];self.active=None;self.reserved=[];self.finished=[]
        self.native_session=None;self.messages={};self.current_message=None;self.models={};self.baseline=0;self.known=0
        self.started=False;self.init_seen=False;self.completed_message_ids=set();self.terminal_coverage=True

    def reserve(self,operation):
        require(not self.faults and self.active is None and self.terminal_coverage,'ADMISSION_CLOSED')
        require(self.known<self.preventive and len(self.reserved)<self.max_requests,'BUDGET_OR_ALLOCATION_CLOSED')
        require(operation not in self.reserved and isinstance(operation,str) and bool(operation),'REQUEST_REPLAY')
        self.reserved.append(operation);self.active=operation;self.messages={};self.current_message=None
        self.completed_message_ids=set();self.started=bool(self.native_session and self.finished);self.init_seen=False;self.terminal_coverage=False;self.baseline=self.known

    def ingest(self,event):
        try:self._ingest(event)
        except (Unknown,KeyError,TypeError,ValueError) as exc:
            reason=str(exc) if isinstance(exc,Unknown) else 'EVENT_SHAPE_INVALID'
            if reason not in self.faults:self.faults.append(reason)
            raise Unknown(reason) from None

    def _ingest(self,e):
        require(all(e.get(k)==v for k,v in self.scope.items()),'EVENT_SCOPE_CHANGED')
        seq=e['sequence'];require(type(seq) is int and seq>0,'SEQUENCE_INVALID')
        h=digest(e)
        if seq<=self.cursor:
            require(self.seen.get(seq)==h,'EVENT_REPLAY_CHANGED');return
        require(seq==self.cursor+1,'EVENT_GAP')
        self.seen[seq]=h;self.cursor=seq
        p=e['payload'];kind=e.get('native_type') or ''
        require(not p.get('reset'),'RESET_FORBIDDEN')
        relevant=kind=='system:init' or kind=='assistant' or kind.startswith('stream_event:') or kind.startswith('result:') and kind!='result:output'
        if not relevant:return
        require(self.active is not None,'UNSELECTED_NATIVE_ACTIVITY')
        require(e.get('operation_id') in (None,self.active),'OPERATION_CHANGED')
        native=p.get('session_id')
        if native is not None:
            require(isinstance(native,str) and bool(native),'NATIVE_SESSION_INVALID')
            require(self.native_session in (None,native),'NATIVE_SESSION_CHANGED');self.native_session=native
        require(p.get('parent_tool_use_id') is None,'SUBAGENT_FORBIDDEN')
        if kind=='system:init':
            require(not self.init_seen and e['operation_id']==self.active and p.get('delivery_phase')=='started','START_UNCORRELATED')
            require('sonnet' in str(p.get('model','')).lower(),'MODEL_NOT_SONNET');self.started=True;self.init_seen=True;return
        require(self.started,'EVENT_BEFORE_START')
        if kind.startswith('stream_event:'):
            value=p['event'];t=value['type']
            if t=='message_start':
                require(self.current_message is None,'MESSAGE_OVERLAP')
                m=value['message'];mid=m['id'];require(isinstance(mid,str) and mid and mid not in self.messages,'MESSAGE_ID_REUSED')
                self.current_message=mid;self.messages[mid]=counters(m['usage'])
                self._observed()
                require('sonnet' in str(m['model']).lower(),'MODEL_NOT_SONNET')
            elif t=='message_delta':
                require(self.current_message is not None,'MESSAGE_DELTA_UNBOUND');usage=value['usage']
                require(type(usage) is dict and 'output_tokens' in usage,'DELTA_USAGE_MISSING')
                current=self.messages[self.current_message]
                for k in FIELDS:
                    if k not in usage:continue
                    n=usage[k];require(type(n) is int and current[k]<=n<2**53,'COUNTER_REGRESSION');current[k]=n
            elif t=='message_stop':
                require(self.current_message is not None,'MESSAGE_STOP_UNBOUND')
                self.completed_message_ids.add(self.current_message);self.current_message=None
            self._observed();return
        if kind=='assistant':
            m=p['message']
            if m.get('id')=='[NATIVE_TEXT_REDACTED]' and m.get('model')=='[NATIVE_TEXT_REDACTED]':
                # Core deliberately withholds all strings in output snapshots,
                # including the native message ID. This duplicate assistant
                # snapshot is not an accounting/identity source. Keep the real
                # stream ID and counters; terminal stream/result coverage is
                # still mandatory and cannot be supplied by this snapshot.
                require(e.get('operation_id')==self.active,'ASSISTANT_OPERATION_UNCORRELATED')
                require(bool(self.messages),'ASSISTANT_WITHOUT_STREAM')
                counters(m.get('usage'))  # Shape only; never use this duplicate snapshot's values.
                return
            require(m['id'] in self.messages,'ASSISTANT_WITHOUT_STREAM')
            usage=counters(m['usage']);prior=self.messages[m['id']]
            require(all(usage[k]==prior[k] for k in FIELDS[:-1]),'ASSISTANT_INPUT_CHANGED')
            # SDK assistant output count is a message_start placeholder, not final output.
            self._observed();return
        if kind.startswith('result:'):
            require(e['operation_id']==self.active and p.get('delivery_phase')=='terminal','TERMINAL_UNCORRELATED')
            models=p.get('modelUsage');require(type(models) is dict and bool(models),'FINAL_MODELS_MISSING')
            parsed={name:counters(v,MODEL_FIELDS) for name,v in models.items()}
            total=sum(sum(v.values()) for v in parsed.values())
            self.known=max(self.known,total)
            require(all('sonnet' in name.lower() for name in parsed),'MODEL_NOT_SONNET')
            require(set(self.models)<=set(parsed),'MODEL_DISAPPEARED')
            require(all(all(parsed[n][k]>=v for k,v in old.items()) for n,old in self.models.items()),'FINAL_COUNTER_REGRESSION')
            require(total>=self.known,'FINAL_BELOW_OBSERVED')
            self.known=total;self.models=parsed
            require(self.current_message is None and bool(self.messages) and self.completed_message_ids==set(self.messages),'MESSAGE_COVERAGE_INCOMPLETE')
            turn=counters(p.get('usage'));local={k:sum(m[k] for m in self.messages.values()) for k in FIELDS}
            require(turn==local,'FINAL_TURN_MISMATCH')
            require(total==self.baseline+sum(local.values()),'FINAL_UNOBSERVED_USAGE')
            self.finished.append({'operation_id':self.active,'outcome':p.get('delivery_outcome'),'tokens':sum(local.values()),'input_tokens_including_cache':sum(local[k] for k in FIELDS[:-1])})
            self.active=None;self.terminal_coverage=True
        self._observed()

    def _observed(self):
        self.known=max(self.known,self.baseline+sum(sum(v.values()) for v in self.messages.values()))

    def summary(self):
        return {'observed_minimum':self.known,'limit':self.limit,'preventive':self.preventive,'reservations':len(self.reserved),
            'active':self.active,'faults':list(self.faults),'coverage':self.terminal_coverage,'can_admit':not self.faults and self.active is None and self.terminal_coverage and self.known<self.preventive and len(self.reserved)<self.max_requests,
            'hard_token_cap_guaranteed':False}

class CampaignBudget:
    """One shared 200k limit including any canonically required setup turn."""
    def __init__(self,*,preventive=150000,limit=200000,max_requests=3):
        require((limit,preventive,max_requests) in ((200000,150000,3),(200000,180000,3),(500000,480000,4)),'POLICY_INVALID')
        self.preventive=preventive;self.limit=limit;self.max_requests=max_requests;self.sessions={}
    @property
    def known(self):return sum(x.known for x in self.sessions.values())
    def attach(self,ledger):
        key=tuple(ledger.scope[k] for k in ('server_id','executor_id','session_id','stream_epoch'))
        require(key not in self.sessions and len(self.sessions)<self.max_requests and ledger.known==0 and not ledger.reserved,'SESSION_BASELINE_NOT_FRESH')
        self.sessions[key]=ledger
    def reservation_estimate(self,phase):
        require(phase in ('setup','useful','continuation'),'PHASE_INVALID')
        previous_input=max((item.get('input_tokens_including_cache',0) for x in self.sessions.values() for item in x.finished),default=0)
        # Deliberately conservative: observed cumulative input, not a prediction or hard cap.
        return max(50000,2*previous_input+32000)
    def check_admission(self,phase):
        require(all(not x.faults and x.active is None and x.terminal_coverage for x in self.sessions.values()),'CAMPAIGN_COVERAGE_UNKNOWN')
        require(sum(len(x.reserved) for x in self.sessions.values())<self.max_requests,'CAMPAIGN_BUDGET_OR_ALLOCATION_CLOSED')
        estimate=self.reservation_estimate(phase)
        require(self.known+estimate<=self.preventive,'NEXT_REQUEST_HEADROOM_INSUFFICIENT')
        return {'observed_tokens':self.known,'reserved_next':estimate,'preventive':self.preventive,'limit':self.limit}
    def reserve(self,ledger,operation,*,phase='useful'):
        require(any(x is ledger for x in self.sessions.values()),'UNATTACHED_LEDGER')
        require(all(not x.faults and x.active is None and x.terminal_coverage for x in self.sessions.values()),'CAMPAIGN_COVERAGE_UNKNOWN')
        require(self.known<self.preventive and sum(len(x.reserved) for x in self.sessions.values())<self.max_requests,'CAMPAIGN_BUDGET_OR_ALLOCATION_CLOSED')
        require(self.known+self.reservation_estimate(phase)<=self.preventive,'NEXT_REQUEST_HEADROOM_INSUFFICIENT')
        require(all(operation not in x.reserved for x in self.sessions.values()),'CAMPAIGN_REQUEST_REPLAY')
        ledger.reserve(operation)

def checkpoint_budget(budget):
    sessions=[]
    for ledger in budget.sessions.values():
        value=dict(ledger.__dict__);value['completed_message_ids']=sorted(value['completed_message_ids'])
        value['seen']={str(k):v for k,v in value['seen'].items()}
        sessions.append(value)
    body={'format':'sonnet-campaign-usage-v2','preventive':budget.preventive,'limit':budget.limit,'max_requests':budget.max_requests,'sessions':sessions}
    return {'state':body,'sha256':digest(body)}

def restore_budget(document):
    require(type(document) is dict and document.get('sha256')==digest(document.get('state')),'CHECKPOINT_CHANGED')
    body=document['state'];require(body.get('format') in ('sonnet-campaign-usage-v1','sonnet-campaign-usage-v2'),'CHECKPOINT_FORMAT')
    b=CampaignBudget(preventive=body['preventive'],limit=body.get('limit',200000),max_requests=body.get('max_requests',3))
    for value in body['sessions']:
        l=Ledger(value['scope'],limit=value['limit'],preventive=value['preventive'],max_requests=value['max_requests'])
        require(set(value)==set(l.__dict__),'CHECKPOINT_FIELDS')
        l.__dict__.update(value);l.completed_message_ids=set(value['completed_message_ids']);l.seen={int(k):v for k,v in value['seen'].items()}
        require(type(l.known) is int and l.known>=0 and type(l.baseline) is int and 0<=l.baseline<=l.known,'CHECKPOINT_COUNTERS')
        require(l.active is None and l.terminal_coverage and not l.faults,'RECONCILIATION_REQUIRED')
        require(l.known==sum(sum(counters(v,MODEL_FIELDS).values()) for v in l.models.values()),'CHECKPOINT_TOTAL_CHANGED')
        key=tuple(l.scope[k] for k in ('server_id','executor_id','session_id','stream_epoch'))
        require(key not in b.sessions and len(b.sessions)<b.max_requests,'CHECKPOINT_SESSION_DUPLICATE');b.sessions[key]=l
    return b

class AdmissionMonitor:
    """Injected clock/transport selection. Never starts or calls provider itself."""
    def __init__(self,ledger,clock,*,budget=None,deadline=600,freshness=20):
        self.ledger=ledger;self.clock=clock;self.deadline=deadline;self.freshness=freshness
        self.budget=budget
        self.observed_at=None;self.started_at=None;self.interrupt_selected=False
    def observed(self):self.observed_at=self.clock()
    def admit(self,operation,*,phase='useful'):
        now=self.clock();require(self.observed_at is not None and 0<=now-self.observed_at<=self.freshness,'OBSERVATION_STALE')
        if self.budget is None:self.ledger.reserve(operation)
        else:self.budget.reserve(self.ledger,operation,phase=phase)
        self.started_at=now;self.interrupt_selected=False
    def containment(self,*,canonical_operation,owner_matches,select_interrupt):
        now=self.clock();stale=self.observed_at is None or now-self.observed_at>self.freshness
        due=self.started_at is not None and now-self.started_at>=self.deadline
        observed=self.ledger.known if self.budget is None else self.budget.known
        threshold=self.ledger.preventive if self.budget is None else self.budget.preventive
        fault=bool(self.ledger.faults) or observed>=threshold or stale or due
        if not fault or self.ledger.active is None:return 'NO_CONTROL_NEEDED'
        if 'MONITOR_CONTAINMENT' not in self.ledger.faults:self.ledger.faults.append('MONITOR_CONTAINMENT')
        if not owner_matches or canonical_operation!=self.ledger.active:return 'ADMISSION_CLOSED_IDENTITY_UNKNOWN'
        if self.interrupt_selected:return 'INTERRUPT_ALREADY_SELECTED'
        self.interrupt_selected=True
        # Caller implements one canonical current_run resolve/admit for exactly this owned operation.
        select_interrupt(self.ledger.scope,self.ledger.active)
        return 'INTERRUPT_SELECTED_NOT_SETTLED'

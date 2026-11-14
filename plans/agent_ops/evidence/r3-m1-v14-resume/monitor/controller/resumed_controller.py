"""Explicit single resumption of the proved, never-dispatched v14 request.

Original checkpoint, closure, fault facts and reservation remain historical.
The caller pins these inputs and writes the returned derived checkpoint once.
This module neither starts a service nor supplies an HTTP/provider transport.
"""
from copy import deepcopy
import json
import os
from pathlib import Path
from types import SimpleNamespace

from independent_controller import Controller, POLICY, Refused
from legacy_controller import Controller as LegacyController, seal

REQUEST='m1v14-local-work-01'
FAULTS={'MONITOR_CADENCE_EXCEEDED','OBSERVATION_STALE','WORK_RESPONSE_UNKNOWN'}

def require(ok,code):
    if not ok:raise Refused(code)

def validate_never_dispatched(checkpoint,result,closure,absence,returned):
    require(checkpoint['state_sha256']==seal(checkpoint),'CHECKPOINT_SEAL_INVALID')
    require(set(checkpoint['requests'])=={REQUEST} and set(checkpoint['faults'])==FAULTS,'EXACT_FAILED_REQUEST_REQUIRED')
    require(result['request_id']==REQUEST and result['calls']['POST']==0
        and result['calls']['productive_posts']==0 and result['calls']['decision_posts']==0,
        'POST_MAY_HAVE_BEEN_DISPATCHED')
    require(result['independent_observation']['worker_in_flight'] is False
        and result['record']['api_returned'] is True
        and returned['wrapper_exit_confirmed'] is True and returned['returncode']==0,
        'WORKER_EXIT_UNCONFIRMED')
    recent=result['cli_execution']['local']['recent']
    require(len(recent)==1 and recent[0]['error_type']=='Fenced'
        and recent[0]['possible_effect'] is False,'EXACT_FENCE_FAILURE_REQUIRED')
    record=checkpoint['requests'][REQUEST]
    require(all(record[key] is None for key in ('operation','session','stream'))
        and record['settled'] is False,'REQUEST_ALREADY_BOUND')
    collector=checkpoint['collector']['state']
    require(set(collector['requests'])=={REQUEST} and collector['requests'][REQUEST]['state']=='reserved'
        and not any(collector[k] for k in ('streams','threads','turns','faults')),
        'COLLECTOR_HAS_POSSIBLE_EFFECT')
    require(absence=={'request_id':REQUEST,'server_id':record['scope']['server_id'],
        'actor_agent_id':record['actor_agent_id'],'canonical_intent_count':0},'CANONICAL_ABSENCE_REQUIRED')
    require(closure['status']=='CLOSED_NORMAL_CLEANUP_ACCEPTANCE_NOT_INFERRED'
        and closure['closed_without_force'] is True and closure['all_temporary_tasks_absent'] is True
        and closure['cumulative_reserved_admissions']==10
        and closure['cumulative_minimum_observed_tokens']==134199,'CLOSED_PREDECESSOR_REQUIRED')
    return {'classification':'NEVER_DISPATCHED','request_id':REQUEST,
            'cumulative_reserved_admissions':10,'observed_tokens':134199,
            'reserved_request_reused':True,'refund':False}

def prepare_derived(checkpoint,result,closure,absence,returned,*,source_pins):
    proof=validate_never_dispatched(checkpoint,result,closure,absence,returned)
    require('pre_effect_resumption' not in checkpoint,'RESUMPTION_ALREADY_PREPARED')
    out=deepcopy(checkpoint)
    out['pre_effect_resumption']={**proof,'source_pins':deepcopy(source_pins),
        'historical_faults':deepcopy(checkpoint['faults']),
        'historical_request':deepcopy(checkpoint['requests'][REQUEST]),
        'historical_owner_stops':deepcopy(checkpoint.get('independent_owner_stops',{})),
        'operational_cadence_seconds':5,'effect_freshness_seconds':1,
        'pre_dispatch_wait_seconds':600,'execution_deadline_seconds':600}
    # Active fault decisions are resolved only by this explicit proof. Their
    # original bytes and facts are retained above and in pinned source files.
    out['faults']=[]
    out['independent_owner_stops']={}
    record=out['requests'][REQUEST]
    record.update(recover=False,stop_selected=None,api_returned=False,
                  resume_selected=False,resume_wait_started_monotonic=None,
                  execution_started_monotonic=None)
    out['state_sha256']=seal(out)
    require(out['collector']==checkpoint['collector'],'COLLECTOR_CHANGED')
    return out

class ResumedController(Controller):
    def __init__(self,*args,original_control_root,first_dispatch_receipt,**kwargs):
        self.original_control_root=Path(original_control_root).resolve()
        self.first_dispatch_receipt=Path(first_dispatch_receipt).resolve()
        path=Path(args[0]).resolve()
        require(path==self.original_control_root/'resume-request01/private/controller.json',
                'DERIVED_CONTROLLER_PATH_INVALID')
        require(self.first_dispatch_receipt==path.parent/'first-dispatch.json','DISPATCH_RECEIPT_PATH_INVALID')
        super().__init__(*args,**kwargs)
        require(self.data['pre_effect_resumption']['classification']=='NEVER_DISPATCHED','RESUMPTION_PROOF_REQUIRED')
        record=self.data['requests'][REQUEST]
        if not record['settled'] and not record.get('resume_selected'):
            require(not self.first_dispatch_receipt.exists(),'DISPATCH_ALREADY_RESERVED')
            if record['resume_wait_started_monotonic'] is None:
                record['resume_wait_started_monotonic']=self._monotonic()
                self.persist()
            self.fence.arm(record['resume_wait_started_monotonic']+600)
        elif not record['settled']:
            started=self._execution_start(record)
            require(started is not None,'RESUMED_DEADLINE_UNKNOWN')
            self.fence.arm(started+600)

    def _approval_valid(self):
        # Same v14 authorization and CONTROL identity; only evidence path differs.
        probe=SimpleNamespace(**self.__dict__)
        probe.path=self.original_control_root/'private/controller.json'
        return LegacyController._approval_valid(probe)

    def _execution_start(self,record):
        if record is self.data['requests'].get(REQUEST):
            if record.get('execution_started_monotonic') is None and self.first_dispatch_receipt.exists():
                receipt=json.loads(self.first_dispatch_receipt.read_bytes())
                started=receipt['execution_started_monotonic']
                require(receipt['request_id']==REQUEST
                    and receipt['classification']=='FIRST_DISPATCH_RESERVED'
                    and type(started) in (int,float)
                    and record['resume_wait_started_monotonic']<=started<=self._monotonic()
                    and receipt['execution_deadline_monotonic']==started+600
                    and receipt['reservation_count_unchanged']==10
                    and receipt['retry_allowed'] is False,'DISPATCH_REQUEST_CHANGED')
                record['execution_started_monotonic']=receipt['execution_started_monotonic']
            return record.get('execution_started_monotonic') or record.get('resume_wait_started_monotonic')
        return super()._execution_start(record)

    def _reserve_first_dispatch(self,started):
        value={'request_id':REQUEST,'classification':'FIRST_DISPATCH_RESERVED',
            'execution_started_monotonic':started,'execution_deadline_monotonic':started+600,
            'reservation_count_unchanged':10,'retry_allowed':False}
        pending=self.first_dispatch_receipt.with_suffix('.pending')
        require(not self.first_dispatch_receipt.exists(),'DISPATCH_ALREADY_RESERVED')
        with pending.open('x',encoding='utf-8') as stream:
            json.dump(value,stream,sort_keys=True);stream.flush();os.fsync(stream.fileno())
        os.replace(pending,self.first_dispatch_receipt)
        return started+600

    def start_work(self,request_id,lane,text,*,binding,checkpoint,stage='useful_work',new_session=False):
        if request_id!=REQUEST:
            return super().start_work(request_id,lane,text,binding=binding,checkpoint=checkpoint,
                                      stage=stage,new_session=new_session)
        self._owned();self._require_authorized()
        record=self.data['requests'][REQUEST]
        require(not record['resume_selected'] and not self.first_dispatch_receipt.exists(),
                'RESERVED_REQUEST_ALREADY_RESUMED')
        require(not self.data['faults'] and lane=='local' and stage=='useful_work' and new_session,
                'RESUME_SELECTION_CHANGED')
        require(self.api.thread is None and self.api_result is None,'API_TASK_ALREADY_IN_FLIGHT')
        require(all(binding[k]==v for k,v in record['scope'].items()),'RESUME_SCOPE_CHANGED')
        require(self._readers[lane].read(request_id) is None,'CANONICAL_INTENT_EXISTS_NO_REPLAY')
        require(not self._journals[lane].io.failed,'CORE_READER_FAILED')
        record['resume_selected']=True
        self.persist()  # existing reservation, no tokens.prearm or _reserve call
        self.fence.before_first_effect=self._reserve_first_dispatch
        self.api.submit(request_id,lambda:self.flows[lane].submit(text,client_intent_id=request_id,
                        new_session=True),productive=True)

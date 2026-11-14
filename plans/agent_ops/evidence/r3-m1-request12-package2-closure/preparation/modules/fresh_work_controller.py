"""New requests12/13; immutable history and no fabricated stream settlement."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from independent_controller import Controller, POLICY, Refused
from legacy_controller import seal
import token_collector as tokens

OLD='m1v14-local-work-01'
FAILED='m1v14-local-work-11'
USEFUL='m1v14-local-work-12'
CONTINUATION='m1v14-local-work-13'

def require(ok,code):
    if not ok:raise Refused(code)

def checked_pin(pin,document=None):
    raw=Path(pin['path']).read_bytes()
    require(hashlib.sha256(raw).hexdigest()==pin['sha256'],'HISTORICAL_SOURCE_CHANGED')
    if document is not None:require(json.loads(raw)==document,'HISTORICAL_DOCUMENT_CHANGED')
    return json.loads(raw)

def prepare_derived(checkpoint,companion,accounting,*,source_pins):
    for key,value in (('checkpoint',checkpoint),('companion',companion),('accounting',accounting)):
        checked_pin(source_pins[key],value)
    require(checkpoint['state_sha256']==seal(checkpoint),'CHECKPOINT_SEAL_INVALID')
    require(set(checkpoint['requests'])=={OLD,FAILED},'EXACT_PREDECESSOR_REQUIRED')
    state=tokens.restore(checkpoint['collector'])
    require(checkpoint['policy']['carry_in_tokens']+tokens.summary(state)['known_observed_tokens']==272648
        and checkpoint['policy']['carry_in_admissions']+len(checkpoint['requests'])==11,'PREDECESSOR_COUNTER_CHANGED')
    require(checkpoint['requests'][OLD]['settled'] is True
        and checkpoint['requests'][OLD]['canonical_stage']=='CANCELLED'
        and checkpoint['requests'][FAILED]['settled'] is False
        and checkpoint['requests'][FAILED]['stream'] is None
        and state['requests'][FAILED]['state']=='reserved','HISTORICAL_STATE_CHANGED')
    require(companion['status']=='CLOSED_AFTER_AUTHORIZED_FORCE_ACCOUNTING_RECONCILED_ACCEPTANCE_NOT_INFERRED'
        and companion['force_used'] is True and companion['physical_exit_confirmed'] is True
        and companion['nexus_task_absent'] is True and companion['canonical_owner_absent'] is True
        and companion['files']['original_checkpoint']==source_pins['checkpoint']
        and companion['files']['derived_accounting']==source_pins['accounting'],'CLOSED_RECONCILIATION_REQUIRED')
    require(accounting['accounting_reconciled'] is True and accounting['request_id']==FAILED
        and accounting['cumulative_minimum_observed_tokens']==272648
        and accounting['cumulative_reserved_admissions']==11 and accounting['new_native_turns']==0
        and accounting['core_launch_stop_proof']=='NEVER_CLAIMED'
        and accounting['canonical_session_state']=='FAILED' and accounting['canonical_lease_state']=='CLOSED'
        and accounting['core_claim_reconciliation_pending'] is True
        and accounting['collector_settled_observed_synthesized'] is False,'ACCOUNTING_RECONCILIATION_REQUIRED')
    projection=checked_pin(accounting['post_exit_projection'])
    require(projection['launch'][0]['spawn_claimed']==0 and projection['launch'][0]['producer_fenced']==1
        and projection['counts']=={'process_births':0,'events':0,'event_streams':0},'NO_NATIVE_PROOF_REQUIRED')
    out=deepcopy(checkpoint)
    out['fresh_local_work']={'classification':'NEW_INTENTS_AFTER_RECONCILED_PRELAUNCH_FAILURE',
        'source_pins':deepcopy(source_pins),'historical_checkpoint':deepcopy(checkpoint),
        'historical_projection':projection,'historical_faults':deepcopy(checkpoint['faults']),
        'new_request_ids':[USEFUL,CONTINUATION],'reservation_refunded':False,
        'initial_cumulative_tokens':272648,'initial_cumulative_reservations':11,
        'historical_reobservation':'Both retained sessions checked every poll; new events or changed launch evidence close admission.'}
    out['requests']={};out['collector']=tokens.checkpoint(tokens.initial_state())
    out['policy']=deepcopy(POLICY);out['faults']=[];out['independent_owner_stops']={}
    out.pop('independent_observation',None)
    out['state_sha256']=seal(out)
    return out

class FreshWorkController(Controller):
    def __init__(self,*args,original_control_root,amendment_path,amendment_sha256,**kwargs):
        self.original_control_root=Path(original_control_root).resolve()
        self.amendment_path=Path(amendment_path).resolve();self.amendment_sha256=amendment_sha256
        require(Path(args[0]).resolve()==self.original_control_root/'work-request12-package2/private/controller.json',
            'NEW_WORK_CONTROLLER_PATH_INVALID')
        super().__init__(*args,**kwargs)

    def _approval_valid(self):
        try:
            history=self.data['fresh_local_work'];original=history['historical_checkpoint']
            raw=self.approval_path.read_bytes();receipt=json.loads(raw)
            amendment_raw=self.amendment_path.read_bytes();amendment=json.loads(amendment_raw)
            return (hashlib.sha256(raw).hexdigest()==self.approval_sha256
                and receipt.get('status')=='USER_APPROVED' and receipt.get('proposal_revision')==14
                and receipt.get('proposal_sha256')==self.expected_proposal_sha256
                and receipt.get('policy')==original['policy'] and receipt.get('ancestry')==original['ancestry']
                and bool(receipt.get('user_quote')) and receipt.get('campaign_root')==str(self.root)
                and receipt.get('control_root')==str(self.original_control_root)
                and hashlib.sha256(amendment_raw).hexdigest()==self.amendment_sha256
                and amendment.get('policy')==POLICY
                and amendment.get('campaign_root')==str(self.root)
                and amendment.get('control_root')==str(self.original_control_root)
                and amendment.get('request_ids')=={'useful':USEFUL,'continuation':CONTINUATION}
                and amendment.get('source_authority')=={'proposal_sha256':self.expected_proposal_sha256,'approval_sha256':self.approval_sha256}
                and all(amendment.get('basis',{}).get(k)==history['source_pins'][k] for k in ('checkpoint','companion','accounting')))
        except (OSError,ValueError,TypeError,KeyError,AttributeError):return False

    def _validate(self):
        super()._validate()
        history=self.data.get('fresh_local_work',{});original=history.get('historical_checkpoint',{})
        require(history.get('classification')=='NEW_INTENTS_AFTER_RECONCILED_PRELAUNCH_FAILURE'
            and history.get('reservation_refunded') is False
            and original.get('state_sha256')==seal(original)
            and set(original.get('requests',{}))=={OLD,FAILED}
            and history.get('historical_faults')==original.get('faults')
            and set(self.data['requests']).issubset({USEFUL,CONTINUATION}),'NEW_WORK_HISTORY_CHANGED')
        checked_pin(history['source_pins']['checkpoint'],original)

    def _poll_historical(self):
        history=self.data['fresh_local_work'];original=history['historical_checkpoint']
        state=tokens.restore(original['collector'])
        for request_id,record in original['requests'].items():
            self._check_poll()
            reader=self._readers.get(record['lane']);journal=self._journals.get(record['lane'])
            require(reader is not None and journal is not None,'HISTORICAL_OBSERVER_REQUIRED')
            observed=reader.read(request_id)
            require(observed is not None and all(observed['scope'][k]==v for k,v in record['scope'].items())
                and observed['operation_id']==record['operation'] and observed['scope']['session_id']==record['session'],
                'HISTORICAL_SCOPE_CHANGED')
            session=observed.get('session_state') or {}
            if request_id==OLD:
                require(session.get('lifecycle_state')=='CLOSED' and session.get('lease_state')=='CLOSED'
                    and (observed.get('operation_receipt') or {}).get('stage')=='CANCELLED','HISTORICAL_TERMINAL_CHANGED')
                stream=state['streams'][record['stream']]
                page=journal.read(observed['scope'],stream['cursor'])
                require(page is not None and page['stream_epoch']==stream['epoch'] and not page['events']
                    and page['committed_contiguous']==stream['watermark'] and not page['has_more'],
                    'HISTORICAL_JOURNAL_CHANGED')
            else:
                expected={k:v for k,v in history['historical_projection']['canonical_receipts'][0].items() if k!='operation_id'}
                require(session.get('lifecycle_state')=='FAILED' and session.get('lease_state')=='CLOSED'
                    and session.get('stream_epoch') is None and observed.get('opening_receipt')==expected,
                    'HISTORICAL_PRELAUNCH_CHANGED')
                current=journal.read_unclaimed(observed['scope'],observed['opening_operation_id'])
                projection=history['historical_projection']
                require(current['launch']==projection['launch'] and current['counts']==projection['counts']
                    and current['action_counts']==projection['action_counts']
                    and current['operations']==projection['operations'] and not current['active_slots'],
                    'HISTORICAL_NATIVE_PROOF_CHANGED')
        self._check_poll()

    def _new_session_allowed(self,lane,stage):
        return lane=='local' and stage=='useful_work' and not self.data['requests']

    def _contain_faults(self):
        super()._contain_faults()
        if self.data['faults']:
            history=self.data['fresh_local_work']['historical_checkpoint']['requests']
            for lane in sorted({r['lane'] for r in history.values()}):
                if lane in self.stops:self._stop_owner_once(lane,self.data['faults'][0])

    def start_work(self,request_id,lane,text,*,binding,checkpoint,stage='useful_work',new_session=False):
        require(lane=='local','LOCAL_WORK_ONLY')
        if request_id==USEFUL:
            require(stage=='useful_work' and new_session and not self.data['requests'],'FRESH_USEFUL_SELECTION_REQUIRED')
        elif request_id==CONTINUATION:
            prior=self.data['requests'].get(USEFUL,{})
            require(stage=='continuation' and not new_session and prior.get('settled') is True
                and prior.get('canonical_stage')=='SUCCEEDED' and checkpoint.get('session_id')==prior.get('session'),
                'SUCCESSFUL_USEFUL_REQUIRED')
        else:raise Refused('NEW_INTENT_OUTSIDE_SELECTION')
        return super().start_work(request_id,lane,text,binding=binding,checkpoint=checkpoint,stage=stage,new_session=new_session)

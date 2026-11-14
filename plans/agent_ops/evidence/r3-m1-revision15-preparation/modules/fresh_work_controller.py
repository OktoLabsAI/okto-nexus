"""Four finite new intents; three histories remain observed without refunds."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from independent_controller import Controller, POLICY, Refused
from legacy_controller import ANCESTRY, seal
import token_collector as tokens

OLD='m1v14-local-work-01'
FAILED='m1v14-local-work-11'
LAST='m1v14-local-work-12'
USEFUL='m1v15-local-useful-13'
CONTINUATION='m1v15-local-continuation-14'
REQUEST_IDS={'useful':USEFUL,'continuation':CONTINUATION,
    'remote_useful':'m1v15-remote-useful-15','remote_continuation':'m1v15-remote-continuation-16'}

def require(ok,code):
    if not ok:raise Refused(code)

def checked_pin(pin,document=None):
    raw=Path(pin['path']).read_bytes()
    require(hashlib.sha256(raw).hexdigest()==pin['sha256'],'HISTORICAL_SOURCE_CHANGED')
    if document is not None:require(json.loads(raw)==document,'HISTORICAL_DOCUMENT_CHANGED')
    return json.loads(raw)

def retained_history(checkpoint,accounting):
    previous=checkpoint['fresh_local_work'];prior=previous['historical_checkpoint']
    require(prior['state_sha256']==seal(prior) and set(prior['requests'])=={OLD,FAILED},'EARLIER_HISTORY_CHANGED')
    records={**deepcopy(prior['requests']),**deepcopy(checkpoint['requests'])}
    require(set(records)=={OLD,FAILED,LAST},'EXACT_THREE_HISTORIES_REQUIRED')
    old_stream=tokens.restore(prior['collector'])['streams'][records[OLD]['stream']]
    streams={OLD:{key:old_stream[key] for key in ('epoch','cursor','watermark')},
        LAST:{'epoch':accounting['canonical']['session_state']['stream_epoch'],
              'cursor':accounting['cursor'],'watermark':accounting['watermark']}}
    return records,streams,deepcopy(previous['historical_projection'])

def prepare_derived(checkpoint,companion,accounting,*,source_pins):
    for key,value in (('checkpoint',checkpoint),('companion',companion),('accounting',accounting)):
        checked_pin(source_pins[key],value)
    require(checkpoint['state_sha256']==seal(checkpoint),'CHECKPOINT_SEAL_INVALID')
    require(set(checkpoint['requests'])=={LAST},'EXACT_PREDECESSOR_REQUIRED')
    require(checkpoint['policy']['carry_in_tokens']==272648 and checkpoint['policy']['carry_in_admissions']==11
        and 272648+tokens.summary(tokens.restore(checkpoint['collector']))['known_observed_tokens']==295262
        and checkpoint['requests'][LAST]['settled'] is False,'PREDECESSOR_COUNTER_CHANGED')
    require(companion['status']=='FAILED_CAMPAIGN_NORMAL_CLEANUP_CONFIRMED'
        and companion['kind']=='NORMAL_CLOSURE_COMPANION_WITH_POST_EXIT_ACCOUNTING'
        and companion['charged_reservations']==12 and companion['observed_tokens']==295262
        and companion['normal_cleanup']['force_used'] is False
        and companion['normal_cleanup']['all_three_retained_handles_exited'] is True
        and companion['normal_cleanup']['tasks_absent'] is True
        and companion['request13_selected'] is False and companion['refunds']==0
        and companion['original_checkpoint']['sha256']==source_pins['checkpoint']['sha256']
        and companion['accounting']['sha256']==source_pins['accounting']['sha256'],'CLOSED_RECONCILIATION_REQUIRED')
    canonical=accounting['canonical'];session=canonical['session_state']
    require(accounting['kind']=='POST_EXIT_READONLY_ACCOUNTING_COMPANION_NOT_CONTROLLER'
        and accounting['request_id']==LAST and accounting['charged_reservations']==12
        and accounting['cumulative_observed_tokens']==295262 and accounting['request12_observed_tokens']==22614
        and accounting['original_checkpoint']['sha256']==source_pins['checkpoint']['sha256']
        and accounting['original_faults']==checkpoint['faults']
        and accounting['collector_request_state_observed_post_exit']=='settled_observed'
        and canonical['operation_receipt']['stage']=='CANCELLED'
        and session['lifecycle_state']=='CLOSED' and session['lease_state']=='CLOSED'
        and accounting['native_pending_count']==0 and accounting['active_owned_slots']==0
        and accounting['cursor']==accounting['watermark']
        and accounting['refunds']==0 and accounting['new_admissions_during_reconciliation']==0,'ACCOUNTING_RECONCILIATION_REQUIRED')
    record=checkpoint['requests'][LAST]
    require(record['operation']==canonical['operation_id'] and record['session']==canonical['scope']['session_id']
        and all(canonical['scope'][key]==value for key,value in record['scope'].items()),'RECONCILED_SCOPE_CHANGED')
    records,streams,projection=retained_history(checkpoint,accounting)
    out=deepcopy(checkpoint)
    out['fresh_local_work']={'classification':'NEW_INTENTS_AFTER_RECONCILED_CANCELLATION',
        'source_pins':deepcopy(source_pins),'historical_checkpoint':deepcopy(checkpoint),
        'historical_records':records,'historical_record_count':3,'historical_streams':streams,
        'historical_projection':projection,'immediate_accounting':deepcopy(accounting),
        'historical_faults':deepcopy(checkpoint['faults']),
        'new_request_ids':list(REQUEST_IDS.values()),'reservation_refunded':False,
        'initial_cumulative_tokens':295262,'initial_cumulative_reservations':12,
        'historical_reobservation':'All three retained records checked every poll; any journal or proof change closes admission pending explicit accounting reconciliation.'}
    out['requests']={};out['collector']=tokens.checkpoint(tokens.initial_state())
    out['policy']=deepcopy(POLICY);out['ancestry']=deepcopy(ANCESTRY)
    out['faults']=[];out['independent_owner_stops']={};out.pop('independent_observation',None)
    out['state_sha256']=seal(out)
    return out

class FreshWorkController(Controller):
    def __init__(self,*args,original_control_root,amendment_path,amendment_sha256,**kwargs):
        self.original_control_root=Path(original_control_root).resolve()
        self.amendment_path=Path(amendment_path).resolve();self.amendment_sha256=amendment_sha256
        require(Path(args[0]).resolve()==self.original_control_root/'work-revision15/private/controller.json','NEW_WORK_CONTROLLER_PATH_INVALID')
        super().__init__(*args,**kwargs)

    def _approval_valid(self):
        try:
            history=self.data['fresh_local_work'];original=history['historical_checkpoint']
            authority=original['fresh_local_work']['historical_checkpoint']
            raw=self.approval_path.read_bytes();receipt=json.loads(raw)
            amendment_raw=self.amendment_path.read_bytes();amendment=json.loads(amendment_raw)
            return (hashlib.sha256(raw).hexdigest()==self.approval_sha256
                and receipt.get('status')=='USER_APPROVED' and receipt.get('proposal_revision')==14
                and receipt.get('proposal_sha256')==self.expected_proposal_sha256
                and receipt.get('policy')==authority['policy'] and receipt.get('ancestry')==authority['ancestry']
                and bool(receipt.get('user_quote')) and receipt.get('campaign_root')==str(self.root)
                and receipt.get('control_root')==str(self.original_control_root)
                and hashlib.sha256(amendment_raw).hexdigest()==self.amendment_sha256
                and amendment.get('policy')==POLICY and amendment.get('controller_ancestry')==ANCESTRY
                and amendment.get('campaign_root')==str(self.root)
                and amendment.get('control_root')==str(self.original_control_root)
                and amendment.get('request_ids')==REQUEST_IDS and amendment.get('remote_execution_enabled') is False
                and amendment.get('source_authority')=={'proposal_sha256':self.expected_proposal_sha256,'approval_sha256':self.approval_sha256}
                and all(amendment.get('basis',{}).get(k)==history['source_pins'][k] for k in ('checkpoint','companion','accounting')))
        except (OSError,ValueError,TypeError,KeyError,AttributeError):return False

    def _validate(self):
        super()._validate()
        history=self.data.get('fresh_local_work',{});original=history.get('historical_checkpoint',{})
        require(history.get('classification')=='NEW_INTENTS_AFTER_RECONCILED_CANCELLATION'
            and history.get('reservation_refunded') is False and original.get('state_sha256')==seal(original)
            and set(original.get('requests',{}))=={LAST} and history.get('historical_faults')==original.get('faults')
            and history.get('historical_record_count')==3
            and set(self.data['requests']).issubset({USEFUL,CONTINUATION}),'NEW_WORK_HISTORY_CHANGED')
        checked_pin(history['source_pins']['checkpoint'],original)
        checked_pin(history['source_pins']['accounting'],history['immediate_accounting'])
        records,streams,projection=retained_history(original,history['immediate_accounting'])
        require(history['historical_records']==records and history['historical_streams']==streams
            and history['historical_projection']==projection,'RETAINED_HISTORY_CHANGED')

    def _poll_historical(self):
        history=self.data['fresh_local_work']
        for request_id,record in history['historical_records'].items():
            self._check_poll()
            reader=self._readers.get(record['lane']);journal=self._journals.get(record['lane'])
            require(reader is not None and journal is not None,'HISTORICAL_OBSERVER_REQUIRED')
            observed=reader.read(request_id)
            require(observed is not None and all(observed['scope'][k]==v for k,v in record['scope'].items())
                and observed['operation_id']==record['operation'] and observed['scope']['session_id']==record['session'],'HISTORICAL_SCOPE_CHANGED')
            session=observed.get('session_state') or {}
            if request_id in (OLD,LAST):
                require(session.get('lifecycle_state')=='CLOSED' and session.get('lease_state')=='CLOSED'
                    and (observed.get('operation_receipt') or {}).get('stage')=='CANCELLED','HISTORICAL_TERMINAL_CHANGED')
                stream=history['historical_streams'][request_id]
                require(session.get('stream_epoch')==stream['epoch'],'HISTORICAL_EPOCH_CHANGED')
                page=journal.read(observed['scope'],stream['cursor'])
                require(page is not None and page['stream_epoch']==stream['epoch'] and not page['events']
                    and page['committed_contiguous']==stream['watermark'] and not page['has_more'],'HISTORICAL_JOURNAL_CHANGED')
            else:
                expected={k:v for k,v in history['historical_projection']['canonical_receipts'][0].items() if k!='operation_id'}
                require(session.get('lifecycle_state')=='FAILED' and session.get('lease_state')=='CLOSED'
                    and session.get('stream_epoch') is None and observed.get('opening_receipt')==expected,'HISTORICAL_PRELAUNCH_CHANGED')
                current=journal.read_unclaimed(observed['scope'],observed['opening_operation_id'])
                projection=history['historical_projection']
                require(current['launch']==projection['launch'] and current['counts']==projection['counts']
                    and current['action_counts']==projection['action_counts'] and current['operations']==projection['operations']
                    and not current['active_slots'],'HISTORICAL_NATIVE_PROOF_CHANGED')
        self._check_poll()

    def _new_session_allowed(self,lane,stage):
        return lane=='local' and stage=='useful_work' and not self.data['requests']

    def _contain_faults(self):
        super()._contain_faults()
        if self.data['faults']:
            for lane in sorted({r['lane'] for r in self.data['fresh_local_work']['historical_records'].values()}):
                if lane in self.stops:self._stop_owner_once(lane,self.data['faults'][0])

    def start_work(self,request_id,lane,text,*,binding,checkpoint,stage='useful_work',new_session=False):
        require(lane=='local','REMOTE_WORK_HELD_FOR_SEPARATE_QUALIFICATION')
        if request_id==USEFUL:
            require(stage=='useful_work' and new_session and not self.data['requests'],'FRESH_USEFUL_SELECTION_REQUIRED')
        elif request_id==CONTINUATION:
            prior=self.data['requests'].get(USEFUL,{})
            require(stage=='continuation' and not new_session and prior.get('settled') is True
                and prior.get('canonical_stage')=='SUCCEEDED' and checkpoint.get('session_id')==prior.get('session'),'SUCCESSFUL_USEFUL_REQUIRED')
        else:raise Refused('NEW_INTENT_OUTSIDE_SELECTION')
        return super().start_work(request_id,lane,text,binding=binding,checkpoint=checkpoint,stage=stage,new_session=new_session)

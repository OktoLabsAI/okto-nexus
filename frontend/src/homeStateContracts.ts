import type {HomeDeliverySemantics,HomeOperationalStatus,HomeOperationalSummary,HomePlacementReason,HomeStateCount} from './homeTypes';

const record=(value:unknown):value is Record<string,unknown>=>value!==null&&typeof value==='object'&&!Array.isArray(value);
const text=(value:unknown):value is string=>typeof value==='string'&&value.length>0;
const nullableText=(value:unknown)=>value===null||text(value);
const oneOf=(value:unknown,values:readonly string[])=>typeof value==='string'&&values.includes(value);
const validPendingKinds=(value:unknown)=>record(value)&&['question','approval','decision','verification'].every(key=>validHomeStateCount(value[key]));
export function validHomeStateCount(value:unknown):value is HomeStateCount {
  return record(value)&&typeof value.total_is_exact==='boolean'&&
    (value.value===null?!value.total_is_exact:typeof value.value==='number'&&Number.isSafeInteger(value.value)&&value.value>=0);
}
export function validHomeOperationalStatus(value:unknown):value is HomeOperationalStatus {
  if(!record(value)||value.version!==1||
    !oneOf(value.connection,['connected','connecting','reconnecting','disconnected','registered','unknown'])||
    !oneOf(value.activity,['working','idle','queued','waiting_user','waiting_agent','awaiting_confirmation','no_active_session','recovering','unknown'])||
    !oneOf(value.blocking,['full','partial','none','unknown'])||!oneOf(value.freshness,['current','stale','unavailable'])||
    !nullableText(value.as_of)||!nullableText(value.state_since)||!nullableText(value.reason_code)||
    !validHomeStateCount(value.pending_actions)||!validHomeStateCount(value.running_sessions)||!validHomeStateCount(value.blocked_sessions)||
    !validPendingKinds(value.pending_by_kind)||
    !Array.isArray(value.pending_request_ids)||!value.pending_request_ids.every(text)||new Set(value.pending_request_ids).size!==value.pending_request_ids.length||
    typeof value.has_more_pending_requests!=='boolean'||!nullableText(value.pending_requests_cursor)||
    typeof value.awaiting_native_confirmation!=='boolean')return false;
  if(value.has_more_pending_requests!==!!value.pending_requests_cursor)return false;
  if(value.activity==='idle'&&(value.connection!=='connected'||value.freshness!=='current'||value.blocking!=='none'||value.awaiting_native_confirmation))return false;
  return true;
}
export function validHomeOperationalSummary(value:unknown):value is HomeOperationalSummary {
  return record(value)&&['connected','working','idle','queued','unconfirmed','disconnected','blocked_harnesses',
    'pending_actions','visible_notifications','resume_confirmations'].every(key=>validHomeStateCount(value[key]));
}
export function validHomePlacement(value:unknown):value is HomePlacementReason {
  return oneOf(value,['normal_monitoring','human_block_confirmed','awaiting_native_confirmation','monitoring_unconfirmed']);
}
export function validHomeDeliverySemantics(value:unknown):value is HomeDeliverySemantics {
  if(!record(value)||value.version!==1||!oneOf(value.scope,['turn','handoff','external_report'])||
    !oneOf(value.evidence,['canonical','reported'])||
    !oneOf(value.execution_outcome,['succeeded','failed','cancelled','rejected','unknown','not_applicable'])||
    !oneOf(value.task_state,['open','claimed','verifying','completed','rejected','cancelled','unknown','not_applicable'])||
    !oneOf(value.verification,['approved','rejected','pending','unknown','not_applicable'])||
    !nullableText(value.verification_evidence_ref)||!oneOf(value.cleanup,['pending','complete','unknown','not_applicable'])||
    !oneOf(value.content_state,['available','pending','not_captured','unavailable'])||
    typeof value.historical!=='boolean'||!text(value.semantic_revision))return false;
  if(value.verification==='approved'&&(value.evidence!=='canonical'||!text(value.verification_evidence_ref)))return false;
  if(value.evidence==='reported'&&value.verification==='approved')return false;
  return true;
}

import type {HomeDeliverySemantics,HomeHarnessCard,HomeHarnessRequest,HomePendingKind,HomeStateCount} from './homeTypes';
import {validHomeDeliverySemantics} from './homeStateContracts';

export type HomeBadge={label:string;tone:'neutral'|'working'|'attention'|'success'|'warning'};
const actions:Record<HomePendingKind,{pending:string;waiting:string;button:string}>={
  question:{pending:'Response pending',waiting:'Waiting for your response',button:'Respond'},
  approval:{pending:'Approval pending',waiting:'Waiting for your approval',button:'Review approval'},
  decision:{pending:'Decision pending',waiting:'Waiting for your decision',button:'Review request'},
  verification:{pending:'Verification pending',waiting:'Waiting for your verification',button:'Verify delivery'},
  unknown:{pending:'Action pending',waiting:'Waiting for your action',button:'Review request'},
};
export function requestKind(item:HomeHarnessRequest):HomePendingKind {
  if(item.action_kind&&item.action_kind in actions)return item.action_kind;
  const kind=item.request.kind;
  return kind==='native_question_pending'?'question':['native_permission_pending','approval_pending'].includes(kind)?'approval':
    kind==='verification_pending'?'verification':'unknown';
}
export const homeActionText=(kind:HomePendingKind)=>actions[kind];
export function homeCountText(count:HomeStateCount|undefined,label:string):string {
  if(!count||count.value===null)return `${label}: unknown`;
  if(count.value===1)label=({'actions':'action','harnesses paused':'harness paused','resume confirmations':'resume confirmation'})[label]??label;
  return `${count.total_is_exact?'':'At least '}${count.value} ${label}`;
}
export function harnessBadges(card:HomeHarnessCard):HomeBadge[] {
  const state=card.operational_status;
  if(!state)return [{label:({registered:'Registered harness',waiting_for_user:'Waiting for your response',
    awaiting_confirmation:'Waiting for confirmation',working:'Working',unknown:'Activity unknown'})[card.activity_state]??'Activity unknown',tone:'neutral'}];
  let label:string,tone:HomeBadge['tone']='neutral';
  if(state.reason_code==='NATIVE_RESPONSE_NOT_APPLIED'){
    label='Response not applied';tone='warning';
  }else if(state.awaiting_native_confirmation&&card.placement_reason==='awaiting_native_confirmation'){
    label='Waiting for resume confirmation';tone='attention';
  }else if(state.blocking==='full'){
    const kinds=Object.entries(state.pending_by_kind).filter(([,c])=>c.value!==null&&c.value>0).map(([k])=>k as HomePendingKind);
    label=state.pending_actions.value!==null&&state.pending_actions.value>1?`Waiting for ${state.pending_actions.value} actions`:
      actions[kinds.length===1?kinds[0]:'unknown'].waiting;tone='attention';
  }else{
    label=({working:'Working',idle:'Idle',queued:'Queued',waiting_user:'Session waiting for you',waiting_agent:'Waiting for another agent',
      awaiting_confirmation:'Confirmation pending',no_active_session:'No active session',recovering:'Recovering',unknown:'State unconfirmed'})[state.activity];
    tone=state.activity==='working'?'working':state.activity==='idle'?'success':'neutral';
    if(state.activity==='unknown')label=({registered:'Registered harness',connecting:'Connecting',reconnecting:'Reconnecting',
      disconnected:'Disconnected',connected:'State unconfirmed',unknown:'State unconfirmed'})[state.connection];
  }
  const badges:HomeBadge[]=[{label,tone}];
  if(state.blocking!=='full'&&card.placement_reason!=='awaiting_native_confirmation'){
    const count=state.pending_actions.value;
    if(count!==null&&count>0){
      const kinds=Object.entries(state.pending_by_kind).filter(([,c])=>c.value!==null&&c.value>0).map(([k])=>k as HomePendingKind);
      badges.push({label:count>1?`${state.pending_actions.total_is_exact?'':'At least '}${count} actions pending`:actions[kinds.length===1?kinds[0]:'unknown'].pending,tone:'attention'});
    }else if(state.awaiting_native_confirmation)badges.push({label:'Confirmation pending',tone:'attention'});
  }
  return badges;
}
export function deliveryPresentation(value:HomeDeliverySemantics|undefined,fallback:{outcome?:string;evidence:'canonical'|'reported'}):{
  title:string;badges:string[];
} {
  if(!value||!validHomeDeliverySemantics(value)){
    if(fallback.evidence==='reported')return {title:'Completion reported',badges:['Not verified by Nexus']};
    const title=({SUCCEEDED:'Turn completed',FAILED:'Execution ended with failure',CANCELLED:'Execution cancelled',REJECTED:'Delivery rejected',COMPLETED:'Task completed'})[fallback.outcome??'']??'Result available';
    return {title,badges:[]};
  }
  const badges:string[]=[];
  let title='Result available';
  if(value.evidence==='reported'){title='Completion reported';badges.push('Not verified by Nexus');}
  else if(value.execution_outcome==='failed')title='Execution ended with failure';
  else if(value.execution_outcome==='cancelled')title='Execution cancelled';
  else if(value.verification==='rejected')title='Delivery not approved';
  else if(value.execution_outcome==='rejected'||value.task_state==='rejected')title='Delivery / task rejected';
  else if(value.task_state==='completed'&&!value.historical)title='Task completed';
  else if(value.scope==='turn')title=value.task_state==='not_applicable'?'Response available':'Turn result available';
  else if(value.scope==='handoff')title='Delivery available';
  if(!value.historical&&['open','claimed'].includes(value.task_state))badges.push('Task not yet completed');
  if(value.verification==='pending')badges.push('Awaiting verification');
  if(value.verification==='approved')badges.push(value.historical?'Verified previous delivery':'Delivery verified');
  if(value.cleanup==='pending')badges.push('Cleanup pending');
  if(value.content_state!=='available'&&value.evidence==='canonical'){
    badges.push(value.content_state==='pending'?'Output not available yet':value.content_state==='not_captured'?'Output not captured':'Output unavailable');
    if(title==='Response available'||title==='Turn result available'||title==='Delivery available')title='Execution ended';
  }
  if(value.historical)badges.push('Previous attempt');
  return {title,badges};
}

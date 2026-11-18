import type {HomeBoardColumn,HomeHarnessCard as HarnessCard,HomeHarnessEvent,HomeHarnessRequest,HomeHarnessDelivery} from '../../homeTypes';
import {homeEntryStateLabel,homeFocus} from './HomeCards';
import {attentionDescription,primaryAttentionAction} from '../../attentionPresentation';
import {deliveryPresentation,harnessBadges,homeActionText,requestKind} from '../../homeStatePresentation';
import {isUntitledHomeWork} from '../../homePresentation';
import {formatTime} from '../../timeFormat';

const harnessName=(id:string)=>({codex_app_server:'Codex',claude_stream:'Claude',pi_rpc:'Pi'}[id]??'Other harness');
const requestButton=(item:HomeHarnessRequest)=>{
  const action=primaryAttentionAction(item.request);
  return action==='respond_native'?'Respond':action==='decide_native'||action==='decide_approval'?'Review approval':action==='verify_handoff'?'Verify delivery':'View request';
};
export function harnessEventAction(event:HomeHarnessEvent):string {
  const action=event.attention?primaryAttentionAction(event.attention):null;
  if(action==='respond_native')return 'Review question';
  if(action==='decide_native'||action==='decide_approval')return 'Review approval';
  if(event.kind==='attention')return 'Review update';
  return event.kind==='result'?'View delivery':event.kind==='session'?'View session':event.kind==='external'?'View report':'View work';
}

/** Server-ordered event previews from a complete registered-connection relation. */
export function HomeHarnessCard({card,column,blocked,onActivity,onEvent,onRequest,onRequests,showProject=false,projectLabel,stale=false}: {
  card:HarnessCard;column:HomeBoardColumn;blocked:boolean;onActivity:()=>void;onEvent:(event:HomeHarnessEvent)=>void;
  onRequest?:(request:HomeHarnessRequest)=>void;onRequests?:()=>void;showProject?:boolean;projectLabel?:string;stale?:boolean;
}) {
  const connection=card.connection;
  const status=card.operational_status,badges=harnessBadges(card);
  const pending=status?.pending_actions.value;
  const requests=card.requests_preview??card.blocking_requests??[];
  const onlyRequest=column==='needs_you'&&pending===1&&status?.pending_actions.total_is_exact===true&&
    !status.has_more_pending_requests&&requests.length===1?requests[0]:null;
  const confirming=card.placement_reason==='awaiting_native_confirmation';
  const showRequests=column==='needs_you'&&!confirming&&((pending??0)>0||requests.length>0);
  const primary=onlyRequest?requestButton(onlyRequest):
    showRequests?(status?.pending_actions.total_is_exact&&pending!==null&&pending!==undefined?`View ${pending} actions`:'View actions'):
    confirming?'Follow confirmation':column==='active'?'Follow activity':'View context';
  const open=()=>onlyRequest&&onRequest?onRequest(onlyRequest):showRequests&&onRequests?onRequests():onActivity();
  return <li className="panel p-4 min-w-0 space-y-3" data-home-harness={card.id}>
    <header><h4 className="font-semibold break-words">{connection.connect_id?<><span className="text-xs font-normal text-surface-500">Harness ID: </span>{connection.connect_id}</>:connection.agent_label||'Unnamed collaborator'}</h4>
      {connection.connect_id?<p className="text-xs text-surface-500 break-words">Collaborator: {connection.agent_label||'Name unavailable'}</p>:
        <p className="text-xs text-surface-500">Harness ID not assigned</p>}
      <p className="text-sm text-surface-500 break-words">{[harnessName(connection.harness_id),connection.host_label||'Host not reported'].join(' · ')}</p>
      {showProject&&<p className="text-xs text-surface-500 break-words">Project: {projectLabel||connection.workspace_label||connection.workspace_id}</p>}
      <div className="flex flex-wrap gap-2 mt-2" aria-label="Harness status">{badges.map((badge,index)=><span key={index}
        data-home-badge={badge.label} className={`rounded-md border px-2 py-1 text-xs font-medium ${!stale&&badge.tone==='attention'?'border-amber-400 text-amber-800 dark:text-amber-200':!stale&&badge.tone==='working'?'border-sky-400 text-sky-800 dark:text-sky-200':'border-surface-300 dark:border-surface-600'}`}>
        {stale&&index===0?'Last known: ':''}{badge.label}</span>)}</div>
      {status?.freshness!=='current'&&status&&<p className="text-xs text-surface-500">Connection evidence {status.freshness}. Inspect for current details.</p>}
      {!status&&card.blocks_harness===null&&<p className="text-xs text-surface-500">Blocking status unknown</p>}
      {confirming&&<p className="text-sm">Your decision is recorded. No further response is required while confirmation is pending.</p>}
    </header>
    {card.reminder_snoozed&&<p className="text-xs text-surface-500">Reminder snoozed. This does not resume the harness.</p>}
    <ul className="space-y-3" aria-label="Activity preview">{card.events_preview.map(event=><li key={event.id} className="border-l-2 border-surface-200 pl-3" data-home-event={event.id}>
      {!isUntitledHomeWork(event)?<p className="text-sm font-medium break-words">{event.title}</p>:
        event.attention&&<p className="text-sm font-medium break-words">{attentionDescription(event.attention).title}</p>}
      <p className="text-xs text-surface-500">{homeEntryStateLabel(event)}</p>
      {(event.target||event.attention)&&(event.kind!=='attention'||!status&&column==='needs_you')&&<button type="button" className={`text-sm underline ${homeFocus}`} disabled={blocked} onClick={()=>onEvent(event)}>{harnessEventAction(event)}</button>}
    </li>)}</ul>
    {card.events_total===0&&<p className="text-sm text-surface-500">No tracked activity.</p>}
    {Object.values(card.events_summary).some(value=>value===null)&&<p className="text-xs text-surface-500">Activity coverage incomplete.</p>}
    <button type="button" className={`btn btn-secondary w-full ${homeFocus}`} disabled={blocked} onClick={open}>{primary}</button>
  </li>;
}

/** Requests and reported deliveries identify their proven originating harness. */
export function HomeHarnessSignalCard({item,blocked,onOpen,showProject=false,projectLabel}: {
  item:HomeHarnessRequest|HomeHarnessDelivery;blocked:boolean;onOpen:()=>void;
  showProject?:boolean;projectLabel?:string;
}) {
  const names=item.harness_refs.map(({connection:c})=>[c.connect_id?`Harness ID: ${c.connect_id}`:c.agent_label||'Unnamed collaborator',harnessName(c.harness_id),c.host_label||'Host not reported'].join(' · '));
  const label=item.kind==='delivery'?'View result':requestButton(item);
  const meaning=item.kind==='delivery'?deliveryPresentation(item.delivery_semantics??item.result?.delivery_semantics,
    {outcome:item.result?.outcome,evidence:item.completion_evidence}):null;
  return <li className="panel p-4 min-w-0 space-y-3" data-home-signal={item.id} data-home-signal-kind={item.kind}>
    <header><p className="text-xs font-medium text-surface-500 break-words">{names.length?names.join(' · '):'Origin unavailable'}</p>
      <h4 className="font-semibold break-words">{item.kind==='delivery'?(item.result?.title??(item.report?attentionDescription(item.report).title:'Completion reported')):attentionDescription(item.request).title}</h4></header>
    {showProject&&<p className="text-xs text-surface-500 break-words">Project: {projectLabel||item.harness_refs[0]?.connection.workspace_label||item.entry.workspace_id}</p>}
    {item.kind==='request'?<div className="space-y-2"><span className="inline-block rounded-md border border-amber-400 px-2 py-1 text-xs font-medium">{homeActionText(requestKind(item)).pending}</span>
      <p className="text-sm">{item.blocks_session===true&&item.blocks_harness===false?'Blocks this session; the harness continues other work':item.blocks_harness===null?'Blocking status unconfirmed':item.blocks_harness?'The harness is waiting for this action':'The harness can continue other work'}</p></div>:
      <div className="space-y-2"><p className="text-sm font-medium">{meaning?.title}</p>
        <div className="flex flex-wrap gap-2">{meaning?.badges.map(badge=><span key={badge} className="rounded-md border border-surface-300 dark:border-surface-600 px-2 py-1 text-xs">{badge}</span>)}</div>
        {item.result?.created_at&&<p className="text-xs text-surface-500">Received <time dateTime={item.result.created_at}>{formatTime(item.result.created_at)}</time></p>}
      </div>}
    <button type="button" className={`btn btn-secondary ${homeFocus}`} disabled={blocked} onClick={onOpen}>{label}</button>
  </li>;
}

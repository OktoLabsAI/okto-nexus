import type {HomeBoardColumn,HomeHarnessCard as HarnessCard,HomeHarnessEvent,HomeHarnessRequest,HomeHarnessDelivery} from '../../homeTypes';
import {homeEntryStateLabel,homeFocus} from './HomeCards';
import {attentionDescription,primaryAttentionAction} from '../../attentionPresentation';

const harnessName=(id:string)=>({codex_app_server:'Codex',claude_stream:'Claude',pi_rpc:'Pi'}[id]??'Other harness');
export function harnessEventAction(event:HomeHarnessEvent):string {
  const action=event.attention?primaryAttentionAction(event.attention):null;
  if(action==='respond_native')return 'Review question';
  if(action==='decide_native'||action==='decide_approval')return 'Review approval';
  if(event.kind==='attention')return 'Review update';
  return event.kind==='result'?'View delivery':event.kind==='session'?'View session':event.kind==='external'?'View report':'View work';
}

/** Server-ordered event previews from a complete registered-connection relation. */
export function HomeHarnessCard({card,column,blocked,onActivity,onEvent}: {
  card:HarnessCard;column:HomeBoardColumn;blocked:boolean;onActivity:()=>void;onEvent:(event:HomeHarnessEvent)=>void;
}) {
  const connection=card.connection;
  const labels={registered:'Registered harness',waiting_for_user:'Waiting for your response',awaiting_confirmation:'Waiting for confirmation',working:'Working',unknown:'Activity unknown'};
  return <li className="panel p-4 min-w-0 space-y-3" data-home-harness={card.id}>
    <header><h4 className="font-semibold break-words">{connection.agent_label||'Unnamed collaborator'}</h4>
      <p className="text-sm text-surface-500 break-words">{[harnessName(connection.harness_id),connection.host_label||'Host not reported'].join(' · ')}</p>
      <p className="text-sm mt-1">{labels[card.activity_state]??'Activity unknown'}</p>
      {card.blocks_harness===null&&<p className="text-xs text-surface-500">Blocking status unknown</p>}</header>
    {card.reminder_snoozed&&<p className="text-xs text-surface-500">Reminder snoozed. This does not resume the harness.</p>}
    <ul className="space-y-3" aria-label="Activity preview">{card.events_preview.map(event=><li key={event.id} className="border-l-2 border-surface-200 pl-3" data-home-event={event.id}>
      <p className="text-sm font-medium break-words">{event.title}</p>
      <p className="text-xs text-surface-500">{homeEntryStateLabel(event)}</p>
      {(event.target||event.attention)&&!(column==='active'&&event.kind==='attention')&&<button type="button" className={`text-sm underline ${homeFocus}`} disabled={blocked} onClick={()=>onEvent(event)}>{harnessEventAction(event)}</button>}
    </li>)}</ul>
    {card.events_total===0&&<p className="text-sm text-surface-500">No tracked activity.</p>}
    <p className="text-xs text-surface-500">{Object.entries(card.events_summary).filter(([,count])=>count===null||count>0).map(([kind,count])=>`${count===null?'Unknown':count} ${kind==='attention'?'questions and updates':kind}`).join(' · ')}</p>
    <button type="button" className={`btn btn-secondary w-full ${homeFocus}`} disabled={blocked} onClick={onActivity}>{column==='active'?'Inspect execution':'View activity'}</button>
    {column==='active'&&<div className="space-y-1">
      <button type="button" className="btn btn-secondary w-full" disabled aria-describedby={`reconnect-help-${card.id}`}>Reconnect</button>
      <p id={`reconnect-help-${card.id}`} className="text-xs text-surface-500">Individual reconnection is not available for this host.</p>
    </div>}
  </li>;
}

/** Requests and reported deliveries identify their proven originating harness. */
export function HomeHarnessSignalCard({item,blocked,onOpen}: {
  item:HomeHarnessRequest|HomeHarnessDelivery;blocked:boolean;onOpen:()=>void;
}) {
  const names=item.harness_refs.map(({connection:c})=>[c.agent_label||'Unnamed collaborator',harnessName(c.harness_id),c.host_label||'Host not reported'].join(' · '));
  const action=item.kind==='request'?primaryAttentionAction(item.request):null;
  const label=item.kind==='delivery'?'View delivery':action==='respond_native'?'Review question':
    action==='decide_native'||action==='decide_approval'?'Review approval':'Review request';
  return <li className="panel p-4 min-w-0 space-y-3" data-home-signal={item.id} data-home-signal-kind={item.kind}>
    <header><p className="text-xs font-medium text-surface-500 break-words">{names.length?names.join(' · '):'Origin unavailable'}</p>
      <h4 className="font-semibold break-words">{item.kind==='delivery'?(item.result?.title??(item.report?attentionDescription(item.report).title:'Completion reported')):attentionDescription(item.request).title}</h4></header>
    {item.kind==='request'?<p className="text-sm">{item.blocks_harness===null?'Blocking status unknown':item.blocks_harness?'Waiting for your response':'The harness can continue other work'}</p>:
      <p className="text-sm">{item.completion_evidence==='reported'?'Completion reported':'Completion recorded'}{item.result?` · Outcome: ${item.result.outcome}`:''}. Review the delivery and its verification state.</p>}
    <button type="button" className={`btn btn-secondary ${homeFocus}`} disabled={blocked} onClick={onOpen}>{label}</button>
  </li>;
}

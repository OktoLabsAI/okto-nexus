import {useEffect, useRef, useState, type ReactNode} from 'react';
import {api, ApiError} from '../../api';
import {ArrowUpRight, Eye} from 'lucide-react';
import type {HomeActivity, HomeResult, HomeSection, HomeSectionName, HomeTarget, HomeSummary, HomeAgent, HomeOverview,
  HomeEntry,HomeEntryGroup,HomeEntryPage,HomeSessionRef,HomeEntryPartition} from '../../homeTypes';
import type {HomeState} from '../../homeController';
import type {AttentionAction, AttentionOccurrence} from '../../attentionTypes';
import {homeCounterLabel, homeSectionLabel, homeStateLabel, homeResultLabel,homeTargetActionLabel} from '../../homePresentation';
import {attentionActionLabels, attentionDescription, primaryAttentionAction} from '../../attentionPresentation';
import {useWorkspaceName} from '../WorkspaceNames';
import {formatTime} from '../../timeFormat';

export const homeFocus = 'focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent-500';
export function homeAnnouncementIds(snapshot: HomeOverview): Set<string> {
  return new Set([...snapshot.work.items.map(item => item.id), ...snapshot.results.items.map(item => item.id),
    ...snapshot.attention.items.map(item => item.attention_id), ...snapshot.server_attention.items.map(item => item.attention_id)]);
}
export function freshHomeOccurrence(snapshot: HomeOverview | null, staleSections: HomeSectionName[], item: AttentionOccurrence): AttentionOccurrence | undefined {
  const fresh = (section: 'attention'|'results'|'server_attention') => snapshot?.[section].status === 'ready' && !staleSections.includes(section);
  const rows = [...(fresh('attention') ? snapshot!.attention.items : []), ...(fresh('server_attention') ? snapshot!.server_attention.items : []),
    ...(fresh('results') ? snapshot!.results.items.flatMap(result => result.attention ? [result.attention] : []) : [])];
  return rows.find(row => row.attention_id === item.attention_id && row.source_revision === item.source_revision && row.seen_state.revision === item.seen_state.revision);
}
export function isQuietHome(snapshot: HomeOverview | null, stale = false): boolean {
  if (!snapshot || stale) return false;
  const empty = (section: HomeSection<unknown>) => section.status === 'ready' && section.total_is_exact === true && section.total === 0 && section.items.length === 0;
  return empty(snapshot.work) && empty(snapshot.results) && empty(snapshot.attention)
    && (snapshot.external_activity.status === 'disabled' || empty(snapshot.external_activity))
    && snapshot.agents.status === 'ready' && snapshot.agents.total_is_exact === true && snapshot.agents.total !== null;
}
export function HomeWelcome({needsSetup, externalDisabled, onSetup, onRequest}: {
  needsSetup: boolean; externalDisabled: boolean; onSetup: () => void; onRequest: () => void;
}) {
  return <section className="panel p-5 sm:p-6" aria-label="Get started" data-testid="home-welcome">
    <h2 className="text-lg font-semibold">{needsSetup ? 'Set up your first agent' : 'What would you like to work on?'}</h2>
    <p className="text-sm text-surface-500 mt-2">{needsSetup ? 'Connect an agent to start work in this scope.' : 'Start a tracked handoff or a conversation. There is no pending work or result in this snapshot.'}</p>
    <button type="button" className={`btn btn-primary mt-4 ${homeFocus}`} onClick={needsSetup ? onSetup : onRequest}>{needsSetup ? 'Set up an agent' : 'New request'}</button>
    {externalDisabled && <p className="text-xs text-surface-500 mt-3">External reports are disabled.</p>}
  </section>;
}

export function HomeCounters({summary}: {summary: HomeSummary}) {
  return <dl aria-label="Operational summary" className="grid grid-cols-2 xl:grid-cols-4 gap-3">
    {(['running', 'waiting_start', 'needs_you', 'results'] as const).map(key => <div key={key} className="panel p-4 min-w-0">
      <dt className="text-xs text-surface-500">{summary[key].label}</dt>
      <dd className="text-2xl font-semibold mt-1">{homeCounterLabel(summary[key])}</dd>
      <p className="text-xs text-surface-500 mt-1">{summary[key].unit.replaceAll('_', ' ')}</p>
    </div>)}
  </dl>;
}
export function HomeBlock<T>({title, section, stale, children, empty, onMore, loadingMore}: {
  title: string; section: HomeSection<T>; stale?: boolean; children: ReactNode; empty: ReactNode;
  onMore?: () => void; loadingMore?: boolean;
}) {
  const readable = section.status === 'ready' || section.status === 'partial';
  return <section aria-label={title} className="panel p-4 sm:p-5 min-w-0">
    <header className="flex items-baseline justify-between gap-3"><h2 className="text-base font-semibold">{title}</h2>
      <span className="text-xs text-surface-500">{section.total === null ? 'Total unknown' : `${section.total_is_exact ? '' : 'At least '}${section.total}`}</span></header>
    <p className="text-xs text-surface-500 mt-1">{stale ? 'Out of date · last authorized snapshot' : homeSectionLabel(section)}{section.as_of ? ` · ${formatTime(section.as_of)}` : ''}</p>
    {!readable && <p role="status" className="text-sm text-surface-500 py-4">{homeSectionLabel(section)}. {section.reason_code?.replaceAll('_', ' ')}</p>}
    {readable && (section.items.length ? children : <div className="text-sm text-surface-500 py-5">{empty}</div>)}
    {readable && section.has_more && <div className="pt-3 border-t border-surface-200 dark:border-surface-700 mt-3">
      <p className="text-xs text-surface-500">Showing {section.items.length}{section.total !== null ? ` of ${section.total}` : ''}.</p>
      {onMore ? <button type="button" className={`btn btn-secondary mt-2 ${homeFocus}`} disabled={loadingMore || stale} onClick={onMore}>{loadingMore ? 'Loading…' : `Load more ${title.toLowerCase()}`}</button>
        : <p className="text-xs text-surface-500">More information is available after refining the scope.</p>}
    </div>}
  </section>;
}
function WorkspaceLabel({id}: {id: string | null}) {const name = useWorkspaceName(id);return <span title={id || undefined}>{id ? name : 'Server-wide'}</span>;}
export function WorkRow({item, onOpen}: {item: HomeActivity; onOpen: (target: HomeTarget) => void}) {
  return <li className="py-3 min-w-0" data-home-item={item.id}>
    <div className="flex justify-between gap-3"><h3 className="font-medium text-sm break-words min-w-0">{item.title}</h3>
      {item.detail_target && <button type="button" className={`btn btn-secondary shrink-0 ${homeFocus}`} aria-label={`Inspect ${item.title}`} onClick={() => onOpen(item.detail_target!)}><ArrowUpRight size={15}/></button>}</div>
    <p className="text-sm mt-1">{homeStateLabel(item.display_state)}{item.evidence_status === 'unknown' ? ' · Evidence unknown' : ''}</p>
    {item.reason && <p className="text-xs text-surface-500 mt-1 break-words">{item.reason}</p>}
    <p className="text-xs text-surface-500 mt-1 break-words">{item.agent_ids.join(', ') || 'Owner not assigned'} · <WorkspaceLabel id={item.workspace_id}/></p>
    {item.state_since && <p className="text-xs text-surface-500">In this state since {formatTime(item.state_since)}</p>}
    {!item.detail_target && <p className="text-xs text-surface-500">Exact detail unavailable.</p>}
  </li>;
}
export function AttentionRow({item, stale, pending, onOpen, onSeen, onSnooze,level=3}: {
  item: AttentionOccurrence; stale: boolean; pending: boolean;
  onOpen: (item: AttentionOccurrence, action: AttentionAction) => void;
  onSeen: (item: AttentionOccurrence, seen: boolean) => void; onSnooze: (item: AttentionOccurrence) => void;
  level?:3|5;
}) {
  const description = attentionDescription(item), action = primaryAttentionAction(item);
  const Heading=level===5?'h5':'h3';
  return <li className="py-3 min-w-0" data-home-item={item.attention_id}>
    <Heading className="text-sm font-medium break-words">{description.title}</Heading><p className="text-sm mt-1 break-words">{description.reason}</p>
    <p className="text-xs text-surface-500 mt-1">{item.agent_id || 'Server'} · <WorkspaceLabel id={item.workspace_id}/>{item.seen_state.snoozed ? ' · Snoozed' : ''}</p>
    <div className="flex flex-wrap gap-2 mt-2">
      {action && <button type="button" className={`btn btn-primary ${homeFocus}`} onClick={() => onOpen(item, action)}>{level===5&&action==='respond_native'?'Review question':attentionActionLabels[action]}</button>}
      <button type="button" className={`btn btn-secondary ${homeFocus}`} disabled={stale || pending} onClick={() => onSeen(item, !item.seen_state.seen)}><Eye size={14}/>{item.seen_state.seen ? 'Mark unseen' : 'Mark seen'}</button>
      <button type="button" className={`btn btn-secondary ${homeFocus}`} disabled={stale || pending} onClick={() => onSnooze(item)}>{item.seen_state.snoozed ? 'Show again' : 'Snooze 1 hour'}</button>
    </div>
  </li>;
}
export async function downloadCurrentArtifact(read: () => Promise<Blob>, current: () => boolean, publish: (blob: Blob) => void) {
  const blob = await read();
  if (!current()) return false;
  publish(blob);return true;
}
function ArtifactDownload({workspace, artifact}: {workspace: string; artifact: HomeResult['artifacts'][number]}) {
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  const lock = useRef(false), access = useRef({active: true});
  useEffect(() => {
    const selected = {active: true};access.current = selected;
    const invalidate = () => {selected.active = false;};
    window.addEventListener('nexus-auth-expired', invalidate);
    window.addEventListener('nexus-operator-logout', invalidate);
    return () => {invalidate();window.removeEventListener('nexus-auth-expired', invalidate);window.removeEventListener('nexus-operator-logout', invalidate);};
  }, [workspace, artifact.artifact_id]);
  const download = async () => {
    if (lock.current || !access.current.active) return;lock.current = true;setBusy(true);setError('');
    const selected = access.current, current = () => selected.active && access.current === selected;
    try {
      // The canonical content API checks the selected workspace again. No filesystem or model-authored URL is opened.
      await downloadCurrentArtifact(() => api.artifactBlob(workspace, artifact.artifact_id), current, blob => {
      const url = URL.createObjectURL(blob), link = document.createElement('a');
      link.href = url;link.download = (artifact.filename || artifact.artifact_id).split(/[\\/]/).pop() || 'artifact';
      document.body.appendChild(link);link.click();link.remove();URL.revokeObjectURL(url);
      });
    } catch (failure) {
      if (!current()) return;
      if (failure instanceof ApiError && [401,403].includes(failure.status)) window.dispatchEvent(new Event('nexus-auth-expired'));
      if (current()) setError('The artifact is unavailable or access has changed. No alternative path was opened.');
    } finally {lock.current = false;if (current()) setBusy(false);}
  };
  return <span className="block"><button type="button" className={`text-xs underline ${homeFocus}`} disabled={busy} onClick={() => void download()}>{busy ? 'Loading artifact…' : artifact.filename || artifact.artifact_id}</button>{error && <span role="alert" className="block text-xs">{error}</span>}</span>;
}
export function ResultRow({item, stale, onOpen, onSeen, onContinue,level=3,allowContinue=true}: {
  item: HomeResult; stale: boolean; onOpen: (target: HomeTarget) => void;
  onSeen: (item: AttentionOccurrence, seen: boolean) => void; onContinue: (target: HomeTarget) => void;
  level?:3|5;
  allowContinue?:boolean;
}) {
  const Heading=level===5?'h5':'h3';
  return <li className="py-3 min-w-0" data-home-item={item.id}>
    <Heading className="font-medium text-sm break-words">{item.title}</Heading>
    <p className="text-xs mt-1">{homeResultLabel(item)}{item.verification_state && item.cleanup_state ? ` · Verification: ${item.verification_state}` : ''} · {item.view_state === 'not_tracked' ? 'Recent · seen state not tracked' : item.view_state === 'seen' ? 'Seen' : 'Unseen'}</p>
    {item.preview && <p className="text-sm mt-2 whitespace-pre-wrap break-words line-clamp-4">{item.preview}</p>}
    {item.truncated && <p className="text-xs text-surface-500">Preview truncated. Open the original result.</p>}
    <p className="text-xs text-surface-500 mt-1">{item.agent_id || 'Author unknown'} · <WorkspaceLabel id={item.workspace_id}/>{item.created_at ? ` · ${formatTime(item.created_at)}` : ''}</p>
    {item.artifacts.length > 0 && <div className="mt-2 space-y-1" aria-label="Authorized artifact references">{item.artifacts.map(artifact => <ArtifactDownload key={artifact.artifact_id} workspace={item.workspace_id} artifact={artifact}/>)}</div>}
    <div className="flex flex-wrap gap-2 mt-2">
      {item.detail_target && <button type="button" className={`btn btn-secondary ${homeFocus}`} onClick={() => onOpen(item.detail_target!)}>View delivery</button>}
      {item.attention && <button type="button" className={`btn btn-secondary ${homeFocus}`} disabled={stale} onClick={() => onSeen(item.attention!, !item.attention!.seen_state.seen)}>{item.view_state === 'seen' ? 'Mark unseen' : 'Mark seen'}</button>}
      {allowContinue&&item.detail_target && ['execution', 'result'].includes(item.detail_target.kind) && <button type="button" className={`btn btn-secondary ${homeFocus}`} disabled={stale} onClick={() => onContinue(item.detail_target!)}>Continue this session</button>}
    </div>
  </li>;
}
export function AgentRow({item}: {item: HomeAgent}) {
  return <li className="py-3 text-sm"><strong className="break-words">{item.name || item.agent_id}</strong>
    <p className="text-xs text-surface-500 mt-1">Presence: {item.presence} · Connection: {item.connectivity}</p>
    <p className="text-xs text-surface-500">Activity not reported{item.capabilities?.length ? ` · ${item.capabilities.join(', ')}` : ''}</p></li>;
}

export function homeEntriesAnnouncementIds(state:Pick<HomeState,'entries'|'board'|'entryChildren'>):Set<string>{
  const ids=new Set<string>();
  const entries=state.board?Object.values(state.board.columns).flatMap(column=>column.items):
    (state.entries?.items??[]).flatMap(group=>state.entryChildren[group.id]?.items??group.children);
  for(const entry of entries){
    ids.add(entry.id);for(const id of entry.attention_refs)ids.add(id);for(const id of entry.result_refs)ids.add(id);
    for(const ref of entry.sessions)ids.add(JSON.stringify([ref.server_id,ref.executor_id,ref.session_id]));
  }
  const root=state.board??state.entries;
  if(root?.server_attention.status==='ready')for(const occurrence of root.server_attention.items)ids.add(occurrence.attention_id);
  return ids;
}
export function freshHomeEntryOccurrence(state:Pick<HomeState,'entries'|'board'|'entryChildren'|'entryAttention'|'entryResults'|'status'|'paused'|'loading'|'staleSections'|'hasPendingUpdate'>,item:AttentionOccurrence):AttentionOccurrence|undefined{
  const root=state.board??state.entries;
  if(!root||!['ready','partial'].includes(root.status)||root.source_status.attention!=='ready'||
    !['ready','stale'].includes(state.status)||state.paused||state.loading||state.staleSections.length||state.hasPendingUpdate)return;
  const rows=root.server_attention.status==='ready'?[...root.server_attention.items]:[];
  const entries=state.board?Object.values(state.board.columns).flatMap(column=>column.items):
    (state.entries?.items??[]).flatMap(group=>state.entryChildren[group.id]?.items??group.children);
  for(const entry of entries){
    rows.push(...entry.attention_preview,...entry.results_preview.flatMap(result=>result.attention?[result.attention]:[]));
  }
  const revision=state.board?state.board.entry_revision:state.entries?.revision;
  for(const page of Object.values(state.entryAttention))if(page.revision===revision&&page.source_status.attention==='ready')rows.push(...page.items);
  for(const page of Object.values(state.entryResults))if(page.revision===revision&&page.source_status.attention==='ready')rows.push(...page.items.flatMap(result=>result.attention?[result.attention]:[]));
  return rows.find(row=>row.attention_id===item.attention_id&&row.source_revision===item.source_revision&&row.seen_state.revision===item.seen_state.revision);
}
export function isQuietEntries(page:HomeEntryPage<HomeEntryGroup>|null,stale=false):boolean{
  return !!page&&!stale&&page.status==='ready'&&page.total_is_exact&&page.total===0&&page.items.length===0&&
    Object.values(page.source_status).every(status=>status==='ready'||status==='disabled');
}
export function homeEntryStateLabel(entry:Pick<HomeEntry,'display_state'|'evidence'>):string{
  const passive:Record<string,string>={configured:'Configured',connected:'Connected',idle:'No work in progress',offline:'Offline',stale:'Information out of date'};
  const label=passive[entry.display_state]??homeStateLabel(entry.display_state);
  return entry.evidence==='confirmed'?label:`${entry.evidence==='reported'?'Reported':entry.evidence==='inferred'?'Inferred':'Evidence unknown'} · ${label}`;
}
export function HomeEntryGroupCard({group,page,expanded,onExpand,onMore,stale,loading,children}: {
  group:HomeEntryGroup;page?:HomeEntryPage<HomeEntry>;expanded:boolean;onExpand:()=>void;onMore:()=>void;
  stale:boolean;loading:boolean;children:(entry:HomeEntry)=>ReactNode;
}){
  const items=page?.items??group.children,total=page?page.total:group.children_total;
  const multiple=total===null||total>1,show=!multiple||expanded,more=page?page.has_more:group.has_more_children;
  return <li className="panel p-4 sm:p-5 min-w-0" data-home-group={group.id}>
    <header className="flex flex-wrap items-start justify-between gap-3">
      <div className="min-w-0"><h3 className="font-semibold break-words">{group.label}</h3>
        {multiple&&<p className="text-xs text-surface-500 mt-1">{total===null?'Item total unknown':`${total} items`}. Sessions and work are distinct.</p>}</div>
      {multiple&&<button type="button" className={`btn btn-secondary ${homeFocus}`} aria-expanded={expanded} aria-controls={`children-${group.id}`} onClick={onExpand}>{expanded?'Collapse':'Expand'}</button>}
    </header>
    {!show&&<ul className="mt-3 space-y-2 text-sm" aria-label="Context preview">{items.map(entry=><li key={entry.id} data-home-entry={entry.id} tabIndex={-1}>
      <span className="font-medium break-words">{entry.title}</span><span className="text-surface-500"> · {homeEntryStateLabel(entry)}</span>
    </li>)}</ul>}
    {show&&<div id={`children-${group.id}`}><ul className="divide-y divide-surface-200 dark:divide-surface-700">{items.map(entry=>children(entry))}</ul>
      {more&&<div className="pt-3 border-t border-surface-200 dark:border-surface-700"><p className="text-xs text-surface-500">Showing {items.length}{total===null?' of an unknown total':` of ${total}`} items.</p>
        <button type="button" className={`btn btn-secondary mt-2 ${homeFocus}`} disabled={stale||loading} onClick={onMore}>{loading?'Loading items…':'Load more items'}</button></div>}
    </div>}
  </li>;
}
export function HomeEntryRow({entry,serverId,sessionsPage,attentionPage,resultsPage,stale,preferencesStale=false,pendingIds,loading,onMore,onOpen,onContinue,onAttentionOpen,onSeen,onSnooze,presentation='row',allowContinue=true}: {
  entry:HomeEntry;serverId:string;sessionsPage?:HomeEntryPage<HomeSessionRef>;attentionPage?:HomeEntryPage<AttentionOccurrence>;resultsPage?:HomeEntryPage<HomeResult>;
  stale:boolean;preferencesStale?:boolean;pendingIds:string[];loading:HomeEntryPartition|null;onMore:(partition:'sessions'|'attention'|'results')=>void;
  onOpen:(target:HomeTarget)=>void;onContinue:(target:HomeTarget)=>void;
  presentation?:'row'|'card';allowContinue?:boolean;
  onAttentionOpen:(item:AttentionOccurrence,action:AttentionAction)=>void;onSeen:(item:AttentionOccurrence,seen:boolean)=>void;onSnooze:(item:AttentionOccurrence)=>void;
}){
  const sessions=sessionsPage?.items??entry.sessions,attention=attentionPage?.items??entry.attention_preview,results=resultsPage?.items??entry.results_preview;
  const sessionsTotal=sessionsPage?sessionsPage.total:entry.sessions_total,moreSessions=sessionsPage?sessionsPage.has_more:entry.has_more_sessions;
  const harness=entry.harness_label==='codex_app_server'?'Codex':entry.harness_label==='claude_stream'?'Claude':entry.harness_label==='pi_rpc'?'Pi':entry.harness_label;
  const sessionButton=(ref:HomeSessionRef)=><button type="button" className={`text-xs underline break-all ${homeFocus}`} onClick={()=>onOpen({kind:'session',...ref})}>View session {ref.session_id} · {ref.workspace_id} · {ref.executor_id}</button>;
  return <li className={`${presentation==='card'?'panel p-4':'py-4'} min-w-0`} data-home-entry={entry.id} data-home-item={entry.id}>
    <div className="flex flex-wrap justify-between gap-2"><h4 className="font-medium break-words">{entry.title}</h4>
      {entry.target&&<button type="button" className={`btn btn-secondary ${homeFocus}`} data-home-entry-open onClick={()=>onOpen(entry.target!)}>{homeTargetActionLabel(entry.target)}</button>}</div>
    <p className="text-sm mt-1">{homeEntryStateLabel(entry)}</p>
    <p className="text-xs text-surface-500 mt-1 break-words">{[entry.agent_label||entry.agent_id||'Owner not assigned',harness,entry.host_label].filter(Boolean).join(' · ')}</p>
    {entry.state_since&&<p className="text-xs text-surface-500">In this state since {formatTime(entry.state_since)}</p>}
    {!entry.target&&<p className="text-xs text-surface-500">Exact context unavailable.</p>}
    {sessions.length===1&&sessionsTotal===1&&entry.kind!=='session'&&<div className="mt-2">{sessionButton(sessions[0])}</div>}
    {(sessions.length>1||moreSessions||sessionsTotal===null)&&<details className="mt-3 text-sm"><summary className="cursor-pointer">{sessionsTotal===null?'Session total unknown':`${sessionsTotal} sessions`} · Choose an exact context</summary>
      <ul className="mt-2 space-y-2">{sessions.map(ref=><li key={JSON.stringify([ref.server_id,ref.executor_id,ref.session_id])}>{sessionButton(ref)}</li>)}</ul>
      {moreSessions&&<button type="button" className="btn btn-secondary mt-2" disabled={stale||loading!==null} onClick={()=>onMore('sessions')}>{loading==='sessions'?'Loading sessions…':'Load more sessions'}</button>}
    </details>}
    {(attention.length>0||entry.attention_total===null)&&<div className="mt-3 border-l-2 border-accent-200 pl-3"><p className="text-xs font-semibold">Related attention{entry.attention_total===null?' · total unknown':''}</p>
      <ul>{attention.map(item=><AttentionRow key={item.attention_id} level={5} item={item} stale={stale||preferencesStale} pending={pendingIds.includes(item.attention_id)} onOpen={onAttentionOpen} onSeen={onSeen} onSnooze={onSnooze}/>)}</ul>
      {(attentionPage?attentionPage.has_more:entry.has_more_attention)&&<button type="button" className="btn btn-secondary" disabled={stale||loading!==null} onClick={()=>onMore('attention')}>{loading==='attention'?'Loading attention…':'Load more related attention'}</button>}
    </div>}
    {(results.length>0||entry.results_total===null)&&<div className="mt-3 border-l-2 border-surface-200 pl-3"><p className="text-xs font-semibold">Related results{entry.result_tracking==='unknown'?' · viewing state partly untracked':''}{entry.results_total===null?' · total unknown':''}</p>
      <ul>{results.map(item=><ResultRow key={item.id} level={5} item={item} allowContinue={allowContinue&&entry.display_state!=='outcome_unknown'} stale={stale||preferencesStale||!!item.attention&&pendingIds.includes(item.attention.attention_id)} onOpen={onOpen} onContinue={onContinue} onSeen={onSeen}/>)}</ul>
      {(resultsPage?resultsPage.has_more:entry.has_more_results)&&<button type="button" className="btn btn-secondary" disabled={stale||loading!==null} onClick={()=>onMore('results')}>{loading==='results'?'Loading results…':'Load more related results'}</button>}
    </div>}
    {entry.external.map(item=><div key={JSON.stringify([item.source_id,item.observed_instance_id,item.generation])} className="mt-3 text-xs text-surface-500">
      <p>{item.source_kind} · generation {item.generation} · {item.last_report?.evidence||'Evidence unknown'} · {item.freshness}</p>
      <p>External report; native execution is not confirmed by this observation.</p>
      <button type="button" className="underline" onClick={()=>onOpen({kind:'external_observation',server_id:serverId,workspace_id:item.workspace_id,source_id:item.source_id,observed_instance_id:item.observed_instance_id,generation:item.generation})}>Inspect external source</button>
    </div>)}
  </li>;
}

import {useCallback, useEffect, useRef, useState} from 'react';
import {Pause, Play, Plus, RefreshCw} from 'lucide-react';
import {api, type WorkspaceListItem} from '../../api';
import type {AttentionAction, AttentionOccurrence} from '../../attentionTypes';
import type {HomeTarget, HomeEntryDisplayState, HomeQuickFilter} from '../../homeTypes';
import {homeEntryPageKey,type HomeInvalidation,type HomeStreamStatus} from '../../homeController';
import {useHomeOverview} from '../../hooks/useHomeOverview';
import {decodeHomeTarget, encodeHomeTarget} from '../../homeNavigation';
import {homeStateLabel} from '../../homePresentation';
import {AgentActionModal} from '../AgentActionModal';
import {PageContainer} from '../PageContainer';
import {useWorkspaceName} from '../WorkspaceNames';
import {HomeNewRequest, HomeInspection, HomeAttentionInspection} from './HomeInspection';
import {HomeEntryGroupCard,HomeEntryRow,homeFocus,homeEntriesAnnouncementIds,freshHomeEntryOccurrence,isQuietEntries} from './HomeCards';

type Panel = {kind: 'request'} | {kind: 'target'; target: HomeTarget; continuation?: boolean}
  | {kind: 'attention'; item: AttentionOccurrence; action: AttentionAction};
const states: HomeEntryDisplayState[] = ['running', 'awaiting_owner', 'claimed', 'queued', 'native_accepted', 'awaiting_operator', 'awaiting_agent', 'awaiting_dependency', 'awaiting_verification', 'outcome_unknown','configured','connected','idle','offline','stale'];
export function OperationalHome({workspace, workspaces, identityKey, refreshTick, latestEvent, streamStatus, onNavigate,
  onAttentionChanged, onSetupAgent, registerLeaveGuard}: {
  workspace: string; workspaces: WorkspaceListItem[]; identityKey: string; refreshTick: number;
  latestEvent: HomeInvalidation | null; streamStatus: HomeStreamStatus;
  onNavigate: (view: 'Agents' | 'Attention' | 'Graph' | 'Meta-harness') => void; onAttentionChanged: () => void; onSetupAgent: () => void;
  registerLeaveGuard: (guard: (() => boolean) | null) => void;
}) {
  const [agentFilter, setAgentFilter] = useState(''), [agentDraft, setAgentDraft] = useState(''), [stateFilter, setStateFilter] = useState('');
  const [harnessFilter,setHarnessFilter]=useState(''),[hostFilter,setHostFilter]=useState('');
  const [harnessDraft,setHarnessDraft]=useState(''),[hostDraft,setHostDraft]=useState('');
  const [quick,setQuick]=useState<HomeQuickFilter|undefined>(undefined);
  const [expanded,setExpanded]=useState<Record<string,boolean>>({}),[listFocused,setListFocused]=useState(false);
  const home = useHomeOverview({family:'entries',workspace: workspace === 'all' ? null : workspace, identityKey,
    agent_id: agentFilter || undefined,state:stateFilter||undefined,quick,harness:harnessFilter||undefined,host:hostFilter||undefined,
    holdOrder:listFocused||Object.values(expanded).some(Boolean),latestEvent,streamStatus});
  const {state,refresh,pause,apply,holdOrder,loadEntries,loadGroupChildren,loadEntrySessions,loadEntryAttention,loadEntryResults}=home;
  const snapshot = state.entries;
  const [panel, setPanel] = useState<Panel | null>(null), [manualPause, setManualPause] = useState(false);
  const [notice, setNotice] = useState(''), [pending, setPending] = useState<string[]>([]);
  const locks = useRef(new Set<string>()), mounted = useRef(true);
  const current = useRef(state);current.current = state;
  const heading = useRef<HTMLHeadingElement>(null), focusReturn = useRef<HTMLElement | null>(null);
  const focusEntry=useRef<string|null>(null);
  const scrollReturn = useRef<{element: HTMLElement; top: number} | null>(null);
  const workspaceName = useWorkspaceName(workspace === 'all' ? null : workspace);
  const initialTarget = useRef(false);
  const [announcement, setAnnouncement] = useState('');
  const announced = useRef<{generation: number; ids: Set<string>}>({generation:-1, ids:new Set()});
  const announceTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    if (announced.current.generation !== state.generation) {
      if (announceTimer.current !== null) {clearTimeout(announceTimer.current);announceTimer.current = null;}
      setAnnouncement('');
    }
    if (!snapshot) return;
    const ids = homeEntriesAnnouncementIds(state);
    const previous = announced.current;
    announced.current = {generation:state.generation,ids};
    if (previous.generation !== state.generation) {setAnnouncement('');return;}
    if ([...ids].some(id => !previous.ids.has(id)) && announceTimer.current === null) {
      // A separate mutation makes the next coalesced batch audible even when
      // its business summary is the same as the preceding batch.
      setAnnouncement('');
      announceTimer.current = setTimeout(() => {announceTimer.current=null;setAnnouncement('Home updated. New work, attention or results are available.');}, 2000);
    }
  }, [snapshot,state.entryChildren, state.generation]);
  useEffect(() => () => {if (announceTimer.current) clearTimeout(announceTimer.current);}, []);
  useEffect(()=>{setExpanded({});setListFocused(false);},[state.generation]);
  useEffect(() => {mounted.current = true;return () => {mounted.current = false;};}, []);
  useEffect(() => {if (refreshTick) refresh();}, [refreshTick, refresh]);
  useEffect(() => {pause(manualPause || !!panel);}, [manualPause, !!panel, pause]);
  const close = useCallback(() => {
    setPanel(null);
    const url = new URL(window.location.href);url.searchParams.delete('home_target');window.history.replaceState(null, '', url);
    window.requestAnimationFrame(() => {
      const scroll = scrollReturn.current;if (scroll?.element.isConnected) scroll.element.scrollTop = scroll.top;
      const moved=focusEntry.current?Array.from(document.querySelectorAll<HTMLElement>('[data-home-entry]')).find(el=>el.dataset.homeEntry===focusEntry.current):null;
      const destination=focusReturn.current?.isConnected?focusReturn.current:moved?.querySelector<HTMLElement>('[data-home-entry-open]')??moved??heading.current;
      destination?.focus({preventScroll:true});
    });
  }, []);
  const dismiss = useCallback(() => {
    const dialog = document.querySelector<HTMLDialogElement>('[data-testid="home-detail"]');
    dialog?.dispatchEvent(new Event('cancel', {cancelable:true}));
    return !dialog;
  }, []);
  useEffect(() => {
    registerLeaveGuard(panel ? dismiss : null);
    const beforeUnload = (event: BeforeUnloadEvent) => {event.preventDefault();event.returnValue = '';};
    if (panel) window.addEventListener('beforeunload', beforeUnload);
    return () => {registerLeaveGuard(null);window.removeEventListener('beforeunload', beforeUnload);};
  }, [panel, dismiss, registerLeaveGuard]);
  const open = (next: Panel) => {
    if (panel) {dismiss();return;}
    focusReturn.current = document.activeElement as HTMLElement | null;
    focusEntry.current=focusReturn.current?.closest<HTMLElement>('[data-home-entry]')?.dataset.homeEntry??null;
    const scroll = heading.current?.closest('main');if (scroll) scrollReturn.current = {element:scroll, top:scroll.scrollTop};
    if (next.kind === 'target') {
      const url = new URL(window.location.href);url.searchParams.set('home_target', encodeHomeTarget(next.target));window.history.pushState(null, '', url);
    }
    setPanel(next);
  };
  useEffect(() => {
    const pop = () => {
      if (panel) {dismiss();return;}
      const raw = new URL(window.location.href).searchParams.get('home_target');
      const target = raw && decodeHomeTarget(raw);if (target) setPanel({kind:'target', target});
    };
    window.addEventListener('popstate', pop);return () => window.removeEventListener('popstate', pop);
  }, [panel, dismiss]);
  useEffect(() => {
    if (initialTarget.current || !snapshot) return;initialTarget.current = true;
    const raw = new URL(window.location.href).searchParams.get('home_target');if (!raw) return;
    const target = decodeHomeTarget(raw);
    if (target) setPanel({kind:'target', target});else setNotice('The saved detail reference is invalid. No record was selected.');
  }, [snapshot]);
  useEffect(() => {if (state.status === 'forbidden' || state.status === 'disabled') {setPanel(null);setNotice('');locks.current.clear();setPending([]);}}, [state.status]);
  const changed = () => {refresh();onAttentionChanged();};
  const preference = async (item: AttentionOccurrence, seen?: boolean) => {
    const before = current.current, snap = before.entries;
    const canonical = freshHomeEntryOccurrence(before,item);
    if (!snap || !['ready', 'stale'].includes(before.status) || before.paused || !canonical || canonical.source_revision !== item.source_revision ||
        canonical.seen_state.revision !== item.seen_state.revision || locks.current.has(item.attention_id)) {setNotice('Refresh this occurrence before changing its viewing preference.');return;}
    locks.current.add(item.attention_id);setPending([...locks.current]);setNotice('');
    try {
      if (seen !== undefined) await api.attentionSeen(item.attention_id, {seen, source_revision:item.source_revision, preference_revision:item.seen_state.revision});
      else await api.attentionSnooze(item.attention_id, {until:item.seen_state.snoozed ? null : new Date(Date.now()+3600000).toISOString(), source_revision:item.source_revision, preference_revision:item.seen_state.revision});
    } catch {if (mounted.current && current.current.generation === before.generation) setNotice('The viewing preference could not be confirmed. Refreshing the canonical occurrence; it will not be replayed.');}
    finally {locks.current.delete(item.attention_id);if (mounted.current && current.current.generation === before.generation) {setPending([...locks.current]);changed();}}
  };
  const blocked=state.loading||!!state.entryLoading||state.paused||state.hasPendingUpdate||state.staleSections.length>0||!snapshot||
    !['ready','partial'].includes(snapshot.status)||['forbidden','disabled','error'].includes(state.status);
  const quiet=isQuietEntries(snapshot,blocked);
  const filtered=!!(quick||agentFilter||stateFilter||harnessFilter||hostFilter);
  const clearFilters=()=>{setQuick(undefined);setAgentFilter('');setAgentDraft('');setStateFilter('');setHarnessFilter('');setHarnessDraft('');setHostFilter('');setHostDraft('');};
  const passiveLabels:Record<string,string>={configured:'Configured',connected:'Connected',idle:'No work in progress',offline:'Offline',stale:'Information out of date'};
  return <PageContainer testId="operational-home" className="space-y-5">
    <header className="flex flex-wrap justify-between items-start gap-3">
      <div><h1 ref={heading} tabIndex={-1} className="text-2xl font-semibold">Home</h1>
        <p className="text-sm text-surface-500 mt-1">{workspace==='all'?'All workspaces':workspaceName} · Follow work, questions and deliveries</p></div>
      <div className="flex flex-wrap gap-2">
        <button type="button" className={`btn btn-primary ${homeFocus}`} onClick={()=>open({kind:'request'})} disabled={!snapshot||['forbidden','disabled'].includes(state.status)}><Plus size={15}/> New request</button>
        <button type="button" className={`btn btn-secondary ${homeFocus}`} onClick={onSetupAgent} disabled={state.status==='forbidden'}>Connect agent</button>
        <button type="button" className={`btn btn-secondary ${homeFocus}`} onClick={refresh} disabled={state.loading||!!state.entryLoading}><RefreshCw size={15}/> Refresh</button>
        <button type="button" className={`btn btn-secondary ${homeFocus}`} aria-pressed={manualPause} onClick={()=>setManualPause(value=>!value)}>{manualPause?<Play size={15}/>:<Pause size={15}/>} {manualPause?'Resume display':'Pause display'}</button>
      </div>
    </header>
    {state.paused&&<p role="status" className="text-sm text-surface-500">Display updates paused. Agents keep running; decisions require a fresh canonical review.</p>}
    {state.hasPendingUpdate&&<div role="status" className="flex flex-wrap gap-3 items-center text-sm"><span>Updates are available.</span><button type="button" className="btn btn-secondary" disabled={!!panel} onClick={()=>{setManualPause(false);apply();}}>Apply updates</button></div>}
    <p className="sr-only" role="status" aria-live="polite" aria-atomic="true">{announcement}</p>
    {notice&&<p role="alert" className="text-sm">{notice}</p>}
    {state.error&&<p role="alert" className="text-sm">{/^[A-Z0-9_]+$/.test(state.error)?'Tracking information could not be refreshed. Try Refresh or narrow the filters.':state.error}</p>}
    <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Follow-up filter">
      {([['active','Active'],['needs_you','Needs you'],['results','Results'],['all','All']] as const).map(([value,label])=><button type="button" key={value} className={`btn ${quick===value||quick===undefined&&value==='active'?'btn-primary':'btn-secondary'} ${homeFocus}`} aria-pressed={quick===value||quick===undefined&&value==='active'} disabled={!!panel} onClick={()=>setQuick(value)}>{label}</button>)}
      {filtered&&<button type="button" className="btn btn-secondary" disabled={!!panel} onClick={clearFilters}>Clear filters</button>}
    </div>
    {quick===undefined&&<p className="text-xs text-surface-500">Initial view includes recent results and tracked unseen deliveries.</p>}
    <details className="text-sm"><summary className={`cursor-pointer ${homeFocus}`}>Filter details</summary>
      <div className="mt-3 flex flex-wrap items-end gap-3" aria-label="Home filters">
        <label className="text-xs text-surface-500">Agent<input className="block mt-1 border rounded-lg p-2 bg-transparent text-sm" aria-label="Filter Home by agent" list="home-entry-agents" value={agentDraft} disabled={!!panel} onChange={event=>setAgentDraft(event.target.value)}/></label>
        <datalist id="home-entry-agents">{[...new Map((snapshot?.items??[]).filter(group=>group.agent_id).map(group=>[group.agent_id!,group.agent_label??group.agent_id!])).entries()].map(([id,label])=><option key={id} value={id}>{label}</option>)}</datalist>
        <label className="text-xs text-surface-500">Harness<input className="block mt-1 border rounded-lg p-2 bg-transparent text-sm" list="home-entry-harnesses" value={harnessDraft} disabled={!!panel} onChange={event=>setHarnessDraft(event.target.value)}/></label>
        <datalist id="home-entry-harnesses">{[...new Set((snapshot?.items??[]).flatMap(group=>group.children.map(entry=>entry.harness_label)).filter((value):value is string=>!!value))].map(id=><option key={id} value={id}>{id==='codex_app_server'?'Codex':id==='claude_stream'?'Claude':id==='pi_rpc'?'Pi':id}</option>)}</datalist>
        <label className="text-xs text-surface-500">Host<input className="block mt-1 border rounded-lg p-2 bg-transparent text-sm" list="home-entry-hosts" value={hostDraft} disabled={!!panel} onChange={event=>setHostDraft(event.target.value)}/></label>
        <datalist id="home-entry-hosts">{[...new Map((snapshot?.items??[]).filter(group=>group.executor_id).map(group=>[group.executor_id!,group.host_label??group.executor_id!])).entries()].map(([id,label])=><option key={id} value={id}>{label}</option>)}</datalist>
        <button type="button" className="btn btn-secondary" disabled={!!panel} onClick={()=>{setAgentFilter(agentDraft.trim());setHarnessFilter(harnessDraft.trim());setHostFilter(hostDraft.trim());}}>Apply details</button>
        <label className="text-xs text-surface-500">State<select className="block mt-1 border rounded-lg p-2 bg-transparent text-sm" value={stateFilter} disabled={!!panel} onChange={event=>setStateFilter(event.target.value)}><option value="">All states</option>{states.map(value=><option value={value} key={value}>{passiveLabels[value]??homeStateLabel(value)}</option>)}</select></label>
      </div>
    </details>
    {!snapshot&&<p role="status" className="panel p-5">{state.status==='forbidden'?'Operator access is required. Protected Home data has been cleared.':state.status==='disabled'?'Operational Home is disabled.':state.status==='error'?'Home information is unavailable. Refresh to try again.':'Loading follow-up…'}</p>}
    {snapshot&&<>
      {(snapshot.server_attention.total===null||snapshot.server_attention.total>0)&&<div role="status" className="rounded-lg border border-surface-200 dark:border-surface-700 p-3 text-sm">
        <button type="button" className={`underline ${homeFocus}`} onClick={()=>onNavigate('Attention')}>{snapshot.server_attention.total===null?'Server attention unavailable':`${snapshot.server_attention.total} Server attention ${snapshot.server_attention.total===1?'item':'items'}`}. Open Needs attention</button>
        <p className="text-xs text-surface-500 mt-1">All projects and Server. These incidents are separate from project work.</p>
      </div>}
      <section aria-labelledby="home-follow-up-title" data-testid="home-follow-up" className="space-y-3 min-w-0"
        onFocusCapture={()=>{holdOrder(true);setListFocused(true);}} onBlurCapture={event=>{if(!event.currentTarget.contains(event.relatedTarget as Node|null)){holdOrder(Object.values(expanded).some(Boolean));setListFocused(false);}}}>
        <div className="flex flex-wrap justify-between items-baseline gap-2"><h2 id="home-follow-up-title" className="text-lg font-semibold">Follow-up</h2>
          <span className="text-xs text-surface-500">{snapshot.total===null?'Context total unknown':`${snapshot.total} contexts`}{blocked?' · Revalidating or displaying a previous snapshot':''}</span></div>
        <p className="text-xs text-surface-500">{(['activities','sessions','occurrences','results'] as const).filter(key=>(snapshot.summary[key]?.value??0)>0).map(key=>`${snapshot.summary[key].value} ${snapshot.summary[key].unit}`).join(' · ')}</p>
        {snapshot.status!=='ready'&&<p role="status" className="text-sm text-surface-500">Some information is incomplete or unavailable. Totals may be unknown; refresh before acting.</p>}
        {snapshot.coverage.result_tracking!=='ready'&&<p className="text-xs text-surface-500">Some result viewing states are untracked. Those deliveries are labeled recent.</p>}
        {quiet&&<div className="panel p-5"><p className="font-medium">No matching activity{filtered?' for these filters':''}.</p><p className="text-sm text-surface-500 mt-2">Use New request to ask for work, or Connect agent to add a collaborator.</p></div>}
        {!snapshot.items.length&&!quiet&&<p role="status" className="panel p-5">Tracking information is incomplete. Refresh to load this scope.</p>}
        <ul className="space-y-3">{snapshot.items.map(group=><HomeEntryGroupCard key={group.id} group={group} page={state.entryChildren[group.id]}
          expanded={!!expanded[group.id]} onExpand={()=>{const next={...expanded,[group.id]:!expanded[group.id]};holdOrder(listFocused||Object.values(next).some(Boolean));setExpanded(next);}}
          stale={blocked} loading={state.entryLoading?.partition==='children'&&state.entryLoading.groupId===group.id} onMore={()=>loadGroupChildren(group.id)}>
          {entry=>{const key=homeEntryPageKey(group.id,entry.id),loading=state.entryLoading?.groupId===group.id&&state.entryLoading.entryId===entry.id?state.entryLoading.partition:null;
            return <HomeEntryRow key={entry.id} entry={entry} serverId={snapshot.server_id} sessionsPage={state.entrySessions[key]} attentionPage={state.entryAttention[key]} resultsPage={state.entryResults[key]}
              stale={blocked} preferencesStale={snapshot.source_status.attention!=='ready'} pendingIds={pending} loading={loading}
              onOpen={target=>open({kind:'target',target})} onContinue={target=>open({kind:'target',target,continuation:true})}
              onAttentionOpen={(item,action)=>open({kind:'attention',item,action})} onSeen={(item,seen)=>void preference(item,seen)} onSnooze={item=>void preference(item)}
              onMore={partition=>partition==='sessions'?loadEntrySessions(group.id,entry.id):partition==='attention'?loadEntryAttention(group.id,entry.id):loadEntryResults(group.id,entry.id)}/>;
          }}
        </HomeEntryGroupCard>)}</ul>
        {snapshot.has_more&&<button type="button" className={`btn btn-secondary ${homeFocus}`} disabled={blocked} onClick={loadEntries}>{state.entryLoading?.partition==='groups'?'Loading contexts…':'Load more contexts'}</button>}
      </section>
    </>}
    {panel&&snapshot&&<AgentActionModal title={panel.kind==='request'?'New request':panel.kind==='attention'?'Canonical attention record':panel.continuation?'Continue this exact session':'Activity detail'} onClose={close} presentation="drawer" wide testId="home-detail">
      {panel.kind==='request'?<HomeNewRequest workspace={workspace} workspaces={workspaces} onChanged={changed}/>
        :panel.kind==='attention'?<HomeAttentionInspection item={panel.item} action={panel.action} onClose={close} onChanged={changed}/>
          :<HomeInspection target={panel.target} serverId={snapshot.server_id} workspace={workspace==='all'?null:workspace} continuation={panel.continuation} onClose={close} onChanged={changed}/>}
    </AgentActionModal>}
  </PageContainer>;
}

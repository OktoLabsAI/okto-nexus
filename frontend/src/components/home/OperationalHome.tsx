import {useCallback, useEffect, useRef, useState} from 'react';
import {Pause, Play, Plus, RefreshCw} from 'lucide-react';
import {api, type WorkspaceListItem} from '../../api';
import type {AttentionAction, AttentionOccurrence} from '../../attentionTypes';
import type {HomeTarget, HomeDisplayState} from '../../homeTypes';
import type {HomeInvalidation, HomeStreamStatus} from '../../homeController';
import {useHomeOverview} from '../../hooks/useHomeOverview';
import {decodeHomeTarget, encodeHomeTarget} from '../../homeNavigation';
import {homeExternalLabel, homeStateLabel, homeFeedLabel} from '../../homePresentation';
import {AgentActionModal} from '../AgentActionModal';
import {PageContainer} from '../PageContainer';
import {useWorkspaceName} from '../WorkspaceNames';
import {HomeNewRequest, HomeInspection, HomeAttentionInspection} from './HomeInspection';
import {AgentRow, AttentionRow, HomeBlock, HomeCounters, HomeWelcome, isQuietHome, ResultRow, WorkRow, homeFocus} from './HomeCards';

type Panel = {kind: 'request'} | {kind: 'target'; target: HomeTarget; continuation?: boolean}
  | {kind: 'attention'; item: AttentionOccurrence; action: AttentionAction};
const states: HomeDisplayState[] = ['running', 'awaiting_owner', 'claimed', 'queued', 'native_accepted', 'awaiting_operator', 'awaiting_agent', 'awaiting_dependency', 'awaiting_verification', 'outcome_unknown'];
export function OperationalHome({workspace, workspaces, identityKey, refreshTick, latestEvent, streamStatus, onNavigate,
  onAttentionChanged, onSetupAgent, registerLeaveGuard}: {
  workspace: string; workspaces: WorkspaceListItem[]; identityKey: string; refreshTick: number;
  latestEvent: HomeInvalidation | null; streamStatus: HomeStreamStatus;
  onNavigate: (view: 'Agents' | 'Attention' | 'Graph' | 'Meta-harness') => void; onAttentionChanged: () => void; onSetupAgent: () => void;
  registerLeaveGuard: (guard: (() => boolean) | null) => void;
}) {
  const [agentFilter, setAgentFilter] = useState(''), [agentDraft, setAgentDraft] = useState(''), [stateFilter, setStateFilter] = useState('');
  const home = useHomeOverview({workspace: workspace === 'all' ? null : workspace, identityKey,
    agent_id: agentFilter || undefined, state: stateFilter || undefined, latestEvent, streamStatus});
  const {state, refresh, pause, apply, loadMore} = home;
  const snapshot = state.snapshot;
  const [panel, setPanel] = useState<Panel | null>(null), [manualPause, setManualPause] = useState(false);
  const [notice, setNotice] = useState(''), [pending, setPending] = useState<string[]>([]);
  const locks = useRef(new Set<string>()), mounted = useRef(true);
  const current = useRef(state);current.current = state;
  const heading = useRef<HTMLHeadingElement>(null), focusReturn = useRef<HTMLElement | null>(null);
  const scrollReturn = useRef<{element: HTMLElement; top: number} | null>(null);
  const workspaceName = useWorkspaceName(workspace === 'all' ? null : workspace);
  const initialTarget = useRef(false);
  const activityRequested = useRef(-1);
  const [announcement, setAnnouncement] = useState('');
  const announced = useRef<{generation: number; ids: Set<string>}>({generation:-1, ids:new Set()});
  const announceTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    if (announced.current.generation !== state.generation) {
      if (announceTimer.current !== null) {clearTimeout(announceTimer.current);announceTimer.current = null;}
      setAnnouncement('');
    }
    if (!snapshot) return;
    const ids = new Set([...snapshot.work.items.map(item => item.id), ...snapshot.results.items.map(item => item.id), ...snapshot.attention.items.map(item => item.attention_id)]);
    const previous = announced.current;
    announced.current = {generation:state.generation,ids};
    if (previous.generation !== state.generation) {setAnnouncement('');return;}
    if ([...ids].some(id => !previous.ids.has(id)) && announceTimer.current === null) {
      // A separate mutation makes the next coalesced batch audible even when
      // its business summary is the same as the preceding batch.
      setAnnouncement('');
      announceTimer.current = setTimeout(() => {announceTimer.current=null;setAnnouncement('Home updated. New work, attention or results are available.');}, 2000);
    }
  }, [snapshot, state.generation]);
  useEffect(() => () => {if (announceTimer.current) clearTimeout(announceTimer.current);}, []);
  useEffect(() => {
    if (snapshot && !state.activity && !state.loading && !state.loadingMore && state.status === 'ready' && !state.paused && activityRequested.current !== state.generation) {
      activityRequested.current = state.generation;loadMore('activity');
    }
  }, [snapshot, state.activity, state.loading, state.loadingMore, state.status, state.paused, state.generation, loadMore]);
  useEffect(() => {mounted.current = true;return () => {mounted.current = false;};}, []);
  useEffect(() => {if (refreshTick) refresh();}, [refreshTick, refresh]);
  useEffect(() => {pause(manualPause || !!panel);}, [manualPause, !!panel, pause]);
  const close = useCallback(() => {
    setPanel(null);
    const url = new URL(window.location.href);url.searchParams.delete('home_target');window.history.replaceState(null, '', url);
    window.requestAnimationFrame(() => {
      const scroll = scrollReturn.current;if (scroll?.element.isConnected) scroll.element.scrollTop = scroll.top;
      (focusReturn.current?.isConnected ? focusReturn.current : heading.current)?.focus({preventScroll:true});
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
  useEffect(() => {if (state.status === 'forbidden' || state.status === 'disabled') {setPanel(null);setNotice('');}}, [state.status]);
  const changed = () => {refresh();onAttentionChanged();};
  const preference = async (item: AttentionOccurrence, seen?: boolean) => {
    const before = current.current, snap = before.snapshot;
    const fresh = (section: 'attention'|'results') => snap?.[section].status === 'ready' && !before.staleSections.includes(section);
    const rows = [...(fresh('attention') ? snap!.attention.items : []), ...(fresh('results') ? snap!.results.items.flatMap(result => result.attention ? [result.attention] : []) : [])];
    const canonical = rows.find(row => row.attention_id === item.attention_id);
    if (!snap || !['ready', 'stale'].includes(before.status) || before.paused || !canonical || canonical.source_revision !== item.source_revision ||
        canonical.seen_state.revision !== item.seen_state.revision || locks.current.has(item.attention_id)) {setNotice('Refresh this occurrence before changing its viewing preference.');return;}
    locks.current.add(item.attention_id);setPending([...locks.current]);setNotice('');
    try {
      if (seen !== undefined) await api.attentionSeen(item.attention_id, {seen, source_revision:item.source_revision, preference_revision:item.seen_state.revision});
      else await api.attentionSnooze(item.attention_id, {until:item.seen_state.snoozed ? null : new Date(Date.now()+3600000).toISOString(), source_revision:item.source_revision, preference_revision:item.seen_state.revision});
    } catch {if (mounted.current && current.current.generation === before.generation) setNotice('The viewing preference could not be confirmed. Refreshing the canonical occurrence; it will not be replayed.');}
    finally {locks.current.delete(item.attention_id);if (mounted.current && current.current.generation === before.generation) {setPending([...locks.current]);changed();}}
  };
  const isStale = (section: 'work'|'attention'|'results'|'agents'|'external_activity') => !['ready', 'stale'].includes(state.status) || state.staleSections.includes(section) || state.paused;
  const quiet = !agentFilter && !stateFilter && isQuietHome(snapshot, state.status !== 'ready' || state.staleSections.some(section => ['work','results','attention','agents','external_activity'].includes(section)));
  const agentsBlock = snapshot && <HomeBlock title="Agents" section={snapshot.agents} stale={isStale('agents')} onMore={() => loadMore('agents')} loadingMore={state.loadingMore === 'agents'} empty="No visible agents in this scope."><ul className="divide-y divide-surface-200 dark:divide-surface-700">{snapshot.agents.items.map(item => <AgentRow key={item.agent_id} item={item}/>)}</ul></HomeBlock>;
  return <PageContainer testId="operational-home" className="space-y-5">
    <header className="flex flex-wrap justify-between items-start gap-3">
      <div><p className="text-xs uppercase tracking-wider text-accent-600 dark:text-accent-300">Operational overview</p>
        <h1 ref={heading} tabIndex={-1} className="text-2xl font-semibold mt-1">Home</h1>
        <p className="text-sm text-surface-500 mt-1">{workspace === 'all' ? 'All workspaces' : workspaceName} · Work, decisions and results</p></div>
      <div className="flex flex-wrap gap-2">
        {!quiet && <button className={`btn btn-primary ${homeFocus}`} onClick={() => open({kind:'request'})} disabled={!snapshot || state.status === 'forbidden'}><Plus size={15}/> New request</button>}
        <button className={`btn btn-secondary ${homeFocus}`} onClick={refresh} disabled={state.loading}><RefreshCw size={15}/> Refresh</button>
        <button className={`btn btn-secondary ${homeFocus}`} aria-pressed={manualPause} onClick={() => setManualPause(value => !value)}>{manualPause ? <Play size={15}/> : <Pause size={15}/>} {manualPause ? 'Resume display' : 'Pause display'}</button>
      </div>
    </header>
    {state.paused && <p role="status" className="text-sm text-surface-500">Display updates paused. Agents keep running; decisions still require a fresh canonical review.</p>}
    {state.hasPendingUpdate && <div role="status" className="flex flex-wrap gap-3 items-center text-sm"><span>Updates are available.</span><button className="btn btn-secondary" disabled={!!panel} onClick={() => {setManualPause(false);apply();}}>Apply updates</button></div>}
    <p className="sr-only" role="status" aria-live="polite" aria-atomic="true">{announcement}</p>
    {notice && <p role="alert" className="text-sm">{notice}</p>}
    {state.error && <p role="alert" className="text-sm">{state.error}</p>}
      <div className="flex flex-wrap gap-3 items-end" aria-label="Home filters">
        <label className="text-xs text-surface-500">Agent<input className="block mt-1 border rounded-lg p-2 bg-transparent text-sm" aria-label="Filter Home by agent" list="home-agents" value={agentDraft} onChange={event => setAgentDraft(event.target.value)} onKeyDown={event => {if (event.key === 'Enter') setAgentFilter(agentDraft.trim());}}/></label>
        <datalist id="home-agents">{(snapshot?.agents.items ?? []).map(agent => <option key={agent.agent_id} value={agent.agent_id}>{agent.name}</option>)}</datalist>
        <button className="btn btn-secondary" onClick={() => setAgentFilter(agentDraft.trim())}>Apply agent filter</button>
        <label className="text-xs text-surface-500">Work state<select className="block mt-1 border rounded-lg p-2 bg-transparent text-sm" value={stateFilter} onChange={event => setStateFilter(event.target.value)}><option value="">All states</option>{states.map(value => <option value={value} key={value}>{homeStateLabel(value)}</option>)}</select></label>
        {(agentFilter || agentDraft || stateFilter) && <button className="btn btn-secondary" onClick={() => {setAgentFilter('');setAgentDraft('');setStateFilter('');}}>Clear filters</button>}
      </div>
    {!snapshot && <p role="status" className="panel p-5">{state.status === 'forbidden' ? 'Operator access is required. Protected Home data has been cleared.' : state.status === 'disabled' ? 'Operational Home is disabled.' : state.status === 'error' ? 'Home information is unavailable. Refresh to try again.' : 'Loading operational overview…'}</p>}
    {snapshot && <>
      {quiet ? <>
        <HomeWelcome needsSetup={snapshot.agents.total === 0} externalDisabled={snapshot.external_activity.status === 'disabled'} onSetup={onSetupAgent} onRequest={() => open({kind:'request'})}/>
        {snapshot.agents.total !== 0 && agentsBlock}
      </> : <>
      <HomeCounters summary={snapshot.summary}/>

      <div className="grid xl:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)] gap-5 items-start">
        <div className="space-y-5 min-w-0">
          <HomeBlock title="Needs you" section={snapshot.attention} stale={isStale('attention')} onMore={() => loadMore('attention')} loadingMore={state.loadingMore === 'attention'} empty="No matching attention occurrences. Work may still be running or waiting elsewhere.">
            <ul className="divide-y divide-surface-200 dark:divide-surface-700">{snapshot.attention.items.map(item => <AttentionRow key={item.attention_id} item={item} pending={pending.includes(item.attention_id)} stale={isStale('attention')} onOpen={(item,action) => open({kind:'attention',item,action})} onSeen={(item,seen) => void preference(item,seen)} onSnooze={item => void preference(item)}/>)}</ul>
          </HomeBlock>
          <HomeBlock title="Work" section={snapshot.work} stale={isStale('work')} empty={snapshot.agents.total === 0 ? <><p>No agents are visible in this scope.</p><button className="btn btn-secondary mt-3" onClick={onSetupAgent}>Set up an agent</button></> : 'No matching work. Start a tracked handoff or a conversation with New request.'} onMore={() => loadMore('work')} loadingMore={state.loadingMore === 'work'}>
            <ul className="divide-y divide-surface-200 dark:divide-surface-700">{snapshot.work.items.map(item => <WorkRow key={item.id} item={item} onOpen={target => open({kind:'target',target})}/>)}</ul>
          </HomeBlock>
        </div>
        <div className="space-y-5 min-w-0">
          <HomeBlock title="Results" section={snapshot.results} stale={isStale('results')} empty="No matching results in this snapshot." onMore={() => loadMore('results')} loadingMore={state.loadingMore === 'results'}>
            <ul className="divide-y divide-surface-200 dark:divide-surface-700">{snapshot.results.items.map(item => <ResultRow key={item.id} item={item} stale={isStale('results') || !!item.attention && pending.includes(item.attention.attention_id)} onOpen={target => open({kind:'target',target})} onSeen={(item,seen) => void preference(item,seen)} onContinue={target => open({kind:'target',target,continuation:true})}/>)}</ul>
          </HomeBlock>
          {agentsBlock}
        </div>
      </div>
      <HomeBlock title="External reports" section={snapshot.external_activity} stale={isStale('external_activity')} onMore={() => loadMore('external')} loadingMore={state.loadingMore === 'external'} empty="No external activity reported. Native work above is independent of external telemetry.">
        <p className="text-xs text-surface-500 mt-3">External reports do not confirm native execution, capacity or successful completion.</p>
        <ul className="divide-y divide-surface-200 dark:divide-surface-700">{snapshot.external_activity.items.map(item => <li key={JSON.stringify([item.source_id,item.observed_instance_id,item.generation])} className="py-3 text-sm">
          <strong>{item.agent_id}</strong><p>{homeExternalLabel(item)}</p><p className="text-xs text-surface-500">{item.source_kind} · generation {item.generation} · {item.last_report?.evidence || 'No activity evidence'}</p>
          <button className="btn btn-secondary mt-2" onClick={() => open({kind:'target',target:{kind:'external_observation',server_id:snapshot.server_id,workspace_id:item.workspace_id,source_id:item.source_id,observed_instance_id:item.observed_instance_id,generation:item.generation}})}>Inspect source</button>
        </li>)}</ul>
      </HomeBlock>
      </>}
      {(!quiet || state.activity && (state.activity.items.length > 0 || state.activity.status !== 'ready')) && (state.activity ? <HomeBlock title="Recent activity" section={state.activity} stale={state.staleSections.includes('activity')} empty="No recent business events in this scope." onMore={() => loadMore('activity')} loadingMore={state.loadingMore === 'activity'}>
        <ul className="divide-y divide-surface-200 dark:divide-surface-700">{state.activity.items.map(event => {
          const label = homeFeedLabel(event.kind);if (!label) return null;
          return <li key={event.id} className="py-2 text-sm flex flex-wrap justify-between gap-2"><span>{label}{event.agent_id ? ` · ${event.agent_id}` : ''}</span>
            {event.detail_target && <button type="button" className={`text-xs underline ${homeFocus}`} onClick={() => open({kind:'target',target:event.detail_target!})}>Inspect event source</button>}</li>;
        })}</ul>
      </HomeBlock> : <section className="panel p-4"><h2 className="font-semibold">Recent activity</h2><button className="btn btn-secondary mt-3" disabled={!!state.loadingMore || state.loading} onClick={() => loadMore('activity')}>Load recent activity</button></section>)}
    </>}
    {panel && snapshot && <AgentActionModal title={panel.kind === 'request' ? 'New request' : panel.kind === 'attention' ? 'Canonical attention record' : panel.continuation ? 'Continue this exact session' : 'Activity detail'} onClose={close} presentation="drawer" wide testId="home-detail">
      {panel.kind === 'request' ? <HomeNewRequest workspace={workspace} workspaces={workspaces} onChanged={changed}/>
        : panel.kind === 'attention' ? <HomeAttentionInspection item={panel.item} action={panel.action} onClose={close} onChanged={changed}/>
          : <HomeInspection target={panel.target} serverId={snapshot.server_id} workspace={workspace === 'all' ? null : workspace} continuation={panel.continuation} onClose={close} onChanged={changed}/>}
    </AgentActionModal>}
  </PageContainer>;
}

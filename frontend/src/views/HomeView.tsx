import { useEffect, type ReactNode } from 'react';
import { ArrowUpRight, Bell, Bot, MessagesSquare, RefreshCw, Users, Waypoints } from 'lucide-react';
import { api, type GraphSnapshot, type MessageRow, type MetaHarnessSessions } from '../api';
import type { AttentionState } from '../attentionTypes';
import type { ObservationReadState } from '../observationReader';
import type { ObservationSummary } from '../observationTypes';
import { useObservationRead } from '../hooks/useObservationRead';
import { observationCountText, observationRefreshSeconds } from '../observationPresentation';
import { PageContainer } from '../components/PageContainer';
import { formatTime } from '../timeFormat';
import { actionLabel } from '../graph/lastAction';
import { getNavigationEntry } from '../navigationRegistry';
import { useWorkspaceName } from '../components/WorkspaceNames';

type Destination = 'Graph' | 'Meta-harness' | 'Messages' | 'Agents' | 'Attention';
type Messages = { items: MessageRow[]; total: number };
type Read<T> = ObservationReadState<T>;
const interval = () => 15;
const focus = 'focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent-500';

/** Bounded canonical reads, no per-agent requests and no seen/decision writes. */
export function HomeView({workspace, refreshTick, attention, onRefreshAttention, onNavigate}: {
  workspace: string; refreshTick: number; attention: AttentionState; onRefreshAttention: () => void; onNavigate: (view: Destination) => void;
}) {
  const projectName=useWorkspaceName(workspace);
  const graph = useObservationRead(workspace, (scope, signal) => api.graph(scope, 24, signal), interval);
  const sessions = useObservationRead(workspace, (scope, signal) => api.metaHarnessSessions(scope, '', 1, signal), interval);
  const messages = useObservationRead(workspace, (scope, signal) => api.messages({
    page: '1', page_size: '6', ...(scope === 'all' ? {} : {workspace: scope}),
  }, signal), interval);
  const observations = useObservationRead(workspace, (scope, signal) => api.externalObservationSummary(
    scope === 'all' ? {} : {workspace_id: scope}, signal), observationRefreshSeconds);
  const refresh = () => { graph.refresh(); sessions.refresh(); messages.refresh(); observations.refresh(); onRefreshAttention(); };
  useEffect(() => { if (refreshTick > 0) refresh(); }, [refreshTick]);
  return <HomeOverview workspace={workspace} graph={graph.state} sessions={sessions.state}
    messages={messages.state} observations={observations.state} attention={attention}
    onNavigate={onNavigate} onRefresh={refresh} projectName={projectName} />;
}

function ReadNotice({state}: {state: Read<unknown>}) {
  if (state.status === 'ready') return null;
  const text = state.status === 'loading' ? 'Loading…'
    : state.status === 'forbidden' ? 'Operator access is required to view this information.'
    : state.status === 'unavailable' ? 'Unavailable on this Server.'
    : state.value ? 'Out of date — showing the last update.'
    : 'Could not load this information. Refresh to try again.';
  return <p role={state.status === 'loading' ? 'status' : 'alert'} className="text-sm text-surface-500 mt-3">{text}</p>;
}

function Section({title, detail, children, destination, onNavigate}: {
  title: string; detail: string; children: ReactNode; destination: Destination; onNavigate: (view: Destination) => void;
}) {
  return <section className="panel p-5 min-w-0">
    <div className="flex justify-between items-start gap-3">
      <div><h2 className="font-semibold text-base">{title}</h2><p className="text-xs text-surface-500 mt-1">{detail}</p></div>
      <button className={`btn btn-secondary shrink-0 ${focus}`} onClick={() => onNavigate(destination)} aria-label={`Open ${getNavigationEntry(destination).label}`}><ArrowUpRight size={16}/></button>
    </div>{children}
  </section>;
}

export function HomeOverview({workspace, graph, sessions, messages, observations, attention, onNavigate, onRefresh, projectName}: {
  workspace: string; graph: Read<GraphSnapshot>; sessions: Read<MetaHarnessSessions>; messages: Read<Messages>;
  observations: Read<ObservationSummary>; attention: AttentionState;
  onNavigate: (view: Destination) => void; onRefresh: () => void;
  projectName?: string;
}) {
  const nodes = graph.value?.nodes;
  const summary = ['disabled', 'forbidden'].includes(attention.status) ||
    (attention.summary?.filters.workspace_id ?? 'all') !== workspace ? null : attention.summary;
  const present = nodes?.filter(node => node.presence === 'present').length;
  const links = [
    {name: 'Graph', detail: 'Connections and handoffs', icon: Waypoints},
    {name: 'Meta-harness', detail: 'Conversations and sessions', icon: Bot},
    {name: 'Messages', detail: 'Communication history', icon: MessagesSquare},
    {name: 'Attention', detail: 'Review pending items', icon: Bell},
  ] as const;
  return <PageContainer testId="home-overview" className="space-y-6">
    <header className="flex flex-wrap items-start justify-between gap-4">
      <div><p className="text-xs uppercase tracking-wider text-accent-600 dark:text-accent-300">Project overview</p>
        <h1 className="text-2xl font-semibold mt-1">Home</h1>
        <p className="text-sm text-surface-500 mt-2">Choose a project above. Use Connect or resume to find an existing connection or add a collaborator.</p>
        <p className="text-xs text-surface-500 mt-1">{workspace === 'all' ? 'All projects' : `Project: ${projectName || 'Selected project'}`} · Updates every 15 seconds</p>
        <p className="text-sm text-surface-500 mt-2">Follow your agents, conversations and pending questions here.</p>
      </div>
      <button onClick={onRefresh} className={`btn btn-secondary ${focus}`}><RefreshCw size={15}/> Refresh overview</button>
    </header>
    <nav aria-label="Overview shortcuts" className="grid grid-cols-2 xl:grid-cols-4 gap-3">
      {links.map(({name, detail, icon: Icon}) => <button key={name} onClick={() => onNavigate(name)} className={`panel p-4 text-left hover:border-accent-400 transition-colors ${focus}`}>
        <Icon size={19} className="text-accent-600 dark:text-accent-300 mb-3"/><span className="block font-semibold">{getNavigationEntry(name).label}</span><span className="block text-xs text-surface-500 mt-1">{detail}</span>
      </button>)}
    </nav>
    <div className="grid lg:grid-cols-2 gap-5">
      <Section title="Agents & activity" detail="Connected agents and recent activity" destination="Agents" onNavigate={onNavigate}>
        <ReadNotice state={graph}/>
        {nodes && <>
          <p className="mt-4 text-sm"><Users size={16} className="inline mr-2"/>{nodes.length} agents · {present} connected {graph.status !== 'ready' && '(last update)'}</p>
          <p className="text-xs text-surface-500 mt-1">Last {graph.value!.window_hours} hours · Updated {formatTime(graph.value!.generated_at)}</p>
          {nodes.length === 0 && <p className="text-sm text-surface-500 py-5">No agents in this scope yet. Open the connection guide from the header menu, or open Advanced → Agents and execution → Agent administration.</p>}
          <ul className="mt-3 divide-y divide-surface-200 dark:divide-surface-700">{nodes.slice(0, 8).map(node => <li key={node.agent_id} className="py-3 text-sm">
            <div className="flex justify-between gap-2"><strong className="break-all">{node.agent_id}</strong><span className="text-xs shrink-0 text-surface-500">{node.presence === 'present' ? 'Connected' : node.presence === 'stale' ? 'Presence out of date' : node.presence === 'offline' ? 'Offline' : 'Presence unknown'}</span></div>
            <p className="text-xs mt-1 text-surface-500">{node.sessions} connections · {node.pending_inbox} messages pending · {node.open_handoffs} open handoffs</p>
            <p className="text-xs mt-1">{node.last_action ? `${actionLabel(node.last_action.type)} · ${formatTime(node.last_action.at)}` : 'No recent activity'}</p>
          </li>)}</ul>
          {nodes.length > 8 && <p className="text-xs text-surface-500 mt-2">Showing 8 of {nodes.length}. Open Advanced → Agents and execution → Agent administration for the full list.</p>}
        </>}
      </Section>
      <Section title="Harness sessions" detail="Your managed conversations" destination="Meta-harness" onNavigate={onNavigate}>
        <ReadNotice state={sessions}/>
        {sessions.value && <>
          <p className="mt-4 text-sm" title="Open describes the session, not whether work is running.">{sessions.value.active_count} open · {sessions.value.total} total {sessions.status !== 'ready' && '(last update)'}</p>
          {sessions.value.items.length === 0 && <p className="py-5 text-sm text-surface-500">No managed conversations yet. Open Conversations to find your agents.</p>}
          <ul className="mt-3 divide-y divide-surface-200 dark:divide-surface-700">{sessions.value.items.slice(0, 6).map(session => <li key={`${session.scope.executor_id}:${session.scope.session_id}`} className="py-3 text-sm">
            <div className="flex justify-between gap-2"><strong className="break-all">{session.scope.agent_id}</strong><span className="text-xs shrink-0" title={`Session: ${session.lifecycle_state}; process: ${session.process_state}; lease: ${session.lease_state}`}>{session.is_open ? 'Open' : 'Ended'}</span></div>
            <p className="mt-1">{session.harness === 'claude_stream' ? 'Claude' : session.harness === 'codex_app_server' ? 'Codex' : session.harness === 'pi_rpc' ? 'Pi' : session.harness} · {session.location === 'embedded' || session.location === 'local' ? 'Local' : session.location === 'remote' ? 'Remote' : 'Location unknown'} · {session.host || 'Host unknown'}</p>
            {workspace === 'all' && <p className="text-xs text-surface-500 mt-1 break-all">{session.scope.workspace_id}</p>}
            <p className="text-xs text-surface-500 mt-1">Last interaction {formatTime(session.last_interaction_at)}</p>
          </li>)}</ul>
          {(sessions.value.has_more || sessions.value.items.length > 6) && <p className="text-xs text-surface-500 mt-2">Showing {Math.min(6, sessions.value.items.length)} of {sessions.value.total}. Open Conversations for more.</p>}
        </>}
      </Section>
      <Section title="Recent communications" detail="Latest messages between agents and people" destination="Messages" onNavigate={onNavigate}>
        <ReadNotice state={messages}/>
        {messages.value?.items.length === 0 && <p className="py-5 text-sm text-surface-500">No messages in this scope yet.</p>}
        <ul className="mt-3 divide-y divide-surface-200 dark:divide-surface-700">{messages.value?.items.map(message => <li key={message.message_id} className="py-3">
          <p className="text-sm break-words"><strong>{message.from_agent_id}</strong> → {message.deliveries.length ? message.deliveries.map(item => item.recipient_agent_id).join(', ') : 'No delivery recorded'}</p>
          <p className="text-sm mt-1 truncate">{message.subject || message.preview || 'Message'}</p>
          <p className="text-xs text-surface-500 mt-1">{formatTime(message.created_at)} · {message.workspace_id}</p>
        </li>)}</ul>
      </Section>
      <Section title="Needs attention" detail="Decisions, questions and results to review" destination="Attention" onNavigate={onNavigate}>
        {summary ? <div className="mt-4">
          <p className="text-xl font-semibold">{summary.counts.action_required} need action <span className="font-normal text-sm text-surface-500">· {summary.counts.watch} to watch</span></p>
          <p className="text-xs text-surface-500 mt-2">{summary.counts.unseen} unseen · {summary.counts.snoozed} snoozed · Updated {formatTime(summary.observed_at)}</p>
          {attention.status !== 'ready' && <p role="status" className="text-sm mt-3">Out of date — showing the last summary.</p>}
          {summary.total === 0 && attention.status === 'ready' && <p className="text-sm text-surface-500 mt-3">No active attention items in this scope.</p>}
        </div> : <p className="text-sm text-surface-500 mt-4" role="status">{attention.status === 'disabled' ? 'Attention is disabled on this Server.' : attention.status === 'forbidden' ? 'Operator access is required.' : attention.status === 'loading' ? 'Loading attention summary…' : 'Attention summary unavailable. Open Needs attention to inspect.'}</p>}
        <div className="border-t border-surface-200 dark:border-surface-700 mt-5 pt-4">
          <h3 className="text-sm font-semibold">External activity reports</h3>
          <ReadNotice state={observations}/>
          {observations.value && <><p className="text-sm mt-2">{observationCountText(observations.value, observations.status === 'ready')}</p>
            <p className="text-xs text-surface-500 mt-1">Observed {formatTime(observations.value.observed_at)}{!observations.value.feature_enabled && ' · Publishing disabled'}</p></>}
          <p className="text-xs text-surface-500 mt-2">Reported by Herdr or other integrations; separate from managed sessions.</p>
          <button onClick={() => onNavigate('Agents')} className={`text-sm text-accent-700 dark:text-accent-300 underline mt-2 ${focus}`}>Inspect external activity</button>
        </div>
      </Section>
    </div>
  </PageContainer>;
}

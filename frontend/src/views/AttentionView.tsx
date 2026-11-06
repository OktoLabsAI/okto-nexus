import { useLayoutEffect, useRef, useState } from 'react';
import { ArrowUpRight, Bell, Check, Clock3, Eye, RefreshCw } from 'lucide-react';
import type { AttentionAction, AttentionCategory, AttentionFilters, AttentionKind, AttentionOccurrence, AttentionPriority, AttentionState } from '../attentionTypes';
import { attentionActionLabels, attentionAge, attentionDescription, attentionKinds, attentionSnoozeUntil, attentionSourceLabel, changeAttentionFilter, nextAttentionFocus, primaryAttentionAction, visibleAttentionPage } from '../attentionPresentation';
import { PageContainer } from '../components/PageContainer';
import { useWorkspaceName } from '../components/WorkspaceNames';

const inputClass = 'w-full rounded-lg border border-surface-200 dark:border-surface-700 bg-white dark:bg-surface-900 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-accent-500';
const focusClass = 'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-500 focus-visible:ring-offset-2 dark:focus-visible:ring-offset-surface-900';

export interface AttentionViewProps {
  state: AttentionState;
  filters: AttentionFilters;
  onFiltersChange: (filters: AttentionFilters) => void;
  onRefresh: () => void;
  onLoadMore: () => void;
  onSeen: (item: AttentionOccurrence, seen: boolean) => Promise<void>;
  onSnooze: (item: AttentionOccurrence, until: string | null) => Promise<void>;
  onOpen: (item: AttentionOccurrence, action: AttentionAction) => void;
}

function fullTime(value: string): string {
  const parsed = new Date(value);
  return Number.isFinite(parsed.getTime()) ? parsed.toLocaleString() : 'Unknown time';
}

function AttentionCard({ item, pending, editable, onSeen, onSnooze, onOpen }: {
  item: AttentionOccurrence; pending: boolean; editable: boolean;
} & Pick<AttentionViewProps, 'onSeen' | 'onSnooze' | 'onOpen'>) {
  const [duration, setDuration] = useState(60);
  const workspaceName = useWorkspaceName(item.workspace_id);
  const description = attentionDescription(item);
  const action = primaryAttentionAction(item);
  const titleId = `${item.attention_id}-title`;
  const controlsDisabled = pending || !editable;
  const freshness = { current: 'Current source', stale: 'Source has changed', unavailable: 'Source unavailable' }[item.freshness];
  return <article aria-labelledby={titleId} aria-busy={pending} className="rounded-xl border border-surface-200 dark:border-surface-700 bg-white dark:bg-surface-900 p-4 sm:p-5">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2 text-xs text-surface-500 dark:text-surface-400 mb-2">
          <span>{item.priority === 30 ? 'High priority' : item.priority === 20 ? 'Medium priority' : 'Standard priority'}</span>
          <span aria-hidden="true">·</span><span>{freshness}</span>
          {item.resolution !== 'open' && <span className="rounded border border-surface-200 dark:border-surface-700 px-2 py-0.5">{item.resolution === 'expired' ? 'Expired' : 'Resolved at source'}</span>}
          {item.seen_state.seen && <span className="inline-flex items-center gap-1"><Check size={13} aria-hidden="true" />Seen</span>}
          {item.seen_state.snoozed && <span className="inline-flex items-center gap-1"><Clock3 size={13} aria-hidden="true" />Snoozed</span>}
        </div>
        <h3 id={titleId} className="font-semibold text-surface-900 dark:text-surface-100">{description.title}</h3>
        <p className="mt-1 text-sm text-surface-600 dark:text-surface-300">{description.reason}</p>
      </div>
      <time dateTime={item.first_detected_at} title={`First detected: ${fullTime(item.first_detected_at)}`} className="shrink-0 text-xs text-surface-500 dark:text-surface-400">{attentionAge(item.first_detected_at)}</time>
    </div>
    <dl className="grid sm:grid-cols-2 gap-x-6 gap-y-2 mt-4 text-xs">
      <div><dt className="text-surface-500 dark:text-surface-400">Agent</dt><dd className="font-mono break-all mt-0.5">{item.agent_id ?? 'Server-wide'}</dd></div>
      <div><dt className="text-surface-500 dark:text-surface-400">Workspace</dt><dd className="break-all mt-0.5">{item.workspace_id ? <>{workspaceName}<span className="block font-mono text-surface-500 dark:text-surface-400">{item.workspace_id}</span></> : 'Server-wide'}</dd></div>
      <div><dt className="text-surface-500 dark:text-surface-400">{attentionSourceLabel(item.source_type)}</dt><dd className="font-mono break-all mt-0.5" data-testid="attention-source-reference">{item.source_id}</dd></div>
      {item.session_id && <div><dt className="text-surface-500 dark:text-surface-400">Session</dt><dd className="font-mono break-all mt-0.5">{item.session_id}</dd></div>}
      {item.operation_id && item.operation_id !== item.source_id && <div><dt className="text-surface-500 dark:text-surface-400">Operation</dt><dd className="font-mono break-all mt-0.5">{item.operation_id}</dd></div>}
      {item.executor_id && item.executor_id !== item.source_id && <div><dt className="text-surface-500 dark:text-surface-400">Execution host</dt><dd className="font-mono break-all mt-0.5">{item.executor_id}</dd></div>}
    </dl>
    {item.seen_state.snoozed && item.seen_state.snoozed_until && <p className="mt-3 text-xs text-surface-500 dark:text-surface-400">Hidden from active attention until <time dateTime={item.seen_state.snoozed_until}>{fullTime(item.seen_state.snoozed_until)}</time>.</p>}
    <div className="flex flex-wrap items-center gap-2 mt-4 pt-4 border-t border-surface-100 dark:border-surface-800">
      {action ? <button type="button" className={`btn btn-primary ${focusClass}`} onClick={() => onOpen(item, action)} data-testid={`attention-open-${item.attention_id}`}>
        {attentionActionLabels[action]}<ArrowUpRight size={15} aria-hidden="true" />
      </button> : <span className="text-xs text-surface-500 dark:text-surface-400">No source control is currently available.</span>}
      <button type="button" className={`btn btn-secondary ${focusClass}`} disabled={controlsDisabled} onClick={() => { void onSeen(item, !item.seen_state.seen).catch(() => {}); }}
        aria-label={`${item.seen_state.seen ? 'Mark unseen' : 'Mark seen'}: ${description.title}, ${item.source_id}`}>
        <Eye size={15} aria-hidden="true" />{item.seen_state.seen ? 'Mark unseen' : 'Mark seen'}
      </button>
      {item.seen_state.snoozed ? <button type="button" className={`btn btn-secondary ${focusClass}`} disabled={controlsDisabled} onClick={() => { void onSnooze(item, null).catch(() => {}); }}>Show again</button>
        : <div className="flex items-center gap-2 sm:ml-auto">
          <label htmlFor={`${item.attention_id}-duration`} className="sr-only">Snooze duration for {description.title}, {item.source_id}</label>
          <select id={`${item.attention_id}-duration`} value={duration} disabled={controlsDisabled} onChange={event => setDuration(Number(event.target.value))} className={`${inputClass} !w-auto !py-1.5 !text-xs`}>
            <option value={15}>15 minutes</option><option value={60}>1 hour</option><option value={1440}>1 day</option>
          </select>
          <button type="button" className={`btn btn-secondary ${focusClass}`} disabled={controlsDisabled} onClick={() => { void onSnooze(item, attentionSnoozeUntil(duration)).catch(() => {}); }}
            aria-label={`Snooze: ${description.title}, ${item.source_id}`}><Clock3 size={15} aria-hidden="true" />Snooze</button>
        </div>}
      {pending && <span role="status" className="text-xs text-surface-500 dark:text-surface-400">Saving viewing preference…</span>}
    </div>
  </article>;
}

export function AttentionView({ state, filters, onFiltersChange, onRefresh, onLoadMore, onSeen, onSnooze, onOpen }: AttentionViewProps) {
  const page = visibleAttentionPage(state, filters);
  const restricted = state.status === 'forbidden' || state.status === 'disabled';
  const groups: { key: AttentionCategory; label: string; items: AttentionOccurrence[] }[] = [
    { key: 'action_required', label: 'Needs action', items: page?.items.filter(item => item.category === 'action_required') ?? [] },
    { key: 'watch', label: 'Watch', items: page?.items.filter(item => item.category === 'watch') ?? [] },
  ];
  const currentIds = groups.flatMap(group => group.items.map(item => item.attention_id));
  const priorIds = useRef<string[]>([]);
  const focused = useRef<{ id: string; element: HTMLElement } | null>(null);
  const rows = useRef(new Map<string, HTMLLIElement>());
  const heading = useRef<HTMLHeadingElement>(null);
  useLayoutEffect(() => {
    const previous = focused.current;
    if (previous && !previous.element.isConnected && document.activeElement === document.body) {
      const next = nextAttentionFocus(priorIds.current, currentIds, previous.id);
      const target = next ? rows.current.get(next) : heading.current;
      (target ?? heading.current)?.focus();
    }
    priorIds.current = currentIds;
  });
  function change<Key extends keyof AttentionFilters>(key: Key, value: AttentionFilters[Key]) {
    onFiltersChange(changeAttentionFilter(filters, key, value));
  }
  return <PageContainer testId="attention-view" className="space-y-5">
    <div onFocusCapture={event => {
      const target = event.target as HTMLElement;
      const row = target.closest<HTMLElement>('[data-attention-id]');
      focused.current = row ? { id: row.dataset.attentionId!, element: target } : null;
    }} className="space-y-5">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 ref={heading} tabIndex={-1} data-testid="attention-heading" className={`text-xl font-semibold inline-flex items-center gap-2 rounded ${focusClass}`}><Bell size={21} aria-hidden="true" />Attention</h1>
          <p className="text-sm text-surface-600 dark:text-surface-400 mt-1">Review pending decisions, blocked work and results.</p>
        </div>
        <button type="button" onClick={onRefresh} disabled={state.loading} className={`btn btn-secondary ${focusClass}`} aria-label="Refresh attention"><RefreshCw size={15} aria-hidden="true" />{state.loading ? 'Refreshing…' : 'Refresh'}</button>
      </header>
      {restricted ? <section role="status" className="rounded-xl border border-surface-200 dark:border-surface-700 p-6 bg-white dark:bg-surface-900">
        <h2 className="font-semibold">{state.status === 'forbidden' ? 'Operator access required' : 'Attention is disabled'}</h2>
        <p className="text-sm text-surface-600 dark:text-surface-400 mt-2">{state.status === 'forbidden' ? 'The current authorization does not permit viewing attention. Protected items have been cleared.' : 'Existing work controls remain available in their usual pages.'}</p>
      </section> : <>
        <fieldset className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3 rounded-xl border border-surface-200 dark:border-surface-700 bg-white dark:bg-surface-900 p-4">
          <legend className="sr-only">Filter attention</legend>
          <label className="text-xs font-medium space-y-1 block">Agent ID<input value={filters.agent_id ?? ''} placeholder="All agents" maxLength={2048} onChange={event => change('agent_id', event.target.value || undefined)} className={inputClass} /></label>
          <label className="text-xs font-medium space-y-1 block">Category<select value={filters.category ?? ''} onChange={event => change('category', event.target.value as AttentionCategory || undefined)} className={inputClass}>
            <option value="">All categories</option><option value="action_required">Needs action</option><option value="watch">Watch</option>
          </select></label>
          <label className="text-xs font-medium space-y-1 block">Kind<select value={filters.kind ?? ''} onChange={event => change('kind', event.target.value as AttentionKind || undefined)} className={inputClass}>
            <option value="">All kinds</option>{Object.entries(attentionKinds).map(([kind, item]) => <option key={kind} value={kind}>{item.title}</option>)}
          </select></label>
          <label className="text-xs font-medium space-y-1 block">State<select value={filters.state ?? 'active'} onChange={event => change('state', event.target.value as AttentionFilters['state'])} className={inputClass}>
            <option value="active">Active attention</option><option value="open">Open at source</option><option value="resolved">Resolved at source</option><option value="expired">Expired</option><option value="all">All states</option>
          </select></label>
          <label className="text-xs font-medium space-y-1 block">Priority<select value={filters.priority ?? ''} onChange={event => change('priority', event.target.value ? Number(event.target.value) as AttentionPriority : undefined)} className={inputClass}>
            <option value="">All priorities</option><option value={30}>High</option><option value={20}>Medium</option><option value={10}>Standard</option>
          </select></label>
          <label className="text-xs font-medium space-y-1 block">Viewing state<select value={filters.seen ?? 'all'} onChange={event => change('seen', event.target.value as AttentionFilters['seen'])} className={inputClass}>
            <option value="all">Seen and unseen</option><option value="unseen">Unseen</option><option value="seen">Seen</option><option value="snoozed">Snoozed</option>
          </select></label>
        </fieldset>
        <p className="text-xs text-surface-600 dark:text-surface-400">Seen only records that you reviewed an item. Snooze hides attention temporarily; it does not approve, pause or resolve work.</p>
        <div aria-live="polite" aria-atomic="true" className="space-y-2">
          {state.status === 'stale' && <p className="rounded-lg border border-amber-300 dark:border-amber-800 bg-amber-50 dark:bg-amber-950/30 p-3 text-sm text-amber-900 dark:text-amber-200">This snapshot may be out of date. Refresh to check the current state. Viewing preferences are unavailable until it refreshes.</p>}
          {state.error && <p role="alert" className="rounded-lg border border-red-200 dark:border-red-900 bg-red-50 dark:bg-red-950/30 p-3 text-sm text-red-800 dark:text-red-200">{state.error}</p>}
          {state.notice && <p className="rounded-lg bg-surface-100 dark:bg-surface-800 p-3 text-sm">{state.notice}</p>}
        </div>
        {!page ? <section role="status" aria-busy={state.loading} className="rounded-xl border border-dashed border-surface-300 dark:border-surface-700 p-8 text-center">
          <h2 className="font-medium">{state.loading || state.status === 'loading' ? 'Loading attention…' : 'Attention could not be loaded'}</h2>
          <p className="text-sm text-surface-500 dark:text-surface-400 mt-2">{state.loading || state.status === 'loading' ? 'Reading the current records for this view.' : 'Refresh to try again. A failed read does not mean there is no pending work.'}</p>
        </section> : <>
          <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-surface-500 dark:text-surface-400" data-testid="attention-page-count">
            <p><strong className="text-surface-700 dark:text-surface-200">{page.total}</strong> matching {page.total === 1 ? 'item' : 'items'} · {page.items.length} shown</p>
            <p><time dateTime={page.observed_at} title={fullTime(page.observed_at)}>Snapshot {attentionAge(page.observed_at).toLowerCase()}</time> · {state.streamStatus === 'live' ? 'Live updates' : state.streamStatus === 'reconnecting' ? 'Reconnecting updates' : state.streamStatus === 'connecting' ? 'Connecting updates' : 'Periodic refresh'}</p>
          </div>
          {page.total === 0 ? <section role="status" className="rounded-xl border border-dashed border-surface-300 dark:border-surface-700 p-8 text-center" data-testid="attention-empty">
            <h2 className="font-medium">{state.status === 'ready' ? 'No attention items match this view' : 'The last snapshot had no matching items'}</h2>
            <p className="mt-2 text-sm text-surface-500 dark:text-surface-400">{state.status === 'ready' ? 'Try another filter to inspect seen, snoozed or historical items.' : 'Refresh before relying on this snapshot.'}</p>
          </section> : groups.filter(group => page.counts[group.key] > 0 || group.items.length > 0).map(group => <section key={group.key} aria-labelledby={`attention-group-${group.key}`} className="space-y-3">
            <h2 id={`attention-group-${group.key}`} className="text-base font-semibold flex items-center gap-2">{group.label}<span className="rounded-full bg-surface-100 dark:bg-surface-800 px-2 py-0.5 text-xs font-medium" aria-label={`${page.counts[group.key]} matching items`}>{page.counts[group.key]}</span></h2>
            <ul className="space-y-3">{group.items.map(item => <li key={item.attention_id} data-attention-id={item.attention_id} data-testid={`attention-item-${item.attention_id}`} tabIndex={-1} className={`rounded-xl ${focusClass}`} ref={node => { if (node) rows.current.set(item.attention_id, node); else rows.current.delete(item.attention_id); }}>
              <AttentionCard item={item} pending={state.pendingIds.includes(item.attention_id)} editable={state.status === 'ready' && !state.loading} onSeen={onSeen} onSnooze={onSnooze} onOpen={onOpen} />
            </li>)}</ul>
            {!group.items.length && <p className="text-sm text-surface-500 dark:text-surface-400">More items in this group are on the next page.</p>}
          </section>)}
          {page.next_cursor && <div className="flex justify-center"><button type="button" className={`btn btn-secondary ${focusClass}`} disabled={state.loadingMore || state.loading || state.status !== 'ready'} onClick={onLoadMore}>{state.loadingMore ? 'Loading more…' : 'Load more attention'}</button></div>}
        </>}
      </>}
    </div>
  </PageContainer>;
}

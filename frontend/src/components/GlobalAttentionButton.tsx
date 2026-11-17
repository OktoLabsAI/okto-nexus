import {Bell} from 'lucide-react';
import type {AttentionState} from '../attentionTypes';

export function GlobalAttentionButton({state, onOpen}: {state: AttentionState; onOpen: () => void}) {
  const summary = state.summary;
  const count = (value: number) => Number.isSafeInteger(value) && value >= 0;
  const usable = (state.status === 'ready' || state.status === 'stale') && summary &&
    summary.filters.workspace_id === undefined && summary.filters.state === 'active' && summary.filters.seen === 'all' &&
    count(summary.total) && count(summary.counts.action_required) && count(summary.counts.watch);
  const stale = state.status === 'stale' || state.loading;
  const text = usable ? `${summary.total}${stale ? '*' : ''}` : state.status === 'loading' ? '…' : '!';
  const detail = usable
    ? `${summary.counts.action_required} need action, ${summary.counts.watch} to watch.${stale ? ' Last known counts, out of date.' : ''}`
    : state.status === 'disabled' ? 'Attention is disabled. Open available questions and approval controls.'
    : state.status === 'forbidden' ? 'Attention access is unavailable. Protected counts have been cleared.'
    : state.status === 'loading' ? 'Attention counts are loading.' : 'Attention counts are unknown. Open to inspect available controls.';
  const label = `Needs attention. All projects and Server. ${detail}`;
  return <button type="button" onClick={onOpen} aria-label={label} title={label}
    className="btn btn-secondary flex items-center gap-2" data-testid="global-attention-button">
    <Bell size={16} aria-hidden="true"/><span className="hidden sm:inline">Needs attention</span>
    <span data-testid="attention-badge" className="min-w-[18px] rounded-full bg-accent-600 px-1.5 py-0.5 text-center text-xs font-semibold text-white">{text}</span>
  </button>;
}

import type {AttentionFilters, AttentionState, AttentionSummary} from './attentionTypes';
import type {ObservationReadState} from './observationReader';

export type ScopedAttentionSummaryQuery = AttentionFilters & {state: 'active'; seen: 'all'};
export function scopedAttentionSummaryQuery(workspace: string, enabled: boolean): ScopedAttentionSummaryQuery | null {
  if (!enabled || !workspace) return null;
  return workspace === 'all' ? {state: 'active', seen: 'all'} : {state: 'active', seen: 'all', workspace_id: workspace};
}
export function attentionSummaryRefreshAfter(value: AttentionSummary): number {
  return Number.isFinite(value.refresh_after_seconds)
    ? Math.max(0, Math.min(15, value.refresh_after_seconds)) : 0;
}

/** Adapt a passive summary read without inventing a page, queue or viewing mutations. */
export function scopedAttentionSummaryState(read: ObservationReadState<AttentionSummary>, workspace: string, enabled = true): AttentionState {
  const base: AttentionState = {page: null, summary: null, status: 'loading', loading: false,
    loadingMore: false, pendingIds: [], error: null, notice: null, streamStatus: 'off'};
  if (!scopedAttentionSummaryQuery(workspace, enabled)) return {...base, status: 'disabled'};
  if (read.status === 'forbidden') return {...base, status: 'forbidden', error: 'Operator access is required. Protected attention data has been cleared.'};
  if (read.status === 'unavailable') return {...base, status: 'error', error: 'Attention summary is unavailable on this Server.'};
  const value = read.value;
  if (value && ((value.filters.workspace_id ?? 'all') !== workspace || value.filters.state !== 'active' || value.filters.seen !== 'all')) {
    return {...base, status: 'error', error: 'Attention summary does not match the selected project.'};
  }
  if (read.status === 'error') return {...base, status: 'error', error: 'Attention summary could not be refreshed.'};
  return {...base, summary: value, status: read.status, loading: read.loading,
    error: read.error ? 'Attention summary could not be refreshed. Displayed data may be out of date.' : null};
}

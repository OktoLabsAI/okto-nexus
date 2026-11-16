import {api} from '../api';
import {attentionSummaryRefreshAfter, scopedAttentionSummaryQuery, scopedAttentionSummaryState} from '../attentionSummaryState';
import {useObservationRead} from './useObservationRead';

/** Passive active/all summary, independent of queue filters; no additional event stream. */
export function useScopedAttentionSummary({workspace, enabled}: {workspace: string; enabled: boolean}) {
  const query = scopedAttentionSummaryQuery(workspace, enabled);
  const {state, refresh} = useObservationRead(query,
    (filters, signal) => api.attentionSummary(filters, signal), attentionSummaryRefreshAfter);
  return {state: scopedAttentionSummaryState(state, workspace, enabled), refresh};
}

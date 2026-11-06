import type { AttentionAction, AttentionFilters, AttentionKind, AttentionOccurrence, AttentionPage, AttentionState } from './attentionTypes';

export const attentionKinds: Record<AttentionKind, { title: string; reason: string }> = {
  approval_pending: { title: 'Approval awaiting review', reason: 'A canonical approval needs review by its authorized recipient.' },
  native_permission_pending: { title: 'Runtime permission requested', reason: 'The runtime is waiting for a permission decision.' },
  native_question_pending: { title: 'Runtime question for the operator', reason: 'The runtime has a question for its authorized operator.' },
  question_waiting_for_agent: { title: 'Question waiting for an agent', reason: 'A runtime question is addressed to this agent. Its recipient must respond.' },
  verification_pending: { title: 'Handoff awaiting verification', reason: 'Submitted work is waiting for its canonical verification.' },
  execution_outcome_unknown: { title: 'Execution outcome unknown', reason: 'The effect of this execution has not been confirmed. Inspect its recorded state.' },
  delivery_parked: { title: 'Delivery needs attention', reason: 'This delivery is parked and needs inspection of its delivery record.' },
  runtime_recovery_attention: { title: 'Runtime recovery needs attention', reason: 'Retained runtime work needs review of its recovery state.' },
  execution_authority_blocking: { title: 'Execution authorization changed', reason: 'Pending work is blocked by its current execution authorization or configuration.' },
  executor_disconnected_with_work: { title: 'Execution host disconnected', reason: 'This disconnected host still has pending work.' },
  handoff_unclaimed_aged: { title: 'Handoff still unclaimed', reason: 'This open handoff has remained unclaimed beyond the configured threshold.' },
  result_unseen: { title: 'Result ready to inspect', reason: 'A canonical result is available for inspection.' },
  cleanup_attention: { title: 'Cleanup needs inspection', reason: 'A cleanup attempt has not been confirmed. Inspect its existing maintenance record.' },
};

export const attentionActionLabels: Record<AttentionAction, string> = {
  inspect_approval: 'Open approval', respond_native: 'Open question', decide_native: 'Review permission',
  inspect_handoff: 'Open handoff', verify_handoff: 'Review verification', inspect_operation: 'Inspect operation',
  inspect_recovery: 'Inspect recovery', review_authority: 'Review authorization', inspect_executor: 'Open execution host',
  inspect_result: 'Inspect result', inspect_cleanup: 'Inspect cleanup', inspect_delivery: 'Inspect delivery',
  decide_approval: 'Review approval',
};

const actionOrder: AttentionAction[] = [
  'respond_native', 'decide_native', 'decide_approval', 'verify_handoff', 'inspect_cleanup',
  'inspect_result', 'inspect_recovery', 'review_authority', 'inspect_delivery',
  'inspect_executor', 'inspect_approval', 'inspect_handoff', 'inspect_operation',
];
const reviewActions = new Set<AttentionAction>(['respond_native', 'decide_native', 'decide_approval', 'verify_handoff', 'review_authority']);

export function attentionDescription(item: Pick<AttentionOccurrence, 'kind'> & Partial<Pick<AttentionOccurrence, 'resolution'>>) {
  const description = Object.hasOwn(attentionKinds, item.kind) ? attentionKinds[item.kind]
    : { title: 'Attention item', reason: 'Inspect the original record for its current state.' };
  if (item.resolution === 'expired') return { ...description, reason: 'This request has expired. Inspect the original record for its history.' };
  if (item.resolution === 'resolved' && item.kind !== 'result_unseen') {
    return { ...description, reason: 'This episode is resolved at its source. Inspect the original record for its history.' };
  }
  return description;
}

export function primaryAttentionAction(item: Pick<AttentionOccurrence, 'allowed_actions' | 'resolution' | 'freshness'>): AttentionAction | null {
  return actionOrder.find(action => item.allowed_actions.includes(action)
    && (item.resolution === 'open' && item.freshness === 'current' || !reviewActions.has(action))) ?? null;
}

export function attentionAge(timestamp: string, now = Date.now()): string {
  const start = Date.parse(timestamp);
  if (!Number.isFinite(start) || !Number.isFinite(now)) return 'Unknown age';
  const minutes = Math.floor(Math.max(0, now - start) / 60000);
  if (minutes < 1) return 'Just now';
  if (minutes < 60) return `${minutes}m ago`;
  if (minutes < 1440) return `${Math.floor(minutes / 60)}h ago`;
  return `${Math.floor(minutes / 1440)}d ago`;
}

export function attentionSnoozeUntil(minutes: number, now = Date.now()): string {
  if (![15, 60, 1440].includes(minutes) || !Number.isFinite(now)) throw new Error('Choose a supported snooze duration.');
  return new Date(now + minutes * 60000).toISOString();
}

export function visibleAttentionPage(state: Pick<AttentionState, 'status' | 'page'>, filters: AttentionFilters): AttentionPage | null {
  if (state.status === 'forbidden' || state.status === 'disabled' || !state.page) return null;
  const expected = { ...filters, state: filters.state ?? 'active', seen: filters.seen ?? 'all' };
  const keys: (keyof AttentionFilters)[] = ['workspace_id', 'agent_id', 'category', 'kind', 'state', 'priority', 'seen'];
  return keys.every(key => state.page!.filters[key] === expected[key]) ? state.page : null;
}

export function changeAttentionFilter<Key extends keyof AttentionFilters>(filters: AttentionFilters, key: Key, value: AttentionFilters[Key]): AttentionFilters {
  const next = { ...filters };
  if (value === undefined) delete next[key]; else next[key] = value;
  // Snoozed occurrences are deliberately inactive in the canonical projection.
  if (key === 'seen' && value === 'snoozed') next.state = 'all';
  return next;
}

export function nextAttentionFocus(previous: string[], current: string[], removed: string): string | null {
  if (current.includes(removed)) return removed;
  const position = previous.indexOf(removed);
  if (position >= 0) {
    const next = previous.slice(position + 1).find(id => current.includes(id));
    if (next) return next;
    const prior = previous.slice(0, position).reverse().find(id => current.includes(id));
    if (prior) return prior;
  }
  return current[0] ?? null;
}

export function attentionSourceLabel(source: string): string {
  const labels: Record<string, string> = {
    approval: 'Approval', execution_native_request: 'Native request', handoff: 'Handoff',
    execution_operation: 'Execution operation', delivery_operation: 'Delivery operation',
    message_delivery: 'Message delivery', runtime_pending_delivery: 'Recovery record',
    execution_executor: 'Execution host', execution_result: 'Execution result',
    runtime_result: 'Runtime result', runtime_result_maintenance: 'Cleanup record',
  };
  return Object.hasOwn(labels, source) ? labels[source] : 'Source record';
}

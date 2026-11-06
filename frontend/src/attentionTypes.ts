// Version 1 of the canonical operator attention API. Cursors remain opaque.
export type AttentionKind =
  | 'native_permission_pending' | 'native_question_pending' | 'question_waiting_for_agent'
  | 'verification_pending' | 'execution_outcome_unknown' | 'delivery_parked'
  | 'runtime_recovery_attention' | 'execution_authority_blocking'
  | 'executor_disconnected_with_work' | 'handoff_unclaimed_aged' | 'result_unseen'
  | 'cleanup_attention' | 'approval_pending';
export type AttentionAction =
  | 'inspect_approval' | 'respond_native' | 'decide_native' | 'inspect_handoff'
  | 'verify_handoff' | 'inspect_operation' | 'inspect_recovery' | 'review_authority'
  | 'inspect_executor' | 'inspect_result' | 'inspect_cleanup' | 'inspect_delivery'
  | 'decide_approval';
export type AttentionCategory = 'action_required' | 'watch';
export type AttentionPriority = 10 | 20 | 30;
export type AttentionResolution = 'open' | 'resolved' | 'expired';
export type AttentionFreshness = 'current' | 'stale' | 'unavailable';
export interface AttentionSeenState {
  seen: boolean;
  seen_at: string | null;
  snoozed: boolean;
  snoozed_until: string | null;
  revision: number;
}
export interface AttentionOccurrence {
  attention_id: string;
  kind: AttentionKind;
  category: AttentionCategory;
  severity: 'info' | 'warning' | 'error';
  priority: AttentionPriority;
  agent_id: string | null;
  workspace_id: string | null;
  session_id: string | null;
  operation_id: string | null;
  message_id: string | null;
  result_id: string | null;
  executor_id: string | null;
  source_type: string;
  source_id: string;
  source_revision: string;
  first_detected_at: string;
  last_changed_at: string;
  freshness: AttentionFreshness;
  summary_code: string;
  allowed_actions: AttentionAction[];
  resolution: AttentionResolution;
  active: boolean;
  next_change_at: string | null;
  seen_state: AttentionSeenState;
}
export interface AttentionFilters {
  workspace_id?: string;
  agent_id?: string;
  category?: AttentionCategory;
  kind?: AttentionKind;
  state?: 'active' | 'all' | AttentionResolution;
  priority?: AttentionPriority;
  seen?: 'all' | 'seen' | 'unseen' | 'snoozed';
}
export interface AttentionPageQuery extends AttentionFilters {
  cursor?: string;
  limit?: number;
}
export interface AttentionCounts {
  action_required: number;
  watch: number;
  priority: { '10': number; '20': number; '30': number };
  unseen: number;
  snoozed: number;
}
export interface AttentionSummary {
  version: 1;
  filters: AttentionFilters & { state: NonNullable<AttentionFilters['state']>; seen: NonNullable<AttentionFilters['seen']> };
  total: number;
  counts: AttentionCounts;
  event_cursor: number;
  event_low_watermark: number | null;
  snapshot_revision: string;
  observed_at: string;
  next_refresh_at: string;
  refresh_after_seconds: number;
}
export interface AttentionPage extends AttentionSummary {
  items: AttentionOccurrence[];
  next_cursor: string | null;
}
export interface AttentionSeenRequest {
  source_revision: string;
  preference_revision: number;
  seen?: boolean;
}
export interface AttentionSnoozeRequest {
  source_revision: string;
  preference_revision: number;
  until: string | null;
}
export interface AttentionPreferenceResponse {
  version: 1;
  item: AttentionOccurrence;
  observed_at: string;
}
export type AttentionLoadStatus = 'loading' | 'ready' | 'stale' | 'error' | 'forbidden' | 'disabled';
export interface AttentionState {
  page: AttentionPage | null;
  summary: AttentionSummary | null;
  status: AttentionLoadStatus;
  loading: boolean;
  loadingMore: boolean;
  pendingIds: string[];
  error: string | null;
  notice: string | null;
  streamStatus: 'connecting' | 'live' | 'reconnecting' | 'off';
}

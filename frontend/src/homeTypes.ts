import type { AttentionOccurrence } from './attentionTypes';
import type { ExternalObservation } from './observationTypes';

export interface HomeScope { workspace_id: string | null; agent_id?: string; state?: string }
export interface HomeFilters { workspace_id?: string; agent_id?: string; state?: string }
export type HomeSectionStatus = 'ready' | 'partial' | 'unavailable' | 'disabled' | 'forbidden';
export interface HomeSection<T> {
  status: HomeSectionStatus; as_of: string | null; next_refresh_at: string | null;
  items: T[]; total: number | null; total_is_exact: boolean;
  has_more: boolean; next_cursor: string | null; reason_code?: string; revision?: string;
}
interface HomeTargetBase { server_id: string; workspace_id: string | null }
export type HomeTarget =
  | (HomeTargetBase & { kind: 'handoff'; handoff_id: string })
  | (HomeTargetBase & { kind: 'execution' | 'result'; executor_id: string; session_id: string; operation_id: string })
  | (HomeTargetBase & { kind: 'message'; message_id: string })
  | (HomeTargetBase & { kind: 'approval'; approval_id: string })
  | (HomeTargetBase & { kind: 'external_observation'; source_id: string; observed_instance_id: string; generation: number });
export interface HomeSourceRef { type: string; id: string; revision: string }
export type HomeDisplayState = 'awaiting_owner' | 'claimed' | 'queued' | 'native_accepted' | 'running'
  | 'awaiting_dependency' | 'awaiting_operator' | 'awaiting_agent' | 'awaiting_verification'
  | 'outcome_unknown' | 'completed' | 'turn_completed' | 'result_available_cleanup_pending'
  | 'failed' | 'cancelled' | 'unknown';
export interface HomeActivity {
  id: string; kind: 'handoff' | 'conversation_turn' | 'direct_operation'; source_ref: HomeSourceRef;
  workspace_id: string; title: string; title_origin: 'canonical_title' | 'message_subject' | 'fallback';
  agent_ids: string[]; display_state: HomeDisplayState; state_since: string | null;
  last_activity_at: string | null; evidence_status: 'confirmed' | 'unknown'; attention_refs: string[];
  runtime_refs: Array<{ executor_id: string; session_id: string; operation_id?: string }>;
  detail_target: HomeTarget | null; running_count: number; reason?: string; parent_target?: HomeTarget | null; attempt_count?: number;
}
export interface HomeResult {
  id: string; source_ref: HomeSourceRef; workspace_id: string; agent_id: string | null;
  title: string; preview: string | null; truncated: boolean; outcome: string;
  verification_state: string | null; cleanup_state: string | null; created_at: string | null;
  detail_target: HomeTarget | null; artifacts: Array<{ artifact_id: string; filename?: string; media_type?: string }>;
  view_state: 'unseen' | 'seen' | 'not_tracked'; attention: AttentionOccurrence | null;
}
export interface HomeAgent {
  agent_id: string; name: string; workspace_ids: string[]; presence: string; connectivity: string;
  activity: 'not_reported'; capabilities?: string[];
}
export interface HomeCounter {
  value: number | null; total_is_exact: boolean; label: string;
  unit: 'activities' | 'occurrences' | 'results' | 'external_instances'; reason_code?: string;
}
export interface HomeSummary {
  running: HomeCounter; waiting_start: HomeCounter; needs_you: HomeCounter;
  results: HomeCounter; external: HomeCounter;
}
export interface HomeOverview {
  version: 1; scope: HomeScope; server_id: string; generated_at: string; snapshot_id: string;
  event_cursor: number; event_low_watermark: number | null; summary: HomeSummary;
  work: HomeSection<HomeActivity>; attention: HomeSection<AttentionOccurrence>;
  results: HomeSection<HomeResult>; agents: HomeSection<HomeAgent>;
  external_activity: HomeSection<ExternalObservation>;
}
export interface HomeFeedEvent {
  id: string; kind: string; label: string; created_at: string; workspace_id: string;
  agent_id: string | null; detail_target?: HomeTarget | null;
}
export interface HomePage<T> extends HomeSection<T> {
  version: 1; scope: HomeScope; server_id: string; generated_at: string; snapshot_id: string;
}
export interface HomePageQuery extends HomeFilters { cursor?: string; limit?: number }
export type HomePageSection = 'work' | 'results' | 'activity' | 'agents' | 'external' | 'attention';
export type HomeSectionName = 'work' | 'attention' | 'results' | 'agents' | 'external_activity' | 'activity';
export interface HomeResolvedTarget {
  version: 1; target: HomeTarget; available: boolean; source_revision: string;
  agent_id?: string | null; reason_code?: string; observed_at?: string;
}

import type { AttentionOccurrence, AttentionAction } from './attentionTypes';
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
  | (HomeTargetBase & { kind: 'session'; workspace_id: string; executor_id: string; session_id: string })
  | (HomeTargetBase & { kind: 'connection'; workspace_id: string; executor_id: string; binding_id: string; agent_id: string })
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
  server_attention: HomeSection<AttentionOccurrence>;
}
export interface HomeFeedEvent {
  id: string; kind: string; label: string; created_at: string; workspace_id: string;
  agent_id: string | null; detail_target?: HomeTarget | null;
}
export interface HomePage<T> extends HomeSection<T> {
  version: 1; scope: HomeScope; server_id: string; generated_at: string; snapshot_id: string;
}
export interface HomePageQuery extends HomeFilters { cursor?: string; limit?: number }
export type HomePageSection = 'work' | 'results' | 'activity' | 'agents' | 'external' | 'attention' | 'server_attention';
export type HomeSectionName = 'work' | 'attention' | 'results' | 'agents' | 'external_activity' | 'activity' | 'server_attention';
export interface HomeResolvedTarget {
  version: 1; target: HomeTarget; available: boolean; source_revision: string;
  agent_id?: string | null; reason_code?: string; observed_at?: string;
  session_context?: HomeSessionContext;
  connection_context?: HomeConnectionContext;
}
export interface HomeConnectionContext {
  server_id: string; executor_id: string; workspace_id: string;
  binding_id: string; workspace_binding_id: string; agent_id: string;
}
export interface HomeSessionContext extends HomeConnectionContext {
  session_id: string; lifecycle_state: string;
}

export type HomeQuickFilter = 'active' | 'needs_you' | 'results' | 'all';
export interface HomeEntryFilters extends HomeFilters { quick?: HomeQuickFilter; harness?: string; host?: string }
export interface HomeEntryScope extends HomeScope { quick: HomeQuickFilter; include_recent_results: boolean; harness?: string; host?: string }
export interface HomeEntryQuery extends HomeEntryFilters { cursor?: string; limit?: number; preview?: number }
export interface HomeSessionRef { server_id: string; executor_id: string; workspace_id: string; session_id: string }
export interface HomeConnectionRef { server_id: string; executor_id: string; workspace_id: string; binding_id: string; agent_id: string }
export type HomeEntryKind = 'work' | 'session' | 'connection' | 'external' | 'attention';
export type HomeEntryDisplayState = HomeDisplayState | 'configured' | 'connected' | 'idle' | 'offline' | 'stale';
export type HomeEntryAction = {kind:'inspect'; target:HomeTarget} | {kind:'attention'; attention_id:string; action:AttentionAction};
export interface HomeEntry {
  id:string; kind:HomeEntryKind; source_ref:HomeSourceRef; workspace_id:string; agent_id:string|null;
  title:string; agent_label:string|null; harness_label:string|null; host_label:string|null;
  display_state:HomeEntryDisplayState; evidence:'confirmed'|'reported'|'inferred'|'unknown'; state_since:string|null;
  sessions:HomeSessionRef[]; sessions_total:number|null; has_more_sessions:boolean; sessions_cursor:string|null;
  attention_refs:string[]; result_refs:string[]; target:HomeTarget|null;
  result_tracking:'unseen'|'unknown'|'seen'|'not_applicable'; actions:HomeEntryAction[];
  attention_preview:AttentionOccurrence[]; attention_total:number|null; has_more_attention:boolean; attention_cursor:string|null;
  results_preview:HomeResult[]; results_total:number|null; has_more_results:boolean; results_cursor:string|null;
  related_coverage:{attention:'ready'|'unknown';results:'ready'|'unknown'};
  external:ExternalObservation[]; as_of:string|null; next_refresh_at:string|null;
}
export interface HomeEntryGroup {
  id:string; server_id:string; executor_id:string|null; workspace_id:string; agent_id:string|null;
  connection:HomeConnectionRef|null; label:string; agent_label:string|null; workspace_label:string|null; host_label:string|null;
  children:HomeEntry[]; children_total:number|null; has_more_children:boolean; children_cursor:string|null;
}
export interface HomeEntryCount { value:number|null; total_is_exact:boolean; unit:'activities'|'external_instances'|'occurrences'|'sessions'|'results' }
export interface HomeEntrySummary {
  activities:HomeEntryCount; external_instances:HomeEntryCount; occurrences:HomeEntryCount;
  sessions:HomeEntryCount; results:HomeEntryCount; unseen_results:HomeEntryCount;
}
export type HomeEntryPartition = 'groups'|'children'|'sessions'|'attention'|'results';
export type HomeBoardColumn = 'active'|'needs_you'|'results';
export interface HomeBoardEntry extends HomeEntry {group_id:string;entry_revision:string}
export interface HomeBoardSlice {
  items:HomeBoardEntry[];total:number|null;total_is_exact:boolean;has_more:boolean;next_cursor:string|null;
}
export interface HomeBoardMetadata {
  version:1;scope:HomeEntryScope;server_id:string;generated_at:string;as_of:string|null;next_refresh_at:string|null;
  snapshot_id:string|null;revision:string|null;entry_revision:string|null;status:HomeSectionStatus;
  source_status:Record<string,HomeSectionStatus>;coverage:{result_tracking:'unknown'|'partial'|'ready'};
  inventory?:{connections:{value:number|null;total_is_exact:boolean;unit:'connections'}};
  summary:HomeEntrySummary;event_cursor:number;event_low_watermark:number|null;
  server_attention:Pick<HomeSection<AttentionOccurrence>,'status'|'items'|'total'|'total_is_exact'|'has_more'>;
}
export interface HomeBoard extends HomeBoardMetadata {partition:'board';columns:Record<HomeBoardColumn,HomeBoardSlice>}
export interface HomeBoardPage extends HomeBoardMetadata,HomeBoardSlice {partition:'board_column';column:HomeBoardColumn}
export type HomeBoardQuery = Omit<HomeEntryQuery,'quick'>;
export interface HomeHarnessChild extends HomeBoardEntry {shared_reference:boolean}
export interface HomeHarnessConnection extends HomeConnectionContext {
  harness_id:string;agent_label:string|null;harness_label?:string|null;host_label:string|null;workspace_label?:string|null;
}
export interface HomeHarnessCard {
  kind:'harness';blocks_harness:boolean|null;blocking_request_ids:string[];
  activity_state:'waiting_for_user'|'awaiting_confirmation'|'working'|'registered'|'unknown';
  blocking_requests:HomeHarnessRequest[];reminder_snoozed:boolean;
  reconnect_available:false;reconnect_reason:string;
  id:string;group_id:string;connection:HomeHarnessConnection;target:HomeTarget;
  children:HomeHarnessChild[];children_total:number|null;has_more_children:boolean;children_cursor:string|null;
  summary:HomeEntrySummary;
  context_state:'registered';
  events_preview:HomeHarnessEvent[];events_total:number|null;has_more_events:boolean;
  events_summary:Record<'attention'|'results'|'work'|'sessions'|'external',number|null>;
}
export interface HomeHarnessEvent {
  id:string;kind:'attention'|'result'|'work'|'session'|'external';entry_id:string;group_id:string;entry_revision:string;
  target:HomeTarget|null;title:string;display_state:HomeEntryDisplayState;evidence:HomeEntry['evidence'];occurred_at:string|null;
  attention?:AttentionOccurrence|null;result?:HomeResult|null;
  entry:HomeHarnessChild;
}
export interface HomeHarnessSlice {
  items:HomeHarnessBoardItem[];total:number|null;total_is_exact:boolean;has_more:boolean;next_cursor:string|null;
}
export interface HomeHarnessRef {card_id:string;connection:HomeHarnessConnection}
export interface HomeHarnessRequest {
  kind:'request';id:string;request:AttentionOccurrence;entry:HomeHarnessChild;
  harness_refs:HomeHarnessRef[];blocks_harness:boolean|null;notification_visible:boolean;
}
export interface HomeHarnessDelivery {
  kind:'delivery';id:string;result:HomeResult|null;report:AttentionOccurrence|null;entry:HomeHarnessChild;harness_refs:HomeHarnessRef[];
  completion_evidence:'canonical'|'reported';
}
export type HomeHarnessBoardItem=HomeHarnessCard|HomeHarnessRequest|HomeHarnessDelivery;
export interface HomeHarnessBoard extends HomeBoardMetadata {
  partition:'harness_board';columns:Record<HomeBoardColumn,HomeHarnessSlice>;
  unlinked:{items:HomeHarnessChild[];total:number|null;total_is_exact:boolean;has_more:boolean;next_cursor:string|null};
}
export interface HomeHarnessBoardPage extends HomeBoardMetadata,HomeHarnessSlice {partition:'harness_board_column';column:HomeBoardColumn}
export interface HomeHarnessChildrenPage extends HomeBoardMetadata {
  partition:'harness_children'|'harness_unlinked';card_id?:string|null;items:HomeHarnessChild[];
  total:number|null;total_is_exact:boolean;has_more:boolean;next_cursor:string|null;
}
export interface HomeEntryPage<T> extends Omit<HomeSection<T>, 'revision'> {
  version:1; scope:HomeEntryScope; server_id:string; generated_at:string; snapshot_id:string|null;
  revision:string|null; partition:HomeEntryPartition; group_id:string|null; entry_id:string|null;
  event_cursor:number; event_low_watermark:number|null; source_status:Record<string,HomeSectionStatus>;
  coverage:{result_tracking:'unknown'|'partial'|'ready'}; summary:HomeEntrySummary;
  inventory?:{connections:{value:number|null;total_is_exact:boolean;unit:'connections'}};
  server_attention:Pick<HomeSection<AttentionOccurrence>,'status'|'items'|'total'|'total_is_exact'|'has_more'>;
}

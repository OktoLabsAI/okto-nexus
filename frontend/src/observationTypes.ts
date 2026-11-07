/** External telemetry is never canonical presence, execution state or capacity. */
export type ObservationActivity = 'working' | 'idle' | 'blocked' | 'unknown';
export type ObservationFreshness = 'current' | 'stale' | 'unknown' | 'unavailable';
export interface CanonicalSessionReference {
  server_id: string;
  executor_id: string;
  session_id: string;
  open_operation_id: string;
  session_owner_generation: number;
  stream_epoch: string;
}
export interface CanonicalObservation {
  correlation_revision: number;
  verified_at: string;
  provenance: {
    external_binding_provenance: 'operator_attested_external_binding';
    native_birth_provenance: 'machine_checked_native_birth';
  };
  session_lifecycle_state: string;
  last_received_receipt: null | { status: 'unknown'; reason: 'receipt_provenance_unavailable' } | {
    status: 'verified';
    operation_id: string;
    action: string;
    stage: string;
    receipt_revision: number;
    received_at: string;
    provenance: 'core_committed';
  };
  precedence: 'canonical_core_facts';
}
export interface ExternalObservation {
  observed_instance_id: string;
  source_id: string;
  agent_id: string;
  workspace_id: string;
  generation: number;
  external_instance_ref: string;
  source_kind: 'herdr' | 'hook' | 'custom';
  source_revision: number;
  freshness: ObservationFreshness;
  activity_state: ObservationActivity;
  source_last_received_at: string | null;
  source_continuity: 'unknown' | 'delayed' | 'recent';
  last_report: {
    sequence: number;
    state: ObservationActivity;
    evidence: 'reported' | 'inferred';
    observed_at: string | null;
    received_at: string;
    valid_until: string;
    reason_code: string | null;
    reason_text: string | null;
    current_completion_ref: string | null;
    last_completion_ref: string | null;
    last_completion_received_at: string | null;
  } | null;
  observational_only: true;
  canonical_session_ref: CanonicalSessionReference | null;
  /** Older Servers omit this field. Null replaces any previous correlation. */
  canonical_observation?: CanonicalObservation | null;
}
export interface ObservationFilters { agent_id?: string; workspace_id?: string; source_id?: string }
export interface ObservationPageQuery extends ObservationFilters { after?: string; limit?: number }
export interface ObservationPage {
  items: ExternalObservation[];
  next_after: string | null;
  observed_at: string;
  feature_enabled: boolean;
}
export interface ObservationDeadline {
  observed_at: string;
  next_refresh_at: string;
  refresh_after_seconds: number;
  feature_enabled: boolean;
}
export interface ObservationDetail extends ObservationDeadline { item: ExternalObservation }
export interface ObservationCounts {
  total_instances: number;
  activity: Record<ObservationActivity, number>;
  freshness: Record<ObservationFreshness, number>;
}
export interface ObservationSummary extends ObservationDeadline, ObservationCounts {
  version: 1;
  filters: ObservationFilters;
  agents: (ObservationCounts & { agent_id: string })[];
}

// API client for the Nexus serve surfaces. Single source of truth for the
// envelope ({ok, data | error}) and for credential handling: the operator
// key lives in sessionStorage only (cleared when the tab closes) and is sent
// via x-api-key. Issued AGENT keys are never stored anywhere (br_ae340cae).

export interface Envelope<T> {
  ok: boolean;
  data?: T;
  // details is populated for TAG_IN_USE (409): the normative usage payload
  // the Tag Registry renders (key/value/total_uses/uses).
  error?: { code: string; message: string; details?: unknown };
}

export interface GraphNode {
  agent_id: string;
  role: string | null;
  capabilities: Record<string, unknown>;
  is_active: boolean;
  has_key: boolean;
  last_seen_at: string | null;
  presence: "present" | "stale" | "offline";
  sessions: number;
  inbox: { unread: number; delivered: number; read: number; parked: number };
}

export interface GraphEdge {
  from: string;
  to: string;
  count: number;
  last_at: string;
  in_flight: { unread: number; delivered: number };
  // Most recent COMPLETED hop (pulled or acked): anchors the grey
  // flow-decay edge (light -> mid -> dark grey, gone after 15 min).
  last_done_at: string | null;
}

// Verification contract descriptor (R-I4): always materialised on verifiable
// handoffs - {kind:"creator"} is written at create time, never inferred.
export interface VerifyBy {
  kind: "creator" | "agent" | "capability";
  agent_id?: string;
  capability?: string;
}

export interface GraphHandoff {
  handoff_id: string;
  workspace_id: string;
  status: string;
  created_at: string;
  from_agent_id: string | null;
  claimed_by: string | null;
  target: unknown;
  // Trajectory correlation (R-I1): non-null only when the feature stamped one.
  trace_id?: string | null;
  // Verification contract (R-I4): present ONLY on verifiable handoffs
  // (omitted otherwise - the trace_id pattern); the UI self-gates on data.
  acceptance_criteria?: string[];
  verify_by?: VerifyBy;
  verification_feedback?: string;
  // Dependency edges (R-I5): present ONLY on handoffs created with
  // depends_on (same self-gating pattern - the UI never consults the flag).
  depends_on?: string[];
  dependencies?: {
    total: number;
    satisfied: number;
    pending: number;
    failed: number;
  };
}

export interface GraphSnapshot {
  workspace_id: string | null;
  generated_at: string;
  window_hours: number;
  nodes: GraphNode[];
  channels: { channel_id: string; workspace_id: string; name: string }[];
  edges: { messages: GraphEdge[]; handoffs: GraphHandoff[] };
}

// Permission flags: {group: {flag: bool | number}} - the Pulse grammar
// adapted to the Nexus communication domain (migration 011). The string[]
// allowed_peers flag was REMOVED in F1 (tag scoping): allowlists are now the
// tag-based comm_scope.outbound audience selector.
export type PermissionFlags = Record<string, Record<string, boolean | number>>;

// Agent tags and audience selectors: {KEY: [VALUE, ...]}. Every key/value
// must be registered in the central tag catalog (fail-closed).
export type TagMap = Record<string, string[]>;

// F3 rich selector grammar (Kubernetes matchExpressions parity). Expressions
// are ANDed; In/NotIn intersect the agent's values under `key` (hierarchical
// by "/" segment: ENG covers ENG/BACKEND); Exists/DoesNotExist are bare
// presence checks and carry no values. ABSENCE TRAP: NotIn and DoesNotExist
// also match agents that lack the key entirely.
export type TagOperator = "In" | "NotIn" | "Exists" | "DoesNotExist";
export interface TagExpression {
  key: string;
  operator: TagOperator;
  values?: string[];
}

// A selector is either the flat map (sugar for one In per key; AND across
// keys, OR within values) or the rich expression list.
export type TagSelector = TagMap | TagExpression[];

// F2 double intersection: outbound bounds who the agent can REACH, inbound
// bounds who can reach IT (senders whose tags miss the selector are blocked
// or silently dropped). Either leg absent/null = unrestricted on that side.
export interface CommScope {
  outbound?: TagSelector | null;
  inbound?: TagSelector | null;
}

export interface TagValueRow {
  value: string;
  description: string | null;
  created_at: string;
}

export interface TagKeyRow {
  key: string;
  description: string | null;
  created_at: string;
  values: TagValueRow[];
}

// One agent reference to a tag pair, as reported by the 409 TAG_IN_USE
// details payload (and recomputable client-side from the agents list).
export interface TagUse {
  agent_id: string;
  kind: "agent_tags" | "comm_scope";
}

export interface TagInUseDetails {
  key: string;
  value: string | null;
  total_uses: number;
  uses: TagUse[];
}

// Central capability catalog (migration 014): the operator-managed,
// fail-closed registry of capability names. Agents may only announce (and
// targets may only reference) names registered here.
export interface CapabilityRow {
  name: string;
  description: string | null;
  created_at: string;
}

// One agent owning a capability, as reported by the 409 CAPABILITY_IN_USE
// details payload (and recomputable client-side from the agents list).
export interface CapabilityUse {
  agent_id: string;
  kind: "capabilities";
}

export interface CapabilityInUseDetails {
  capability: string;
  total_uses: number;
  uses: CapabilityUse[];
}

// Governance policies (spec ffef15bf): GLOBAL, operator-set deny rules and
// quotas the bus enforces pre-persistence while feature_governance is ON.
// CRUD works with the flag OFF (stage policies before enabling).
export type PolicySubjectKind = "agent" | "role" | "capability" | "star";
export type PolicyAction =
  | "message_create"
  | "broadcast"
  | "handoff_create"
  | "artifact_put";
export type PolicyLimitKind =
  | "deny"
  | "max_count"
  | "max_bytes"
  | "max_open_handoffs";
export type PolicyWindow = "1h" | "24h";

export interface GovernancePolicy {
  policy_id: string;
  subject_kind: PolicySubjectKind;
  subject_value: string | null;
  action: PolicyAction;
  limit_kind: PolicyLimitKind;
  limit_value: number | null;
  window: PolicyWindow | null;
  enabled: boolean;
  created_at: string;
}

// Named, versioned policy catalog (spec 80624c1a, migration 022): a single
// NAMED, append-only object that unifies audience (comm_scope) + governance in
// one versionable unit. The legacy governance_policies were migrated here as
// detached governance-only globals. This surface manages the header + the
// append-only version stream; enforcement only begins once an agent BINDS a
// policy. Operator-only.

// One subject-less governance rule inside a policy version (the binding is the
// subject). limit_value/window are present-but-null for kinds that do not use
// them (e.g. deny).
export interface PolicyRule {
  action: PolicyAction;
  limit_kind: PolicyLimitKind;
  limit_value?: number | null;
  window?: PolicyWindow | null;
}

// One immutable, published version: an audience (comm_scope envelope) plus a
// list of governance rules, stamped with a monotonically increasing number.
export interface PolicyVersion {
  policy_id: string;
  version: number;
  audience: CommScope | null;
  governance: PolicyRule[];
  published_at: string;
}

// A named policy HEADER. `latest_version` is 0 until a version is published.
// create/get/patch also return the full `versions` history (ascending); the
// list endpoint returns headers only (versions omitted).
export interface PolicyRecord {
  policy_id: string;
  name: string;
  description: string | null;
  created_at: string;
  updated_at: string | null;
  latest_version: number;
  versions?: PolicyVersion[];
}

// The 409 POLICY_IN_USE details payload: the agents that still bind the policy
// (delete is refused until they detach, or a pin would be orphaned).
export interface PolicyInUseDetails {
  policy_id: string;
  agents: string[];
}

// One GLOBAL binding reference on an agent (spec 80624c1a, FR10). `mode` picks
// which published version applies: "latest" follows the highest (pinned_version
// omitted), "pinned" freezes on an explicit pinned_version.
export interface AgentGlobalBinding {
  policy_id: string;
  mode: "latest" | "pinned";
  pinned_version?: number;
}

// An agent's CURRENT binding set, reshaped for the C2 editor (the inverse of the
// PUT contract, round-trip-stable): N ordered global references + at most one
// embedded inline policy (audience + governance), or `inline: null` when none.
export interface AgentBindings {
  agent_id: string;
  globals: AgentGlobalBinding[];
  inline: { audience: CommScope | null; governance: PolicyRule[] } | null;
}

// HITL approvals (spec 2948b2a2): operator-only queue behind the Approvals
// screen. Queue reads and decisions work with feature_hitl OFF — the flag
// gates only the interception of new actions.
export type ApprovalStatus = "pending" | "approved" | "rejected";

export interface ApprovalRow {
  approval_id: string;
  action: string;
  agent_id: string;
  policy_id: string;
  status: ApprovalStatus;
  created_at: string;
  decided_at: string | null;
  decided_by: string | null;
  // BR5: routing metadata only (byte size + who it addresses) — subject/body
  // never leave the approvals table through the queue.
  payload_meta: {
    kind: string;
    byte_size: number;
    target?: unknown;
    channel_id?: string | null;
    visibility?: string | null;
  };
  trace_id?: string;
  justification?: string;
}

// The detail endpoint is the ONE surface with the full serialized request.
export interface ApprovalDetail extends ApprovalRow {
  workspace_id: string;
  request_payload: {
    action?: string;
    kwargs?: Record<string, unknown>;
  } | null;
  executed_result?: unknown;
}

export interface ApprovalDecision {
  approval_id: string;
  status: "approved" | "rejected";
  decided_by: string;
  decided_at: string;
  // approve: the re-executed use case's response. reject: whether the
  // requester notification landed + the justification echoed back.
  executed_result?: unknown;
  notified?: boolean;
  justification?: string;
}

// POST /steering/messages reply: the NORMAL create_message result (BR9 — no
// delivery privilege), so a require_approval policy matching the operator
// surfaces here as status "pending_approval".
export interface SteeringResult {
  message_id?: string;
  recipients?: string[];
  delivered_count?: number;
  status?: string;
  approval_id?: string;
  warning?: string;
}

export interface PresetRow {
  preset_id: string;
  name: string;
  description: string | null;
  is_builtin: boolean;
  flags: PermissionFlags;
}

export interface PresetsPayload {
  items: PresetRow[];
  registry: PermissionFlags;
  descriptions: Record<string, string>;
}

export interface AgentRow {
  agent_id: string;
  role: string | null;
  capabilities: Record<string, unknown>;
  metadata: Record<string, unknown>;
  is_active: boolean;
  has_key: boolean;
  created_at: string;
  last_seen_at: string | null;
  permissions: PermissionFlags | null;
  preset_id: string | null;
  // Operator-only tag scoping (F1): agent labels + outbound audience
  // selector. The MCP discovery surface exposes tags but NEVER comm_scope.
  tags: TagMap | null;
  comm_scope: CommScope | null;
}

export interface MessageRow {
  message_id: string;
  workspace_id: string;
  channel_id: string | null;
  from_agent_id: string;
  created_at: string;
  subject: string | null;
  preview: string;
  body?: string; // full body, present only with include_body=true
  // Trajectory correlation (R-I1): non-null only when the feature stamped one.
  trace_id?: string | null;
  deliveries: {
    delivery_id: string;
    recipient_agent_id: string;
    status: string;
    created_at: string;
    delivered_at?: string | null;
    read_at?: string | null;
  }[];
}

export interface ConversationPeer {
  peer: string;
  count: number;
  last_at: string;
}

// One cosine-ranked hit from GET /messages/search (Frente 3). Lighter than
// MessageRow: no deliveries/body - just enough to show the ranked result.
export interface MessageSearchHit {
  message_id: string;
  score: number;
  from_agent_id: string;
  subject: string | null;
  created_at: string;
}

export interface MessageSearchResult {
  items: MessageSearchHit[];
  total: number;
  query: string;
  k: number;
}

export interface SessionRow {
  session_id: string;
  agent_id: string;
  workspace_id: string;
  status: string;
  started_at: string;
  last_heartbeat_at: string | null;
  presence: string;
}

export interface SettingItem {
  key: string;
  type: "int" | "bool" | "enum";
  group: string;
  description: string;
  value: number | boolean | string;
  default: number | boolean | string;
  min: number | null;
  max: number | null;
  choices: string[] | null;
  source: "cli/env" | "stored" | "default";
  editable: boolean;
  requires_restart: boolean;
}

// One memory entry in the browse/search list (GET /api/v1/memory) - the LEAN
// item shape: content_preview instead of content; score only when the declared
// search_mode is "semantic". Conditional fields follow the trace_id pattern
// (present only when non-null).
export interface MemoryItem {
  memory_id: string;
  title: string;
  topics: string[];
  author_agent_id: string;
  created_at: string;
  content_preview: string;
  score?: number;
  source_kind?: string;
  source_id?: string;
  supersedes?: string;
  superseded_by?: string;
}

// Full memory detail (GET /api/v1/memory/{id}) - content included.
export interface MemoryDetail {
  memory_id: string;
  workspace_id: string;
  author_agent_id: string;
  title: string;
  content: string;
  content_bytes: number;
  topics: string[];
  created_at: string;
  source_kind?: string;
  source_id?: string;
  supersedes?: string;
  superseded_by?: string;
  trace_id?: string;
}

export interface NexusEvent {
  event_id: number;
  workspace_id: string;
  stream: string;
  type: string;
  created_at: string;
  actor_agent_id: string | null;
  payload: unknown;
  visibility?: string | null; // NULL reads as "public"
  target?: unknown; // routing descriptor, present on the REST/SSE read model
  // Top-level echo of payload.trace_id on the REST/SSE read model (R-I1);
  // null when the event carries no trajectory.
  trace_id?: string | null;
}

// One workspace in the operator overview (GET /api/v1/workspaces). Identity +
// a 24h activity rollup + presence counts + a health block. root_realpath is
// null + path_redacted when the expose_workspace_path setting is off.
export interface WorkspaceListItem {
  workspace_id: string;
  display_name: string | null;
  root_realpath: string | null;
  path_redacted: boolean;
  created_at: string;
  last_seen_at: string | null;
  is_default: boolean;
  message_count: number;
  event_count: number;
  last_event_at: string | null;
  open_handoff_count: number;
  presence: { present: number; stale: number; offline: number };
  health: {
    open_handoffs_unclaimed: number;
    stale_sessions: number;
    parked_messages_deadletter: number;
    inbox_backlog_unread: number;
  };
}

export type AnalyticsWindow = "24h" | "7d" | "30d";

export interface AnalyticsBucket {
  bucket_start: string;
  total_count: number;
  total_tokens: number;
  by_agent: Record<string, { count: number; tokens: number }>;
}

export interface AnalyticsAgent {
  agent_id: string;
  count: number;
  tokens: number;
  avg_tokens: number;
  p95_tokens: number;
}

export interface WorkspaceAnalytics {
  window: AnalyticsWindow;
  bucket_seconds: number;
  truncated: boolean;
  scanned_messages: number;
  buckets: AnalyticsBucket[];
  summary: {
    total_messages: number;
    total_tokens: number;
    avg_tokens_per_msg: number;
    p95_tokens: number;
    peak_bucket_start: string | null;
  };
  agents: AnalyticsAgent[];
  others: { agent_count: number; count: number; tokens: number } | null;
}

// Coordination health (spec 7df9b1e0). The closed window enum of
// GET /api/v1/workspaces/{id}/health — distinct from AnalyticsWindow.
export type HealthWindow = "1h" | "24h" | "7d";

export interface HealthMetricBase {
  scope: "windowed" | "snapshot";
  status: "ok" | "warn";
}

// The full health payload. Thresholds are echoed by the server on EVERY
// reply — the UI renders them from here and never hardcodes a copy.
export interface WorkspaceHealth {
  workspace_id: string;
  window: HealthWindow;
  window_seconds: number;
  generated_at: string;
  status: "ok" | "warn";
  metrics: {
    message_volume: HealthMetricBase & { count: number };
    event_volume: HealthMetricBase & { count: number };
    unclaimed_handoffs: HealthMetricBase & {
      count: number;
      oldest_age_seconds: number | null;
    };
    handoff_completion: HealthMetricBase & {
      completed_pairs: number;
      avg_claim_to_complete_seconds: number | null;
      truncated: boolean;
    };
    handoff_rejections: HealthMetricBase & {
      created: number;
      rejected: number;
      rejection_rate: number | null;
      truncated: boolean;
    };
    inbox_backlog: HealthMetricBase & {
      total_unread: number;
      per_agent: { agent_id: string; unread: number }[];
      others_unread: number;
    };
    agent_presence: HealthMetricBase & {
      present: number;
      stale: number;
      offline: number;
    };
  };
  thresholds: {
    unclaimed_handoff_age_seconds: number;
    avg_claim_to_complete_seconds: number;
    rejection_rate: number;
    per_agent_unread: number;
    stale_agents: number;
  };
}

const KEY_STORAGE = "okto_nexus_operator_key";

export function getApiKey(): string | null {
  return sessionStorage.getItem(KEY_STORAGE);
}

export function setApiKey(key: string): void {
  sessionStorage.setItem(KEY_STORAGE, key);
}

export function clearApiKey(): void {
  sessionStorage.removeItem(KEY_STORAGE);
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details?: unknown,
  ) {
    super(message);
  }
}

async function call<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const key = getApiKey();
  const headers = new Headers(init.headers);
  if (key) headers.set("x-api-key", key);
  if (init.body) headers.set("content-type", "application/json");
  const response = await fetch(path, { ...init, headers });
  // Never assume JSON: a crashed handler or a proxy can answer plain text,
  // and "Unexpected token ..." hides the actual error from the operator.
  const raw = await response.text();
  let body: Envelope<T> | null = null;
  try {
    body = JSON.parse(raw) as Envelope<T>;
  } catch {
    throw new ApiError(
      response.status,
      "HTTP_" + response.status,
      raw.slice(0, 300) || response.statusText,
    );
  }
  if (!response.ok || !body.ok) {
    const error = body.error ?? {
      code: "HTTP_" + response.status,
      message: response.statusText,
    };
    throw new ApiError(response.status, error.code, error.message, error.details);
  }
  return body.data as T;
}

export interface NexusInfo {
  service: string;
  package_version: string;
  schema_version: number;
  trust_mode?: string;
  default_workspace_id?: string | null;
  // Live effective feature flags (mirrors MCP nexus_info.features): opt-in
  // surfaces self-gate on these (e.g. the I8 export button on features.feature_replay).
  features: Record<string, boolean>;
}

// Download an NDJSON event-log export (I8). Uses fetch (not a bare anchor) so the
// operator x-api-key rides along in key trust modes; on loopback local_open no
// key is needed. Streams to a Blob and saves via an object URL so the browser's
// Save dialog fires with the Content-Disposition filename.
async function downloadExport(path: string, filename: string): Promise<void> {
  const key = getApiKey();
  const headers = new Headers();
  if (key) headers.set("x-api-key", key);
  const response = await fetch(path, { headers });
  if (!response.ok) {
    const raw = await response.text();
    let message = raw.slice(0, 300) || response.statusText;
    try {
      message = (JSON.parse(raw) as Envelope<unknown>).error?.message ?? message;
    } catch {
      /* keep the raw text */
    }
    throw new ApiError(response.status, "HTTP_" + response.status, message);
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export const api = {
  graph: (workspace: string, windowHours = 24) =>
    call<GraphSnapshot>(
      `/api/v1/graph?workspace=${encodeURIComponent(workspace)}&window_hours=${windowHours}`,
    ),
  messages: (params: Record<string, string>) =>
    call<{ items: MessageRow[]; page: number; page_size: number; total: number }>(
      `/api/v1/messages?${new URLSearchParams(params)}`,
    ),
  conversationPeers: (agent: string) =>
    call<{ items: ConversationPeer[]; failed_count: number }>(
      `/api/v1/conversations/peers?agent=${encodeURIComponent(agent)}`,
    ),
  // Semantic search over message content. Throws ApiError with code
  // EMBEDDINGS_UNAVAILABLE (HTTP 503) when the embedding provider is off /
  // the [embeddings] extra is absent - the caller degrades gracefully.
  searchMessages: (q: string, k = 10) =>
    call<MessageSearchResult>(
      `/api/v1/messages/search?q=${encodeURIComponent(q)}&k=${k}`,
    ),
  handoffs: (workspace?: string) =>
    call<{ items: GraphHandoff[] }>(
      `/api/v1/handoffs${workspace ? `?workspace=${encodeURIComponent(workspace)}` : ""}`,
    ),
  sessions: (workspace?: string) =>
    call<{ items: SessionRow[] }>(
      `/api/v1/sessions${workspace ? `?workspace=${encodeURIComponent(workspace)}` : ""}`,
    ),
  // Paged event log with optional equality filters (workspace/stream/type/
  // agent/trace) + cursor (after/limit). Omitting them keeps the legacy shape.
  events: (params: Record<string, string>) =>
    call<{ items: NexusEvent[]; next_cursor: number }>(
      `/api/v1/events?${new URLSearchParams(params)}`,
    ),
  // Distinct event types present (scoped by workspace), for the type filter.
  eventTypes: (workspace?: string) =>
    call<{ items: string[] }>(
      `/api/v1/events/types${workspace ? `?workspace=${encodeURIComponent(workspace)}` : ""}`,
    ),
  // The rich workspace list (operator overview): every known workspace, not
  // just the ones with a live session.
  workspaces: () =>
    call<{ workspaces: WorkspaceListItem[] }>("/api/v1/workspaces"),
  // Message-distribution analytics for ONE workspace over a window.
  workspaceAnalytics: (workspaceId: string, window: AnalyticsWindow = "24h") =>
    call<WorkspaceAnalytics>(
      `/api/v1/workspaces/${encodeURIComponent(workspaceId)}/analytics?window=${window}`,
    ),
  // Coordination-health report for ONE workspace over a window (spec
  // 7df9b1e0). Operator surface, NOT gated by feature_health; an unknown
  // workspace is a 404 (unlike analytics' zeroed 200).
  workspaceHealth: (workspaceId: string, window: HealthWindow = "24h") =>
    call<WorkspaceHealth>(
      `/api/v1/workspaces/${encodeURIComponent(workspaceId)}/health?window=${window}`,
    ),
  // Workspace memory browse/search over ONE workspace (spec 8928b320 FR8).
  // The server DECLARES the effective ranking in search_mode
  // (semantic | lexical | recent); items are lean (content_preview).
  memories: (params: Record<string, string>) =>
    call<{ search_mode: string; count: number; items: MemoryItem[] }>(
      `/api/v1/memory?${new URLSearchParams(params)}`,
    ),
  memoryDetail: (workspace: string, memoryId: string) =>
    call<MemoryDetail>(
      `/api/v1/memory/${encodeURIComponent(memoryId)}?workspace=${encodeURIComponent(workspace)}`,
    ),
  // Operator curation: PHYSICAL delete, no event (BR9); operator-only.
  deleteMemory: (workspace: string, memoryId: string) =>
    call<{ memory_id: string; deleted: boolean }>(
      `/api/v1/memory/${encodeURIComponent(memoryId)}?workspace=${encodeURIComponent(workspace)}`,
      { method: "DELETE" },
    ),
  agents: () => call<{ items: AgentRow[] }>("/api/v1/agents"),
  createAgent: (body: {
    agent_id: string;
    role?: string;
    capabilities?: string[];
    metadata?: Record<string, unknown>;
    preset_id?: string;
    permissions?: PermissionFlags;
  }) =>
    call<AgentRow & { api_key: string }>("/api/v1/agents", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  updateAgent: (
    agentId: string,
    body: {
      is_active?: boolean;
      role?: string;
      // Already accepted + persisted by PATCH /agents/{id} (UpdateAgentBody);
      // the typed client just never exposed them, blocking an edit flow.
      capabilities?: string[];
      metadata?: Record<string, unknown>;
      preset_id?: string | null;
      permissions?: PermissionFlags | null;
      // Full-overwrite tag scoping fields (F1): explicit null resets.
      // Fail-closed: unregistered keys/values are rejected with 400/422.
      tags?: TagMap | null;
      comm_scope?: CommScope | null;
    },
  ) =>
    call<AgentRow>(`/api/v1/agents/${encodeURIComponent(agentId)}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  presets: () => call<PresetsPayload>("/api/v1/presets"),
  createPreset: (body: {
    name: string;
    description?: string;
    flags: PermissionFlags;
  }) =>
    call<PresetRow>("/api/v1/presets", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  updatePreset: (
    presetId: string,
    body: { name?: string; description?: string; flags?: PermissionFlags },
  ) =>
    call<PresetRow>(`/api/v1/presets/${encodeURIComponent(presetId)}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  deletePreset: (presetId: string) =>
    call<{ deleted: boolean }>(
      `/api/v1/presets/${encodeURIComponent(presetId)}`,
      { method: "DELETE" },
    ),
  // Central tag catalog (F1): the operator-managed, fail-closed registry
  // behind agent tags, audience selectors and the "tag" routing strategy.
  tags: () => call<{ items: TagKeyRow[] }>("/api/v1/tags"),
  createTagKey: (body: { key: string; description?: string }) =>
    call<{ key: string }>("/api/v1/tags", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  createTagValue: (key: string, body: { value: string; description?: string }) =>
    call<{ key: string; value: string }>(
      `/api/v1/tags/${encodeURIComponent(key)}/values`,
      { method: "POST", body: JSON.stringify(body) },
    ),
  // Both deletes 409 with code TAG_IN_USE + a details payload naming every
  // agent/selector still referencing the entry (never a cascade).
  deleteTagKey: (key: string) =>
    call<{ key: string; deleted: boolean }>(
      `/api/v1/tags/${encodeURIComponent(key)}`,
      { method: "DELETE" },
    ),
  deleteTagValue: (key: string, value: string) =>
    call<{ key: string; value: string; deleted: boolean }>(
      `/api/v1/tags/${encodeURIComponent(key)}/values/${encodeURIComponent(value)}`,
      { method: "DELETE" },
    ),
  // Central capability catalog (migration 014): the operator-managed,
  // fail-closed registry behind agent capabilities and "capability" targets.
  capabilities: () => call<{ items: CapabilityRow[] }>("/api/v1/capabilities"),
  createCapability: (body: { name: string; description?: string }) =>
    call<CapabilityRow>("/api/v1/capabilities", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  // Deletes 409 with code CAPABILITY_IN_USE + a details payload naming every
  // agent still owning the name (never a cascade).
  deleteCapability: (name: string) =>
    call<{ name: string; deleted: boolean }>(
      `/api/v1/capabilities/${encodeURIComponent(name)}`,
      { method: "DELETE" },
    ),
  // Governance policies (spec ffef15bf): the operator CRUD behind the
  // Policies screen. Enforcement failures surface to AGENTS as
  // POLICY_DENIED (403) / QUOTA_EXCEEDED (429); this surface only manages
  // the rules and works with feature_governance OFF.
  governancePolicies: () =>
    call<{ items: GovernancePolicy[] }>("/api/v1/governance/policies"),
  createGovernancePolicy: (body: {
    subject_kind: PolicySubjectKind;
    subject_value?: string | null;
    action: PolicyAction;
    limit_kind: PolicyLimitKind;
    limit_value?: number | null;
    window?: PolicyWindow | null;
    enabled?: boolean;
  }) =>
    call<GovernancePolicy>("/api/v1/governance/policies", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  updateGovernancePolicy: (
    policyId: string,
    body: {
      subject_kind?: PolicySubjectKind;
      subject_value?: string | null;
      action?: PolicyAction;
      limit_kind?: PolicyLimitKind;
      limit_value?: number | null;
      window?: PolicyWindow | null;
      enabled?: boolean;
    },
  ) =>
    call<GovernancePolicy>(
      `/api/v1/governance/policies/${encodeURIComponent(policyId)}`,
      { method: "PATCH", body: JSON.stringify(body) },
    ),
  deleteGovernancePolicy: (policyId: string) =>
    call<{ policy_id: string; deleted: boolean }>(
      `/api/v1/governance/policies/${encodeURIComponent(policyId)}`,
      { method: "DELETE" },
    ),
  // Named, versioned policy catalog (spec 80624c1a, migration 022): operator
  // CRUD over policy headers + append-only version publishing. Pure staging —
  // nothing is enforced until an agent binds a policy. The envelope is
  // unwrapped by call<T>; POST/GET/PATCH bring the version history, list()
  // returns headers only.
  policies: () => call<{ items: PolicyRecord[] }>("/api/v1/policies"),
  policy: (policyId: string) =>
    call<PolicyRecord>(`/api/v1/policies/${encodeURIComponent(policyId)}`),
  // Unknown fields -> 422 VALIDATION_ERROR; a duplicate name -> 422.
  createPolicy: (body: { name: string; description?: string }) =>
    call<PolicyRecord>("/api/v1/policies", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  updatePolicy: (
    policyId: string,
    body: { name?: string; description?: string },
  ) =>
    call<PolicyRecord>(`/api/v1/policies/${encodeURIComponent(policyId)}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  // 409 POLICY_IN_USE (details: {policy_id, agents}) while any agent binds it.
  deletePolicy: (policyId: string) =>
    call<{ deleted: boolean; policy_id: string }>(
      `/api/v1/policies/${encodeURIComponent(policyId)}`,
      { method: "DELETE" },
    ),
  // Publish the next immutable version (MAX+1, append-only). An empty body {}
  // is valid (a version with no restriction). `audience` is a comm_scope
  // envelope; `governance` is a list of subject-less rules.
  publishPolicyVersion: (
    policyId: string,
    body: { audience?: CommScope; governance?: PolicyRule[] },
  ) =>
    call<PolicyVersion>(
      `/api/v1/policies/${encodeURIComponent(policyId)}/versions`,
      { method: "POST", body: JSON.stringify(body) },
    ),
  policyVersions: (policyId: string) =>
    call<{ items: PolicyVersion[] }>(
      `/api/v1/policies/${encodeURIComponent(policyId)}/versions`,
    ),
  // FR10/FR12: read an agent's CURRENT binding set, reshaped into the same
  // {globals, inline} shape the PUT accepts (round-trip-stable) so the C2 editor
  // pre-populates without a blind overwrite. Operator-only. Unknown agent -> 404.
  agentPolicies: (agentId: string) =>
    call<AgentBindings>(
      `/api/v1/agents/${encodeURIComponent(agentId)}/policies`,
    ),
  // FR10 (contract api_101afea2): replace an agent's FULL binding set — N
  // global references (latest/pinned) + at most one inline policy. Operator-
  // only; consumed by the C2 agent-policy editor.
  setAgentPolicies: (
    agentId: string,
    body: {
      globals: {
        policy_id: string;
        mode: "latest" | "pinned";
        pinned_version?: number;
      }[];
      inline?: { audience?: CommScope; governance?: PolicyRule[] };
    },
  ) =>
    call<{ agent_id: string; effective_policies: string[] }>(
      `/api/v1/agents/${encodeURIComponent(agentId)}/policies`,
      { method: "PUT", body: JSON.stringify(body) },
    ),
  // HITL approvals (spec 2948b2a2): operator-only. status defaults to
  // "pending" server-side; pass "approved" / "rejected" / "all" to widen.
  approvals: (workspace: string, status?: string) =>
    call<{ items: ApprovalRow[] }>(
      `/api/v1/approvals?workspace=${encodeURIComponent(workspace)}${
        status ? `&status=${encodeURIComponent(status)}` : ""
      }`,
    ),
  approvalDetail: (approvalId: string) =>
    call<ApprovalDetail>(
      `/api/v1/approvals/${encodeURIComponent(approvalId)}`,
    ),
  // 409 CONFLICT when already decided (the first decision survives; its
  // details ride ApiError.details).
  decideApproval: (
    approvalId: string,
    decision: "approve" | "reject",
    justification?: string,
  ) =>
    call<ApprovalDecision>(
      `/api/v1/approvals/${encodeURIComponent(approvalId)}/decision`,
      {
        method: "POST",
        body: JSON.stringify(
          justification ? { decision, justification } : { decision },
        ),
      },
    ),
  // Direct message sent AS the reserved "operator" identity. Empty subject
  // is omitted so the server default ("Operator steering") applies.
  steerMessage: (
    workspace: string,
    toAgentId: string,
    subject: string,
    body: string,
  ) =>
    call<SteeringResult>("/api/v1/steering/messages", {
      method: "POST",
      body: JSON.stringify({
        workspace,
        to_agent_id: toAgentId,
        subject: subject || undefined,
        body,
      }),
    }),
  regenerateKey: (agentId: string) =>
    call<{ agent_id: string; api_key: string; rotated_at: string }>(
      `/api/v1/agents/${encodeURIComponent(agentId)}/regenerate-key`,
      { method: "POST" },
    ),
  deleteAgent: (agentId: string) =>
    call<{ deleted: boolean }>(`/api/v1/agents/${encodeURIComponent(agentId)}`, {
      method: "DELETE",
    }),
  closeSession: (sessionId: string) =>
    call<{ session_id: string; status: string }>(
      `/api/v1/sessions/${encodeURIComponent(sessionId)}/close`,
      { method: "POST" },
    ),
  cancelHandoff: (handoffId: string, workspace: string) =>
    call<{ handoff_id: string; status: string }>(
      `/api/v1/handoffs/${encodeURIComponent(handoffId)}/cancel?workspace=${encodeURIComponent(workspace)}`,
      { method: "POST" },
    ),
  // Verifier-only verdict on a VERIFYING handoff (R-I4, POST .../verify).
  // NOT operator-only: the backend applies the domain rule (dynamic verifier
  // + anti-self-verification), so a 403 means "not the eligible verifier".
  verifyHandoff: (
    handoffId: string,
    workspace: string,
    verdict: "pass" | "fail",
    feedback?: string,
  ) =>
    call<{ handoff_id: string; status: string; verified_by?: string }>(
      `/api/v1/workspaces/${encodeURIComponent(workspace)}/handoffs/${encodeURIComponent(handoffId)}/verify`,
      {
        method: "POST",
        body: JSON.stringify(feedback ? { verdict, feedback } : { verdict }),
      },
    ),
  prune: (dryRun: boolean) =>
    call<Record<string, unknown>>(`/api/v1/admin/prune?dry_run=${dryRun}`, {
      method: "POST",
    }),
  reset: (keepAgents: boolean) =>
    call<Record<string, unknown>>(
      `/api/v1/admin/reset?keep_agents=${keepAgents}`,
      { method: "POST" },
    ),
  settings: () => call<{ items: SettingItem[] }>("/api/v1/settings"),
  updateSettings: (changes: Record<string, unknown>) =>
    call<{ applied: Record<string, unknown> }>("/api/v1/settings", {
      method: "PATCH",
      body: JSON.stringify(changes),
    }),
  resetSettings: () =>
    call<{ cleared: string[] }>("/api/v1/settings/reset", { method: "POST" }),
  info: () => call<NexusInfo>("/api/v1/info"),
  // I8 replay/export: download the workspace event log as NDJSON. `params` may
  // carry stream/trace/since_event_id/until_event_id to narrow the recorte.
  exportEventLog: (workspaceId: string, params: Record<string, string> = {}) => {
    const qs = new URLSearchParams(params).toString();
    const path = `/api/v1/workspaces/${encodeURIComponent(workspaceId)}/events/export${
      qs ? `?${qs}` : ""
    }`;
    return downloadExport(path, `okto-nexus-events-${workspaceId.slice(0, 8)}.ndjson`);
  },
};

// MCP snippets per client format (mirrors the Pulse getMcpConfigJson).
export function mcpSnippet(format: string, apiKey: string): string {
  const url = `http://${location.hostname}:${location.port || "8202"}/mcp?api_key=${apiKey}`;
  switch (format) {
    case "claude-cli":
      return `claude mcp add -t http okto-nexus "${url}"`;
    case "codex":
      return `codex mcp add okto-nexus --url "${url}"`;
    case "vscode":
      return JSON.stringify(
        { servers: { "okto-nexus": { type: "http", url } } },
        null,
        2,
      );
    case "claude":
    case "cursor":
    case "windsurf":
      return JSON.stringify(
        { mcpServers: { "okto-nexus": { url } } },
        null,
        2,
      );
    default:
      return url;
  }
}

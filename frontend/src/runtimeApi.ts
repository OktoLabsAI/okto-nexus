import { ApiError, type ApprovalDetail } from "./api";
import type { SetupRequest, SetupTest, SetupBaseline } from './connectionConfiguration';

export interface ProjectPresetOverview {
  format_version: 1;
  origin: {id: string; revision: number};
  identity: {role: string; permissions: Record<string, unknown>; defaults_hash: string};
  configuration: Pick<import('./connectionConfiguration').ConnectionConfiguration,
    'runtime_enabled' | 'session_policy' | 'harness_settings' | 'tool_access'> & {
      authorization: {minutes:number|null; actions:number|null; no_expiry:boolean; unlimited_actions:boolean};
    };
  effects: string[];
}

export interface ConnectionCatalogItem {
  connect_id?: string | null;
  server_id: string; binding_id: string; executor_id: string; endpoint_id: string;
  workspace_binding_id: string; agent_id: string; workspace_id: string; adapter_id: string;
  binding_revision: number; realization_revision: number; endpoint_revision: number;
  activation_state: string; endpoint_enabled: number | boolean; agent_active: number | boolean;
  executor_revoked: number | boolean; execution_location: 'local' | 'remote';
  agent_label: string | null; workspace_label: string | null; host_label: string | null;
  needs_revalidation: true;
}
export interface ConnectionCatalogPage {
  version: 1; server_id: string; scope: Record<string, string>; revision: string; generated_at: string;
  items: ConnectionCatalogItem[]; total: number; total_is_exact: true;
  has_more: boolean; next_cursor: string | null; requires_canonical_revalidation: true;
  cursor_integrity: 'unsigned_scope_checked';
}
export interface PublicConnectionReceipt {
  version:1;connect_id:string;reservation_ref:string;revision:number;state:'bound';
  canonical_ref:Pick<ConnectionCatalogItem,'server_id'|'executor_id'|'binding_id'|'endpoint_id'|'agent_id'|'workspace_id'|'workspace_binding_id'>;
}
export interface SetupFinishResult {saved: boolean; agent_id?: string; agent_created?: boolean; binding?: BindingView; project_preset?: {id:string;revision:number};public_connection?:PublicConnectionReceipt}
export interface SetupReceipt {setup_run_id: string; request_hash: string; state: 'committed'; result: SetupFinishResult}
export interface SetupDraftView {
  baseline: SetupBaseline; runtime_policy: import('./api').RuntimePolicy;
  agent_creation_defaults: ProjectPresetOverview['identity'];
  native_decision_policy?: {value: boolean; source: string; editable: boolean; revision: string; can_initialize: boolean};
}

export interface ExecutorChoice {
  executor_id: string;
  kind: string;
  label: string | null;
  control_state: string;
}

export interface RuntimeChoice {
  harness_configuration?: HarnessConfiguration;
  provider_home_suggestion?: string | null;
  adapter_id: string;
  candidate_ref: string | null;
  label: string;
  technical_state: string;
  technical_reasons: string[];
  policy_reasons: string[];
  can_prepare: boolean;
  can_configure: boolean;
  can_bind: boolean;
  can_start: boolean;
  preparation: {realization_ref: string; realization_revision: number; workspace_binding_id: string} | null;
  binding: BindingView | null;
}

export interface HarnessConfiguration {
  schema_version: number; schema_revision: string; adapter_id: string; version: string | null;
  parameters: {name: string; label: string; type: string; native_parameter: string;
    core_applies: boolean; scope: string; default: unknown; default_source: string;
    values: string[]; availability: string}[];
  models: {id: string; provider: string | null; efforts: string[]; default_effort: string | null}[];
  constraints?: Record<string, string[]>;
  human_input: {core_bridge: string; native_methods: string[]; recipient_policy: string;
    recipient_routing_implemented: boolean; separate_from_tool_approval: boolean};
}

export interface BindingView {
  server_id?: string;
  binding_id: string; binding_revision: number; state: string; endpoint_id: string;
  executor_id: string; agent_id: string; workspace_id: string;
  workspace_binding_id: string; adapter_id: string; candidate_ref: string;
  inventory_revision: string; realization_ref: string; realization_revision: number;
}

export interface RevalidateBindingsResult {
  revalidated: number; already_current: number; installation_missing: number;
  installation_not_ready: number; inventory_unavailable: number;
  bindings: {binding_id: string; endpoint_id: string; adapter_id: string; outcome: string}[];
}

export interface HeldSuccession {
  id: number; executor_id: string; adapter_id: string; reason: string; policy: string;
  from_version: string | null; to_version: string | null; decided_at: string;
  agent_ids: string[]; can_accept: boolean;
}

export interface BindingProposal extends Omit<BindingView, "binding_revision" | "state"> {
  proposal_id: string; proposal_revision: number; expires_at: string;
  can_apply: boolean; required_approvals: string[];
  diff: {summary: string; approved_diff_hash: string; fields_changed: string[]};
}

export interface RuntimeOptions {
  agent_id: string;
  executor_id: string;
  inventory_revision: string;
  freshness: string;
  adapter_freshness: Record<string, 'FRESH' | 'STALE' | 'OFFLINE'>;
  observations: {adapter_id: string; state: 'PENDING' | 'PRESENT' | 'ABSENT' | 'FAILED';
    observation_age_ms: number | null; error_code: string | null}[];
  options: RuntimeChoice[];
  catalog: {runtimes: {adapter_id: string; display_name: string; support_status: string; implementation_platforms: string[]}[]};
  availability: {platform: string; availability?: {adapter_id: string; candidate_ref: string;
    display_name: string; version: string | null; architecture: string | null; source: string}[]};
}

export function localInstallationAvailable(item: RuntimeChoice): boolean {
  return !!item.candidate_ref && ['NOT_PROBED', 'PREPARATION_REQUIRED', 'READY_FOR_RUNTIME'].includes(item.technical_state) &&
    !item.technical_reasons.some(reason => reason.startsWith('containment_unavailable:') || reason.startsWith('containment_unverified:'));
}

export function localRuntimeAvailability(options: RuntimeOptions, adapterId: string): {available: boolean; label: string} {
  const runtime = options.catalog.runtimes.find(item => item.adapter_id === adapterId);
  if (!runtime || runtime.support_status !== 'managed_supported') return {available: false, label: 'Not supported'};
  if (!runtime.implementation_platforms.includes(options.availability.platform)) return {available: false, label: 'Not supported on this system'};
  const observation = options.observations.find(item => item.adapter_id === adapterId);
  if (observation?.state === 'PENDING') return {available: false, label: 'Checking installation…'};
  if (observation?.state === 'FAILED') return {available: false, label: 'Installation check unavailable · retrying'};
  if (options.adapter_freshness[adapterId] !== 'FRESH') return {available: false, label: 'Inventory unavailable'};
  const candidates = options.options.filter(item => item.adapter_id === adapterId && item.candidate_ref);
  if (!candidates.length) return {available: false, label: 'Not installed'};
  const usable = candidates.filter(localInstallationAvailable);
  if (!usable.length) return {available: false, label: 'Installation not supported'};
  if (usable.every(item => !item.can_configure)) return {available: false, label: 'Configuration unavailable'};
  return {available: true, label: usable.every(item => item.technical_state === 'NOT_PROBED') ? 'Installed · version check required' : 'Available'};
}

export interface LocalPreparationRequest {
  client_intent_id: string; local_consent_id: string; approved: true;
  agent_id: string; adapter_id: string; candidate_ref: string; inventory_revision: string;
  workspace_id: string | null; workspace_label: string; workspace_root: string;
  provider_home: string | null; secret_bindings: Record<string, string>;
}

export interface PreparationView {
  executor_id: string; agent_id: string; workspace_id: string;
  inventory_revision: string; realization_ref: string;
}

export type RuntimeIntent = "runtime.start" | "turn.submit" | "turn.steer" | "turn.interrupt" | "runtime.close";
export interface RuntimeRequest {
  client_intent_id: string; agent_id: string; intent: RuntimeIntent;
  binding_id: string; workspace_binding_id: string;
  session_id?: string; new_session?: boolean; text?: string;
  target?: {kind: "native_turn_id" | "current_run"; expected_turn_id: string | null};
}
export interface RuntimeScope {
  server_id: string; agent_id: string; executor_id: string; binding_id: string;
  workspace_id: string; workspace_binding_id: string; session_id: string;
  session_owner_generation?: number;
}
export interface RuntimeResolution {
  client_intent_id: string; operation_id: string; session_id: string; scope: RuntimeScope;
  resolution_revision: number; intent_hash: string; expires_at: string;
  can_submit: boolean; blockers: string[]; reuse: boolean;
}
export interface RuntimeOperation {
  operation_id: string; scope: RuntimeScope; action: string; admission_state: string;
  executor_stage: string | null; possible_effect: boolean; retry_safe: boolean;
  error: {code: string; message: string} | null; follow_up_operation_ids: string[];
  result?: {output_text: string; output_truncated: number} | null;
}
export interface RuntimeSession {
  scope: RuntimeScope; lifecycle_state: string; process_state: string; lease_state: string;
  control_available: boolean; durable_release_pending: boolean;
}

export interface InteractionScope extends RuntimeScope {
  session_owner_generation: number;
}

export interface SessionInteraction {
  scope: InteractionScope;
  stream_epoch: string | null;
  interaction_enabled?: boolean;
  interrupt_review_supported?: boolean;
  steer_review_supported?: boolean;
  next_turn: {supported: boolean; capability_revision: string | null; human_login_required: boolean};
}

export interface SessionCommandDescriptor {
  command_id: string;
  label: string;
  effect: string;
  source: 'nexus' | 'native';
  surface: 'dashboard' | 'native_terminal';
  handler: 'catalog' | 'session_status' | 'enqueue' | 'review_steer' | 'review_interrupt' | null;
  arguments: 'message'[];
  state: 'supported' | 'disabled_for_state' | 'denied_by_policy' | 'native_only' | 'unsupported' | 'unqualified';
  reason: string | null;
  requires_confirmation: boolean;
}

export interface SessionCommandCatalog {
  version: 1;
  scope: RuntimeScope;
  session_owner_generation: number;
  capability_revision: string;
  literal_text_supported: false;
  items: SessionCommandDescriptor[];
}

export interface SessionCommandStatus extends Pick<RuntimeSession, 'lifecycle_state' | 'lease_state' | 'control_available'> {
  scope: RuntimeScope;
  session_owner_generation: number;
}

export interface SessionInputReceipt {
  scope: RuntimeScope;
  session_owner_generation: number;
  input_id: string;
  enqueue_sequence: number;
  input_revision: number;
  queue_revision: number;
  status: 'QUEUED' | 'DISPATCHING' | 'ACCEPTED_NATIVE' | 'REFUSED_BEFORE_SEND' | 'DELIVERY_UNKNOWN' |
    'BLOCKED_AUTH' | 'BLOCKED_SESSION' | 'PAUSED' | 'EXPIRED' | 'CANCELLED';
  operation_id: string | null;
  possible_effect: boolean;
  reorientation?: boolean;
  steer_submitted?: boolean;
  steer_boundary?: 'awaiting_boundary' | 'applied' | 'discarded';
  steer_compound?: {
    interruption: 'submitted' | 'confirmed' | 'write_unknown';
    replacement: 'pending' | 'submitted' | 'not_sent' | 'write_unknown';
  };
}

export interface SessionInputQueueItem extends SessionInputReceipt {
  can_cancel: boolean;
  can_promote?: boolean;
}

export interface SessionInputQueueState {
  scope: RuntimeScope;
  session_owner_generation: number;
  queue_revision: number;
  paused: boolean;
}

export interface SessionInputQueuePage extends SessionInputQueueState {
  cancel_capability_revision: string | null;
  pause_capability_revision: string | null;
  items: SessionInputQueueItem[];
  next_cursor: string | null;
}

type NativeTurnTarget = {kind: 'native_turn'; turn_id: string};
type ObservedRunTarget = {kind: 'observed_run'; run_ref: string};
type ClaudeOperationTarget = {kind: 'claude_operation'; operation_id: string};

export interface SessionInterruptTarget {
  target: NativeTurnTarget | ObservedRunTarget | ClaudeOperationTarget;
  capability_revision: string;
  queue_revision: number;
}

export interface SessionInterruptAvailability {
  scope: RuntimeScope;
  session_owner_generation: number;
  control: SessionInterruptTarget | null;
}

export type SessionSteerTarget = Pick<SessionInterruptTarget, 'capability_revision' | 'queue_revision'> & {
  effect_revision: string;
} & (
  {effect: 'same_turn'; target: NativeTurnTarget} |
  {effect: 'next_boundary'; target: ObservedRunTarget} |
  {effect: 'interrupt_then_send'; target: ClaudeOperationTarget}
);

export interface QueuedSteerPreview {
  input_id: string;
  input_revision: number;
  text_preview: string;
  truncated: boolean;
}

export interface SessionSteerAvailability {
  scope: RuntimeScope;
  session_owner_generation: number;
  control: SessionSteerTarget | null;
  queued_input: QueuedSteerPreview | null;
}

export interface SessionInterruptReceipt extends RuntimeOperation {
  interrupt: {
    target_status: 'unconfirmed' | 'running' | 'interrupted' | 'finished';
    queue_paused: boolean;
    pending_count: number;
  };
}

export interface ConversationUpdate {
  update_id: string;
  message_id: string;
  sequence: number;
  role: 'user' | 'assistant';
  change: 'append' | 'replace';
  text: string | null;
  text_truncated: boolean;
  origin?: {kind: 'native_session'; session_id: string} |
    {kind: 'native_thread'; thread_id: string} |
    {kind: 'subagent'; session_id: string; parent_tool_use_id: string};
}

export interface SessionConversationPage {
  scope: InteractionScope;
  stream_epoch: string | null;
  updates: ConversationUpdate[];
  next_after_sequence: number;
  committed_contiguous: number;
  gap_pending: boolean;
  has_more: boolean;
  omitted_artifact_events: number;
  history_complete: boolean;
}

export interface SessionConversationPosition {
  version: 1;
  scope: InteractionScope;
  stream_epoch: string | null;
  committed_contiguous: number;
  gap_pending: boolean;
}
export interface RuntimeEventPage {
  scope: RuntimeScope; stream_epoch: string | null;
  events: {server_id: string; executor_id: string; session_id: string; stream_epoch: string;
    sequence: number; category: string; native_type: string | null; payload: unknown; received_at: string}[];
  count: number; next_after_sequence: number; committed_contiguous: number;
  gap_pending: boolean; has_more: boolean;
}

export interface NativeDecisionRequest {
  client_intent_id: string; approval_key: Record<string, string | number>;
  expected_revision: number; request_hash: string; cas_token: string;
  decision: "approve" | "deny"; response?: Record<string, unknown>;
}
export interface NativeDecisionView {
  decision_id: string; client_intent_id: string; approval_key: Record<string, string | number>;
  canonical_state: string; native_stage: string; native_operation_id: string;
  possible_effect: boolean; retry_safe: boolean; response_digest: string | null;
}

// R4 uses Bearer authentication and direct JSON, unlike the legacy /api envelope.
export interface DefinitiveSetupTestRejection {
  status:422; code:'VALIDATION_ERROR'; stage:'connection.test'; possible_effect:false;
  operation_id:null; retry_safe:false;
}
export class RuntimeManagementError extends ApiError {
  readonly definitiveTestRejection:DefinitiveSetupTestRejection|null;
  constructor(status:number, code:string, message:string, details:unknown, metadata:unknown) {
    super(status,code,message,details);
    const value=metadata as Record<string,unknown>|null;
    this.definitiveTestRejection=status===422&&code==='VALIDATION_ERROR'&&value?.stage==='connection.test'&&
      value.possible_effect===false&&value.operation_id===null&&value.retry_safe===false&&value.action===''?
      {status:422,code:'VALIDATION_ERROR',stage:'connection.test',possible_effect:false,operation_id:null,retry_safe:false}:null;
  }
}
function managementUrl(path: string) {
  return path.replace(/^\/v1\//, "/api/v1/runtime-management/");
}

async function read<T>(path: string, signal: AbortSignal | undefined, body?: unknown): Promise<T> {
  const headers = new Headers();
  headers.set("x-nexus-ui", "1");
  if (body !== undefined) headers.set("Content-Type", "application/json");
  const url = managementUrl(path);
  const response = await fetch(url, { headers, signal, cache: "no-store",
    method: body === undefined ? "GET" : "POST", body: body === undefined ? undefined : JSON.stringify(body) });
  const raw = await response.text();
  let value;
  try { value = JSON.parse(raw); }
  catch { throw new ApiError(response.status, `HTTP_${response.status}`, response.statusText || "Invalid server response"); }
  if (!response.ok) {
    const error = value.error ?? value;
    throw new RuntimeManagementError(response.status, error.code ?? `HTTP_${response.status}`, error.message ?? response.statusText, error.details,error);
  }
  return value as T;
}

function interactionTarget(scope: InteractionScope) {
  const {server_id, executor_id, binding_id, workspace_id, workspace_binding_id, agent_id, session_id} = scope;
  const exact = {server_id, executor_id, binding_id, workspace_id, workspace_binding_id, agent_id};
  return {
    path: `/v1/runtime/sessions/${encodeURIComponent(session_id)}`,
    query: new URLSearchParams({...exact, expected_session_generation: String(scope.session_owner_generation)}),
    scope: {...exact, session_id},
  };
}

function sessionInputReceipt(scope: InteractionScope, selector: 'input_id' | 'client_intent_id', id: string, signal: AbortSignal) {
  const target = interactionTarget(scope);
  target.query.set(selector, id);
  return read<SessionInputReceipt>(`${target.path}/inputs/receipt?${target.query}`, signal);
}

function steerConfirmation(scope: InteractionScope, reviewed: SessionSteerTarget) {
  const target = interactionTarget(scope);
  return {
    scope: target.scope, expected_session_generation: scope.session_owner_generation,
    capability_revision: reviewed.capability_revision, expected_queue_revision: reviewed.queue_revision,
    confirmed_effect_revision: reviewed.effect_revision, target: reviewed.target,
  };
}

function commandMutation(path: string, actionPath: string, command: 'send' | 'steer' | 'interrupt', revision?: string) {
  return revision
    ? {url: path + '/commands:execute', confirmation: {command, catalog_revision: revision, confirmed: true}}
    : {url: path + actionPath, confirmation: {}};
}

// Save the complete immutable request before sending it. Retrying an uncertain
// request uses the same identity/body; credentials never enter this record.
export function durableBindingRequest(key: string, payload: Record<string, unknown>): Record<string, unknown> {
  const storageKey = `okto-nexus:r4-binding:${key}`;
  const saved = sessionStorage.getItem(storageKey);
  if (saved) {
    const request = JSON.parse(saved) as Record<string, unknown>;
    const {client_intent_id, ...previous} = request;
    if (typeof client_intent_id !== "string" || JSON.stringify(previous) !== JSON.stringify(payload)) {
      throw new Error("The saved connection request differs. Review the selection before continuing.");
    }
    return request;
  }
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  const request = {client_intent_id: `ui_${Array.from(bytes, byte => byte.toString(16).padStart(2, "0")).join("")}`, ...payload};
  sessionStorage.setItem(storageKey, JSON.stringify(request));
  return request;
}

export function discardExpiredBindingReview(key: string): void {
  sessionStorage.removeItem(`okto-nexus:r4-binding:${key}`);
}

export function bindingRequestExists(key: string): boolean {
  return sessionStorage.getItem(`okto-nexus:r4-binding:${key}`) !== null;
}

export interface RecoveryPlan {
  executor_id: string; generation: number; agent_id?: string | null;
  sessions: {session_id: string; opening_operation_id: string; agent_id: string}[];
}

export const runtimeApi = {
  connectionCatalog: (filters: {workspace_id?: string; agent_id?: string; executor_id?: string; execution_location?: 'local' | 'remote'}, cursor: string | null, signal?: AbortSignal) => {
    const query = new URLSearchParams({...filters, limit: '100'});
    if (cursor) query.set('cursor', cursor);
    return read<ConnectionCatalogPage>(`/v1/connections/catalog?${query}`, signal);
  },
  setupDraft: (agent: string, signal?: AbortSignal) => read<SetupDraftView>(`/v1/connections/setup/${encodeURIComponent(agent)}?new_agent_draft=true`, signal),
  recoverSetup: (body: SetupRequest, signal?: AbortSignal) => read<SetupReceipt>('/v1/connections/setup:recover', signal, body),
  setupReceipt: (id: string, signal?: AbortSignal) => read<SetupReceipt>(`/v1/connections/setup-commits/${encodeURIComponent(id)}`, signal),
  connectionWorkspaces: (after: string | null, signal?: AbortSignal) => read<{
    items: {workspace_id: string; display_name: string | null}[]; has_more: boolean; next_workspace_id: string | null;
  }>(`/v1/connections/workspaces?limit=100${after ? '&after_workspace_id='+encodeURIComponent(after) : ''}`, signal),
  recoveryPlan: (agentId: string) => read<RecoveryPlan>(`/v1/runtime/recovery/plan?agent_id=${encodeURIComponent(agentId)}`, undefined),
  confirmStopped: (plan: RecoveryPlan) => read<{state: string; message: string}>(
    '/v1/runtime/recovery/confirm-stopped', undefined,
    {plan, confirmation: 'PREVIOUS_RUNTIME_PROCESSES_STOPPED'}),
  retryRecovery: (agentId: string) => read<{state: string; error_code: string | null; message: string}>(
    `/v1/runtime/recovery/retry?agent_id=${encodeURIComponent(agentId)}`, undefined, {}),
  projectPreset: (signal?: AbortSignal) => read<ProjectPresetOverview>('/v1/connections/project-preset', signal),
  setup: (agent: string, binding?: string, signal?: AbortSignal) => read<{baseline: SetupBaseline;
    project_preset?: {id: string; revision: number};
    runtime_policy: import('./api').RuntimePolicy;
    mcp_preset?: import('./api').MCPPreset;
    connections: (Pick<BindingView,'binding_id' | 'candidate_ref' | 'executor_id' | 'workspace_id' | 'adapter_id'> & {execution_location: 'local' | 'remote'})[];
    authorization?: {minutes: number | null; actions: number | null};
    folders?: {workspace_root: string; provider_home: string | null; secret_bindings: Record<string,string>};
    public_config?: {alias?: string; harness_settings?: Record<string,string>; nexus_tool_permission?: 'ask' | 'always_allow'};
    automatic_reply?: boolean}>(`/v1/connections/setup/${encodeURIComponent(agent)}${binding ? `?binding_id=${encodeURIComponent(binding)}` : ''}`, signal),
  workspacePaths: (workspaceId: string, executorId: string, signal?: AbortSignal) =>
    read<{workspace_id: string; executor_id: string; items: {path: string}[]}>(
      `/v1/workspaces/${encodeURIComponent(workspaceId)}/paths?executor_id=${encodeURIComponent(executorId)}`,
      signal,
    ),
  testSetup: (body: SetupRequest) => read<SetupTest>('/v1/connections/setup:test', undefined, body),
  setupTest: (id: string, signal?: AbortSignal) => read<SetupTest>(`/v1/connections/setup-tests/${encodeURIComponent(id)}`, signal),
  finishSetup: (body: SetupRequest) => read<SetupFinishResult>('/v1/connections/setup:finish', undefined, body),
  nativeInputs: (workspace: string, signal?: AbortSignal) => read<{items: ApprovalDetail[]}>(
    `/v1/runtime/input-requests${workspace && workspace !== "all" ? `?workspace_id=${encodeURIComponent(workspace)}` : ""}`, signal),
  decideNative: (body: NativeDecisionRequest) => read<NativeDecisionView>("/v1/runtime/approval-decisions", undefined, body),
  nativeDecision: (id: string, signal?: AbortSignal) => read<NativeDecisionView>(`/v1/runtime/approval-decisions/${encodeURIComponent(id)}`, signal),
  resolve: (body: RuntimeRequest) => read<RuntimeResolution>("/v1/runtime/intents:resolve", undefined, body),
  intent: (id: string, signal?: AbortSignal) => read<{resolution: RuntimeResolution; operation: RuntimeOperation | null}>(
    `/v1/runtime/intents/${encodeURIComponent(id)}`, signal),
  submit: (resolution: RuntimeResolution) => read<RuntimeOperation>("/v1/runtime/operations", undefined, {
    client_intent_id: resolution.client_intent_id, operation_id: resolution.operation_id,
    resolution_revision: resolution.resolution_revision, intent_hash: resolution.intent_hash,
  }),
  operation: (id: string, signal?: AbortSignal) => read<RuntimeOperation>(`/v1/runtime/operations/${encodeURIComponent(id)}`, signal),
  session: (id: string, signal?: AbortSignal, executorId?: string) => read<RuntimeSession>(`/v1/runtime/sessions/${encodeURIComponent(id)}${executorId ? `?executor_id=${encodeURIComponent(executorId)}` : ''}`, signal),
  sessionInteraction: (scope: InteractionScope, signal: AbortSignal) => {
    const target = interactionTarget(scope);
    return read<SessionInteraction>(`${target.path}/interaction?${target.query}`, signal);
  },
  sessionCommands: (scope: InteractionScope, signal: AbortSignal) => {
    const target = interactionTarget(scope);
    return read<SessionCommandCatalog>(`${target.path}/commands?${target.query}`, signal);
  },
  sessionCommandStatus: (scope: InteractionScope, revision: string, signal: AbortSignal) => {
    const target = interactionTarget(scope);
    return read<SessionCommandStatus>(`${target.path}/commands:execute`, signal, {
      scope: target.scope, expected_session_generation: scope.session_owner_generation,
      command: 'status', catalog_revision: revision,
    });
  },
  sessionConversation: (scope: InteractionScope, after: number, epoch: string | null, signal: AbortSignal) => {
    const target = interactionTarget(scope);
    target.query.set('after_sequence', String(after));
    if (epoch !== null) target.query.set('stream_epoch', epoch);
    return read<SessionConversationPage>(`${target.path}/conversation?${target.query}`, signal);
  },
  sessionConversationStream: (scope: InteractionScope) => {
    const target = interactionTarget(scope);
    return managementUrl(`${target.path}/conversation/stream?${target.query}`);
  },
  enqueueSessionInput: (scope: InteractionScope, intent: string, text: string, capability: string, signal: AbortSignal,
    catalogRevision?: string) => {
    const target = interactionTarget(scope);
    const command = commandMutation(target.path, '/inputs', 'send', catalogRevision);
    return read<SessionInputReceipt>(command.url, signal, {
      ...command.confirmation,
      scope: target.scope, expected_session_generation: scope.session_owner_generation,
      client_intent_id: intent, capability_revision: capability, mode: 'next_turn',
      content: [{type: 'text', text}],
    });
  },
  sessionInputReceipt: (scope: InteractionScope, intent: string, signal: AbortSignal) =>
    sessionInputReceipt(scope, 'client_intent_id', intent, signal),
  sessionInputReceiptById: (scope: InteractionScope, inputId: string, signal: AbortSignal) =>
    sessionInputReceipt(scope, 'input_id', inputId, signal),
  sessionSteerTarget: (scope: InteractionScope, inputId: string | null, signal: AbortSignal) => {
    const target = interactionTarget(scope);
    if (inputId !== null) target.query.set('input_id', inputId);
    return read<SessionSteerAvailability>(`${target.path}/steer?${target.query}`, signal);
  },
  steerSessionInput: (scope: InteractionScope, reviewed: SessionSteerTarget, intent: string, text: string, signal: AbortSignal,
    catalogRevision?: string) => {
    const command = commandMutation(interactionTarget(scope).path, '/steer', 'steer', catalogRevision);
    return read<SessionInputReceipt>(command.url, signal, {
      ...command.confirmation, ...steerConfirmation(scope, reviewed),
      client_intent_id: intent, content: [{type: 'text', text}],
    });
  },
  promoteSessionInput: (scope: InteractionScope, reviewed: SessionSteerTarget, input: QueuedSteerPreview, signal: AbortSignal) => {
    const target = interactionTarget(scope);
    return read<SessionInputReceipt>(`${target.path}/inputs/${encodeURIComponent(input.input_id)}/promote`, signal, {
      ...steerConfirmation(scope, reviewed), expected_input_revision: input.input_revision,
    });
  },
  sessionInputQueue: (scope: InteractionScope, cursor: string | null, signal: AbortSignal) => {
    const target = interactionTarget(scope);
    target.query.set('pending_only', 'true');
    if (cursor !== null) target.query.set('cursor', cursor);
    return read<SessionInputQueuePage>(`${target.path}/inputs?${target.query}`, signal);
  },
  cancelSessionInput: (scope: InteractionScope, item: SessionInputQueueItem, capability: string, signal: AbortSignal) => {
    const target = interactionTarget(scope);
    return read<SessionInputReceipt>(`${target.path}/inputs/${encodeURIComponent(item.input_id)}/cancel`, signal, {
      scope: target.scope, expected_session_generation: scope.session_owner_generation,
      capability_revision: capability, expected_queue_revision: item.queue_revision,
      expected_input_revision: item.input_revision,
    });
  },
  changeSessionQueuePause: (scope: InteractionScope, page: SessionInputQueuePage, paused: boolean, signal: AbortSignal) => {
    const target = interactionTarget(scope);
    return read<SessionInputQueueState>(`${target.path}/inputs/queue-state`, signal, {
      scope: target.scope, expected_session_generation: scope.session_owner_generation,
      expected_queue_revision: page.queue_revision, capability_revision: page.pause_capability_revision, paused,
    });
  },
  sessionInterruptTarget: (scope: InteractionScope, signal: AbortSignal) => {
    const target = interactionTarget(scope);
    return read<SessionInterruptAvailability>(`${target.path}/interrupt?${target.query}`, signal);
  },
  interruptSessionTurn: (scope: InteractionScope, reviewed: SessionInterruptTarget, intent: string, signal: AbortSignal,
    catalogRevision?: string) => {
    const target = interactionTarget(scope);
    const command = commandMutation(target.path, '/interrupt', 'interrupt', catalogRevision);
    return read<RuntimeOperation>(command.url, signal, {
      ...command.confirmation,
      scope: target.scope, expected_session_generation: scope.session_owner_generation, client_intent_id: intent,
      capability_revision: reviewed.capability_revision, expected_queue_revision: reviewed.queue_revision, target: reviewed.target,
    });
  },
  sessionInterruptReceipt: (scope: InteractionScope, intent: string, signal: AbortSignal) => {
    const target = interactionTarget(scope);
    target.query.set('client_intent_id', intent);
    return read<SessionInterruptReceipt>(`${target.path}/interrupt/receipt?${target.query}`, signal);
  },
  sessions: (agentId: string, binding: Pick<BindingView, 'executor_id' | 'binding_id'>, after: string, signal?: AbortSignal) => {
    const query = new URLSearchParams({agent_id: agentId, executor_id: binding.executor_id,
      binding_id: binding.binding_id, after_session_id: after, limit: "25"});
    return read<{sessions: RuntimeSession[]; has_more: boolean; next_after_session_id: string}>(`/v1/runtime/sessions?${query}`, signal);
  },
  events: (scope: RuntimeScope, after: number, epoch: string | null, signal?: AbortSignal) => {
    const query = new URLSearchParams({executor_id: scope.executor_id, after_sequence: String(after), limit: "100"});
    if (epoch !== null) query.set("stream_epoch", epoch);
    return read<RuntimeEventPage>(`/v1/runtime/sessions/${encodeURIComponent(scope.session_id)}/events?${query}`, signal);
  },
  checkLocalInstallation: (executorId: string, body: {agent_id: string; adapter_id: string;
      candidate_ref: string; inventory_revision: string; approved: true}) =>
    read<{version: string; runtime_authorized: false}>(
      `/v1/runtime/executors/${encodeURIComponent(executorId)}/installations:check`, undefined, body),
  prepareLocal: (executorId: string, body: LocalPreparationRequest) =>
    read<PreparationView>(`/v1/runtime/executors/${encodeURIComponent(executorId)}/realizations`, undefined, body),
  me: (signal?: AbortSignal) => read<{server_id: string; agent_id: string}>("/v1/connections/me", signal),
  refreshInventory: (executorId: string, clientIntentId: string, signal?: AbortSignal) =>
    read<{client_intent_id: string; refresh_id: string; executor_id: string; state: "PENDING" | "REQUESTED" | "UPDATED" | "OFFLINE"}>(
      `/v1/runtime/executors/${encodeURIComponent(executorId)}/inventory:refresh`, signal, {client_intent_id: clientIntentId}),
  // Operator recovery after a harness update. Accepts the current installation
  // for every binding that needs review: /api/v1/runtime-management/connections/bindings:revalidate.
  revalidateBindings: () => read<RevalidateBindingsResult>("/v1/connections/bindings:revalidate", undefined, {}),
  heldSuccessions: () => read<{items: HeldSuccession[]}>("/v1/connections/installation-successions?state=held", undefined),
  acceptSuccession: (id: number) => read<{decision: string}>(`/v1/connections/installation-successions/${id}:accept`, undefined, {}),
  prepareBinding: (body: Record<string, unknown>) => read<BindingProposal>("/v1/connections/bindings:prepare", undefined, body),
  applyBinding: (body: Record<string, unknown>) => read<BindingView>("/v1/connections/bindings:apply", undefined, body),
  binding: (id: string) => read<BindingView>(`/v1/connections/bindings/${encodeURIComponent(id)}`, undefined),
  async executors(agentId: string, signal: AbortSignal): Promise<ExecutorChoice[]> {
    const items: ExecutorChoice[] = [];
    let cursor: string | null = null;
    do {
      const query = new URLSearchParams({ limit: "100" });
      if (cursor) query.set("after_executor_id", cursor);
      const page: {items: ExecutorChoice[]; has_more: boolean; next_executor_id: string | null} =
        await read(`/v1/agents/${encodeURIComponent(agentId)}/executors?${query}`, signal);
      items.push(...page.items);
      if (!page.has_more) return items;
      if (!page.next_executor_id || (cursor !== null && page.next_executor_id <= cursor)) {
        throw new Error("Executor directory changed. Refresh the list.");
      }
      cursor = page.next_executor_id;
      if (items.length >= 1000) throw new Error("Executor directory exceeds the interactive limit.");
    } while (cursor);
    return items;
  },
  options(agentId: string, executorId: string, workspaceId: string, signal: AbortSignal) {
    const query = new URLSearchParams({ executor_id: executorId });
    if (workspaceId) query.set("workspace_id", workspaceId);
    return read<RuntimeOptions>(`/v1/agents/${encodeURIComponent(agentId)}/runtime-options?${query}`, signal);
  },
};

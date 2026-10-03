import { ApiError, getApiKey } from "./api";

export interface ExecutorChoice {
  executor_id: string;
  kind: string;
  label: string | null;
  control_state: string;
}

export interface RuntimeChoice {
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

export interface BindingView {
  binding_id: string; binding_revision: number; state: string; endpoint_id: string;
  executor_id: string; agent_id: string; workspace_id: string;
  workspace_binding_id: string; adapter_id: string; candidate_ref: string;
  inventory_revision: string; realization_ref: string; realization_revision: number;
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
  options: RuntimeChoice[];
  catalog: {runtimes: {adapter_id: string; display_name: string; support_status: string; implementation_platforms: string[]}[]};
  availability: {platform: string};
}

export function localInstallationAvailable(item: RuntimeChoice): boolean {
  return !!item.candidate_ref && ['NOT_PROBED', 'PREPARATION_REQUIRED', 'READY_FOR_RUNTIME'].includes(item.technical_state) &&
    !item.technical_reasons.some(reason => reason.startsWith('containment_unavailable:') || reason.startsWith('containment_unverified:'));
}

export function localRuntimeAvailability(options: RuntimeOptions, adapterId: string): {available: boolean; label: string} {
  const runtime = options.catalog.runtimes.find(item => item.adapter_id === adapterId);
  if (!runtime || runtime.support_status !== 'managed_supported') return {available: false, label: 'Not supported'};
  if (!runtime.implementation_platforms.includes(options.availability.platform)) return {available: false, label: 'Not supported on this system'};
  const candidates = options.options.filter(item => item.adapter_id === adapterId && item.candidate_ref);
  if (!candidates.length) return {available: false, label: 'Not installed'};
  if (options.freshness !== 'FRESH') return {available: false, label: 'Inventory unavailable'};
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
async function read<T>(path: string, signal: AbortSignal | undefined, body?: unknown): Promise<T> {
  const headers = new Headers();
  const key = getApiKey();
  if (key) headers.set("Authorization", `Bearer ${key}`);
  if (body !== undefined) headers.set("Content-Type", "application/json");
  const url = key ? path : path.replace(/^\/v1\//, "/api/v1/runtime-management/");
  const response = await fetch(url, { headers, signal, cache: "no-store",
    method: body === undefined ? "GET" : "POST", body: body === undefined ? undefined : JSON.stringify(body) });
  const raw = await response.text();
  let value;
  try { value = JSON.parse(raw); }
  catch { throw new ApiError(response.status, `HTTP_${response.status}`, response.statusText || "Invalid server response"); }
  if (!response.ok) {
    const error = value.error ?? value;
    throw new ApiError(response.status, error.code ?? `HTTP_${response.status}`, error.message ?? response.statusText);
  }
  return value as T;
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

export const runtimeApi = {
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
  session: (id: string, signal?: AbortSignal) => read<RuntimeSession>(`/v1/runtime/sessions/${encodeURIComponent(id)}`, signal),
  sessions: (agentId: string, binding: BindingView, after: string, signal?: AbortSignal) => {
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

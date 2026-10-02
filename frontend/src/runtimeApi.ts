import { ApiError, getApiKey } from "./api";

export interface ExecutorChoice {
  executor_id: string;
  kind: string;
  label: string | null;
  control_state: string;
}

export interface RuntimeChoice {
  adapter_id: string;
  candidate_ref: string | null;
  label: string;
  technical_state: string;
  technical_reasons: string[];
  policy_reasons: string[];
  can_prepare: boolean;
  can_bind: boolean;
  can_start: boolean;
  preparation: {realization_ref: string; realization_revision: number; workspace_binding_id: string} | null;
  binding: BindingView | null;
}

export interface BindingView {
  binding_id: string; binding_revision: number; state: string;
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

// R4 uses Bearer authentication and direct JSON, unlike the legacy /api envelope.
async function read<T>(path: string, signal: AbortSignal | undefined, body?: unknown): Promise<T> {
  const headers = new Headers();
  const key = getApiKey();
  if (key) headers.set("Authorization", `Bearer ${key}`);
  if (body !== undefined) headers.set("Content-Type", "application/json");
  const response = await fetch(path, { headers, signal, cache: "no-store",
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

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
}

export interface RuntimeOptions {
  agent_id: string;
  executor_id: string;
  inventory_revision: string;
  freshness: string;
  options: RuntimeChoice[];
}

// R4 uses Bearer authentication and direct JSON, unlike the legacy /api envelope.
async function read<T>(path: string, signal: AbortSignal): Promise<T> {
  const headers = new Headers();
  const key = getApiKey();
  if (key) headers.set("Authorization", `Bearer ${key}`);
  const response = await fetch(path, { headers, signal, cache: "no-store" });
  const raw = await response.text();
  let body;
  try { body = JSON.parse(raw); }
  catch { throw new ApiError(response.status, `HTTP_${response.status}`, response.statusText || "Invalid server response"); }
  if (!response.ok) {
    const error = body.error ?? body;
    throw new ApiError(response.status, error.code ?? `HTTP_${response.status}`, error.message ?? response.statusText);
  }
  return body as T;
}

export const runtimeApi = {
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

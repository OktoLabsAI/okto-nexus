// API client for the Nexus serve surfaces. Single source of truth for the
// envelope ({ok, data | error}) and for credential handling: the operator
// key lives in sessionStorage only (cleared when the tab closes) and is sent
// via x-api-key. Issued AGENT keys are never stored anywhere (br_ae340cae).

export interface Envelope<T> {
  ok: boolean;
  data?: T;
  error?: { code: string; message: string };
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

export interface GraphHandoff {
  handoff_id: string;
  workspace_id: string;
  status: string;
  created_at: string;
  from_agent_id: string | null;
  claimed_by: string | null;
  target: unknown;
}

export interface GraphSnapshot {
  workspace_id: string | null;
  generated_at: string;
  window_hours: number;
  nodes: GraphNode[];
  channels: { channel_id: string; workspace_id: string; name: string }[];
  edges: { messages: GraphEdge[]; handoffs: GraphHandoff[] };
}

// Permission flags: {group: {flag: bool | number | string[]}} - the Pulse
// grammar adapted to the Nexus communication domain (migration 011).
export type PermissionFlags = Record<
  string,
  Record<string, boolean | number | string[]>
>;

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
  deliveries: {
    delivery_id: string;
    recipient_agent_id: string;
    status: string;
    created_at: string;
  }[];
}

export interface ConversationPeer {
  peer: string;
  count: number;
  last_at: string;
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

export interface NexusEvent {
  event_id: number;
  workspace_id: string;
  stream: string;
  type: string;
  created_at: string;
  actor_agent_id: string | null;
  payload: unknown;
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
    throw new ApiError(response.status, error.code, error.message);
  }
  return body.data as T;
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
  handoffs: (workspace?: string) =>
    call<{ items: GraphHandoff[] }>(
      `/api/v1/handoffs${workspace ? `?workspace=${encodeURIComponent(workspace)}` : ""}`,
    ),
  sessions: (workspace?: string) =>
    call<{ items: SessionRow[] }>(
      `/api/v1/sessions${workspace ? `?workspace=${encodeURIComponent(workspace)}` : ""}`,
    ),
  events: (after = 0, limit = 100) =>
    call<{ items: NexusEvent[]; next_cursor: number }>(
      `/api/v1/events?after=${after}&limit=${limit}`,
    ),
  agents: () => call<{ items: AgentRow[] }>("/api/v1/agents"),
  createAgent: (body: {
    agent_id: string;
    role?: string;
    capabilities?: string[];
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
      preset_id?: string | null;
      permissions?: PermissionFlags | null;
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
  info: () =>
    call<{ service: string; package_version: string; schema_version: number }>(
      "/api/v1/info",
    ),
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

// Agents & API keys (spec S2 / FR5): the AgentsModal mirror. The freshly
// issued key renders ONCE in component state - it is never written to any
// storage, so closing the panel or reloading makes it unrecoverable
// (br_ae340cae). Pulse light/dark grammar, including the permissions
// surface (presets + per-agent flags, migration 011).

import { useEffect, useMemo, useState } from "react";
import {
  Check,
  Copy,
  Eye,
  FileJson,
  KeyRound,
  Pencil,
  Plus,
  Power,
  ShieldCheck,
  Terminal,
  Trash2,
} from "lucide-react";
import {
  api,
  mcpSnippet,
  type AgentRow,
  type PermissionFlags,
  type PresetRow,
  type PresetsPayload,
} from "../api";
import { useConfirm } from "../components/Confirm";
import {
  countEnabled,
  mergeFlags,
  PermissionFlagsEditor,
} from "../components/PermissionFlagsEditor";
import { PresetEditorModal } from "../components/PresetEditorModal";

// MCP consumers (the Pulse AgentsModal grammar): one button per client,
// clicking copies that client's ready-to-paste command/config.
const MCP_CONSUMERS = [
  { format: "claude-cli", label: "Claude Code (CLI)", file: "terminal", icon: "terminal" },
  { format: "claude", label: "Claude Desktop / Claude Code", file: "claude_desktop_config.json", icon: "json" },
  { format: "codex", label: "Codex (CLI)", file: "terminal", icon: "terminal" },
  { format: "cursor", label: "Cursor", file: ".cursor/mcp.json", icon: "json" },
  { format: "vscode", label: "VS Code (Copilot)", file: ".vscode/mcp.json", icon: "json" },
  { format: "windsurf", label: "Windsurf / Cline", file: "cline_mcp_settings.json", icon: "json" },
] as const;

const inputCls =
  "rounded-lg border border-surface-200 dark:border-surface-700 bg-white dark:bg-surface-800 px-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-accent-500/40";

export function AgentsView({ onChanged }: { onChanged: () => void }) {
  const { confirm, dialog } = useConfirm();
  const [tab, setTab] = useState<"agents" | "presets">("agents");
  const [agents, setAgents] = useState<AgentRow[]>([]);
  const [presets, setPresets] = useState<PresetsPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  // The ONE place a plaintext key ever lives in the UI (state only).
  const [freshKey, setFreshKey] = useState<{ agentId: string; key: string } | null>(
    null,
  );
  const [copied, setCopied] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [newAgent, setNewAgent] = useState({
    agent_id: "",
    role: "",
    capabilities: "",
    preset_id: "",
  });
  const [permsOpen, setPermsOpen] = useState<string | null>(null);
  const [permsSavedAt, setPermsSavedAt] = useState<string | null>(null);
  // Preset manager modal state: editing (PresetRow|null for new) +
  // optional clone template flags.
  const [editorOpen, setEditorOpen] = useState<{
    preset: PresetRow | null;
    initialFlags?: PermissionFlags;
  } | null>(null);

  const copySnippet = (format: string, key: string) => {
    navigator.clipboard.writeText(mcpSnippet(format, key));
    setCopied(format);
    window.setTimeout(
      () => setCopied((current) => (current === format ? null : current)),
      1600,
    );
  };

  const reload = () =>
    Promise.all([api.agents(), api.presets()])
      .then(([a, p]) => {
        setAgents(a.items);
        setPresets(p);
      })
      .catch((exc) => setError((exc as Error).message));

  useEffect(() => {
    reload();
  }, []);

  const presetName = useMemo(() => {
    const map = new Map<string, string>();
    for (const p of presets?.items ?? []) map.set(p.preset_id, p.name);
    return map;
  }, [presets]);

  const create = async () => {
    try {
      const created = await api.createAgent({
        agent_id: newAgent.agent_id.trim(),
        role: newAgent.role.trim() || undefined,
        capabilities: newAgent.capabilities
          ? newAgent.capabilities.split(",").map((c) => c.trim()).filter(Boolean)
          : undefined,
        preset_id: newAgent.preset_id || undefined,
      });
      setFreshKey({ agentId: created.agent_id, key: created.api_key });
      setCreating(false);
      setNewAgent({ agent_id: "", role: "", capabilities: "", preset_id: "" });
      setError(null);
      await reload();
      onChanged();
    } catch (exc) {
      setError((exc as Error).message);
    }
  };

  const applyPermissions = async (
    agentId: string,
    body: { preset_id?: string | null; permissions?: PermissionFlags | null },
  ) => {
    try {
      await api.updateAgent(agentId, body);
      setPermsSavedAt(agentId);
      window.setTimeout(
        () => setPermsSavedAt((c) => (c === agentId ? null : c)),
        1500,
      );
      setError(null);
      await reload();
    } catch (exc) {
      setError((exc as Error).message);
    }
  };

  const permChip = (agent: AgentRow) => {
    if (agent.permissions == null) {
      return ["Full access", "bg-surface-200 text-surface-600 dark:bg-surface-700 dark:text-surface-300"];
    }
    const label = agent.preset_id
      ? presetName.get(agent.preset_id) ?? "custom"
      : "custom";
    const { enabled, total } = countEnabled(
      mergeFlags(presets?.registry ?? {}, agent.permissions),
    );
    return [
      `${label} · ${enabled}/${total}`,
      enabled === total
        ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300"
        : "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
    ];
  };

  return (
    <div className="h-full overflow-y-auto p-6">
      {dialog}
      {editorOpen && presets && (
        <PresetEditorModal
          preset={editorOpen.preset}
          registry={presets.registry}
          descriptions={presets.descriptions}
          initialFlags={editorOpen.initialFlags}
          onClose={() => setEditorOpen(null)}
          onSaved={() => {
            reload();
          }}
        />
      )}
      <div className="max-w-3xl mx-auto panel overflow-hidden" data-testid="agents-view">
        <div className="flex items-center justify-between px-4 h-12 border-b border-surface-200/60 dark:border-surface-700/50">
          {/* Tabs (the Pulse AgentsModal header) */}
          <div className="flex items-center gap-1 text-sm">
            {(
              [
                ["agents", "Agents"],
                ["presets", "Permission presets"],
              ] as const
            ).map(([id, label]) => (
              <button
                key={id}
                onClick={() => setTab(id)}
                className={`px-3 py-1.5 rounded-lg font-display font-semibold text-sm transition-colors ${
                  tab === id
                    ? "bg-accent-100 text-accent-700 dark:bg-accent-900/60 dark:text-accent-200"
                    : "text-surface-500 hover:text-surface-800 dark:hover:text-surface-200"
                }`}
                data-testid={`tab-${id}`}
              >
                {label}
              </button>
            ))}
          </div>
          {tab === "agents" ? (
            <button className="btn btn-primary" onClick={() => setCreating((v) => !v)}>
              <Plus size={14} /> New agent
            </button>
          ) : (
            <button
              className="btn btn-primary"
              onClick={() => setEditorOpen({ preset: null })}
              data-testid="new-preset"
            >
              <Plus size={14} /> New preset
            </button>
          )}
        </div>

        {error && <p className="px-4 py-2 text-xs text-red-500">{error}</p>}

        {/* ------------------------------------------------------------ */}
        {/* Presets tab                                                   */}
        {/* ------------------------------------------------------------ */}
        {tab === "presets" && (
          <div className="p-4 space-y-4" data-testid="presets-panel">
            {(["builtin", "custom"] as const).map((section) => {
              const items = (presets?.items ?? []).filter((p) =>
                section === "builtin" ? p.is_builtin : !p.is_builtin,
              );
              return (
                <div key={section}>
                  <h3 className="text-xs font-medium uppercase tracking-wider text-surface-400 dark:text-surface-500 mb-2">
                    {section === "builtin" ? "Built-in" : "Custom"}
                  </h3>
                  {items.length === 0 && section === "custom" && (
                    <p className="text-xs text-surface-400 dark:text-surface-500">
                      No custom presets yet — create one or clone a built-in.
                    </p>
                  )}
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                    {items.map((p) => {
                      const counts = countEnabled(
                        mergeFlags(presets?.registry ?? {}, p.flags),
                      );
                      return (
                        <div
                          key={p.preset_id}
                          className={`rounded-xl border p-3 ${
                            p.is_builtin
                              ? "border-surface-200 dark:border-surface-700"
                              : "border-accent-200 dark:border-accent-800/50 bg-accent-50/30 dark:bg-accent-900/10"
                          }`}
                          data-testid={`preset-${p.preset_id}`}
                        >
                          <div className="flex items-center gap-2">
                            <span className="font-medium text-sm text-surface-900 dark:text-surface-100">
                              {p.name}
                            </span>
                            <span
                              className={`chip text-[10px] ${
                                counts.enabled === counts.total
                                  ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300"
                                  : "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300"
                              }`}
                            >
                              {counts.enabled}/{counts.total}
                            </span>
                            <div className="ml-auto flex gap-1">
                              <button
                                className="p-1.5 text-surface-400 hover:text-surface-600 dark:hover:text-surface-300 hover:bg-surface-100 dark:hover:bg-white/10 rounded-lg"
                                title={p.is_builtin ? "View" : "Edit"}
                                onClick={() => setEditorOpen({ preset: p })}
                              >
                                {p.is_builtin ? <Eye size={14} /> : <Pencil size={14} />}
                              </button>
                              <button
                                className="p-1.5 text-surface-400 hover:text-surface-600 dark:hover:text-surface-300 hover:bg-surface-100 dark:hover:bg-white/10 rounded-lg"
                                title="Clone"
                                onClick={() =>
                                  setEditorOpen({
                                    preset: null,
                                    initialFlags: mergeFlags(
                                      presets?.registry ?? {},
                                      p.flags,
                                    ),
                                  })
                                }
                              >
                                <Copy size={14} />
                              </button>
                              {!p.is_builtin && (
                                <button
                                  className="p-1.5 text-red-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg"
                                  title="Delete"
                                  onClick={() =>
                                    confirm({
                                      title: "Delete preset?",
                                      body: (
                                        <span>
                                          <b>{p.name}</b> will be removed. Agents using
                                          it keep their current flags; only the preset
                                          reference is cleared.
                                        </span>
                                      ),
                                      onConfirm: async () => {
                                        await api.deletePreset(p.preset_id);
                                        await reload();
                                      },
                                    })
                                  }
                                >
                                  <Trash2 size={14} />
                                </button>
                              )}
                            </div>
                          </div>
                          {p.description && (
                            <p className="text-xs text-surface-500 dark:text-surface-400 mt-1">
                              {p.description}
                            </p>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* ------------------------------------------------------------ */}
        {/* Agents tab                                                    */}
        {/* ------------------------------------------------------------ */}
        {tab === "agents" && creating && (
          <div className="px-4 py-3 border-b border-surface-200/60 dark:border-surface-700/50 grid grid-cols-2 gap-2 text-xs">
            <input
              placeholder="agent_id (e.g. researcher)"
              value={newAgent.agent_id}
              onChange={(e) => setNewAgent({ ...newAgent, agent_id: e.target.value })}
              className={`${inputCls} font-mono`}
              data-testid="new-agent-id"
            />
            <input
              placeholder="role (optional)"
              value={newAgent.role}
              onChange={(e) => setNewAgent({ ...newAgent, role: e.target.value })}
              className={inputCls}
            />
            <input
              placeholder="capabilities, comma-separated"
              value={newAgent.capabilities}
              onChange={(e) =>
                setNewAgent({ ...newAgent, capabilities: e.target.value })
              }
              className={inputCls}
            />
            <div className="flex gap-2">
              <select
                value={newAgent.preset_id}
                onChange={(e) =>
                  setNewAgent({ ...newAgent, preset_id: e.target.value })
                }
                className={`${inputCls} flex-1`}
                title="Permission preset applied at creation (flags are copied; customize later per agent)."
                data-testid="new-agent-preset"
              >
                <option value="">Full access (default)</option>
                {(presets?.items ?? []).map((p) => (
                  <option key={p.preset_id} value={p.preset_id}>
                    {p.name}
                    {p.is_builtin ? " (built-in)" : ""}
                  </option>
                ))}
              </select>
              <button
                className="btn btn-primary"
                onClick={create}
                disabled={!newAgent.agent_id.trim()}
                data-testid="create-agent"
              >
                Create
              </button>
            </div>
          </div>
        )}

        {tab === "agents" && (
          <div className="divide-y divide-surface-100 dark:divide-surface-700/50 text-sm">
            {agents.map((agent) => {
              const [chipLabel, chipCls] = permChip(agent);
              return (
                <div key={agent.agent_id} className="px-4 py-3" data-testid={`agent-${agent.agent_id}`}>
                  <div className="flex items-center gap-3">
                    <span
                      className={`w-2 h-2 rounded-full ${
                        agent.is_active ? "bg-accent-500" : "bg-surface-400 dark:bg-surface-600"
                      }`}
                    />
                    <div>
                      <div className="font-medium text-surface-900 dark:text-surface-100">
                        {agent.agent_id}
                      </div>
                      <div className="text-xs text-surface-500 dark:text-surface-400">
                        {agent.role ?? "—"} · {agent.has_key ? "key issued" : "no key"} ·
                        last seen {agent.last_seen_at ?? "never"}
                      </div>
                    </div>
                    <div className="ml-auto flex items-center gap-2">
                      <span className={`chip ${chipCls}`} title="Effective permissions">
                        {chipLabel}
                      </span>
                      <span
                        className={`chip ${
                          agent.is_active
                            ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300"
                            : "bg-surface-200 text-surface-600 dark:bg-surface-700 dark:text-surface-300"
                        }`}
                      >
                        {agent.is_active ? "active" : "inactive"}
                      </span>
                    </div>
                  </div>

                  {freshKey?.agentId === agent.agent_id && (
                    <div className="mt-3 space-y-2 animate-slide-up" data-testid="fresh-key-panel">
                      <div className="bg-surface-100 dark:bg-surface-900 border border-accent-300 dark:border-accent-700/50 rounded-lg p-2 flex items-center gap-2">
                        <code
                          className="text-accent-700 dark:text-accent-300 text-xs break-all flex-1"
                          data-testid="fresh-key"
                        >
                          {freshKey.key}
                        </code>
                        <button
                          className="btn btn-primary !py-1"
                          onClick={() => navigator.clipboard.writeText(freshKey.key)}
                        >
                          <Copy size={12} /> Copy
                        </button>
                      </div>
                      <p className="text-[11px] text-amber-600 dark:text-amber-300/80">
                        ⚠ This key will not be shown again. Store it now — closing this
                        panel makes it unrecoverable (regenerating issues a new one).
                      </p>
                      <div>
                        <div className="text-[11px] font-medium uppercase tracking-wide text-surface-500 dark:text-surface-400 mb-1">
                          MCP configuration
                        </div>
                        <div className="grid grid-cols-2 lg:grid-cols-3 gap-2">
                          {MCP_CONSUMERS.map(({ format, label, file, icon }) => (
                            <button
                              key={format}
                              onClick={() => copySnippet(format, freshKey.key)}
                              className="flex items-center gap-2 px-3 py-2 text-xs rounded-lg text-left
                                bg-white dark:bg-surface-900 border border-surface-200 dark:border-surface-700
                                hover:bg-accent-50 dark:hover:bg-accent-900/20
                                text-surface-700 dark:text-surface-300 transition-colors"
                              title={icon === "terminal" ? "Terminal command" : file}
                              data-testid={`mcp-copy-${format}`}
                            >
                              {copied === format ? (
                                <Check size={14} className="shrink-0 text-emerald-500" />
                              ) : icon === "terminal" ? (
                                <Terminal size={14} className="shrink-0 text-surface-400 dark:text-surface-500" />
                              ) : (
                                <FileJson size={14} className="shrink-0 text-surface-400 dark:text-surface-500" />
                              )}
                              <span className="truncate">
                                {copied === format ? "Copied!" : label}
                              </span>
                            </button>
                          ))}
                        </div>
                      </div>
                      <button className="btn btn-secondary" onClick={() => setFreshKey(null)}>
                        Close key panel
                      </button>
                    </div>
                  )}

                  {/* Per-agent permissions (the Pulse expanded-card grammar):
                      preset dropdown resets flags; individual toggles PATCH
                      immediately. */}
                  {permsOpen === agent.agent_id && presets && (
                    <div
                      className="mt-3 space-y-3 rounded-xl border border-surface-200 dark:border-surface-700 p-3 animate-slide-up"
                      data-testid={`perms-panel-${agent.agent_id}`}
                    >
                      <div className="flex items-center gap-2">
                        <label className="text-xs font-medium text-surface-600 dark:text-surface-300">
                          Preset
                        </label>
                        <select
                          value={agent.preset_id ?? ""}
                          onChange={(e) =>
                            applyPermissions(agent.agent_id, {
                              preset_id: e.target.value || null,
                            })
                          }
                          className={`${inputCls} flex-1 max-w-[260px]`}
                          title="Selecting a preset RESETS the flags below from it; clearing it restores full access."
                        >
                          <option value="">Full access (no preset)</option>
                          {presets.items.map((p) => (
                            <option key={p.preset_id} value={p.preset_id}>
                              {p.name}
                              {p.is_builtin ? " (built-in)" : ""}
                            </option>
                          ))}
                        </select>
                        {permsSavedAt === agent.agent_id && (
                          <span className="chip bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300">
                            saved
                          </span>
                        )}
                      </div>
                      <PermissionFlagsEditor
                        flags={mergeFlags(presets.registry, agent.permissions)}
                        registry={presets.registry}
                        descriptions={presets.descriptions}
                        onChange={(flags) =>
                          applyPermissions(agent.agent_id, { permissions: flags })
                        }
                      />
                      <p className="text-[10px] text-surface-400 dark:text-surface-500">
                        Changes apply immediately to every transport (MCP HTTP and
                        stdio). “Full access” agents have no stored flags.
                      </p>
                    </div>
                  )}

                  <div className="mt-2 flex gap-2 text-xs">
                    <button
                      className="btn btn-secondary !py-1 !text-xs"
                      data-testid={`perms-${agent.agent_id}`}
                      onClick={() =>
                        setPermsOpen((open) =>
                          open === agent.agent_id ? null : agent.agent_id,
                        )
                      }
                    >
                      <ShieldCheck size={12} />{" "}
                      {permsOpen === agent.agent_id ? "Close permissions" : "Permissions…"}
                    </button>
                    <button
                      className="btn btn-secondary !py-1 !text-xs"
                      data-testid={`regenerate-${agent.agent_id}`}
                      onClick={() =>
                        confirm({
                          title: "Regenerate key?",
                          body: (
                            <span>
                              The current key of <b>{agent.agent_id}</b> stops working
                              immediately; the new one is shown a single time.
                            </span>
                          ),
                          onConfirm: async () => {
                            const rotated = await api.regenerateKey(agent.agent_id);
                            setFreshKey({ agentId: agent.agent_id, key: rotated.api_key });
                            await reload();
                            onChanged();
                          },
                        })
                      }
                    >
                      <KeyRound size={12} /> Regenerate key…
                    </button>
                    <button
                      className="btn btn-secondary !py-1 !text-xs"
                      onClick={async () => {
                        await api.updateAgent(agent.agent_id, {
                          is_active: !agent.is_active,
                        });
                        await reload();
                        onChanged();
                      }}
                    >
                      <Power size={12} /> {agent.is_active ? "Deactivate" : "Activate"}
                    </button>
                    <button
                      className="btn btn-secondary !py-1 !text-xs text-red-500 ml-auto"
                      onClick={() =>
                        confirm({
                          title: "Delete agent?",
                          body: (
                            <span>
                              <b>{agent.agent_id}</b> will be removed permanently
                              (deactivation is the reversible path).
                            </span>
                          ),
                          onConfirm: async () => {
                            await api.deleteAgent(agent.agent_id);
                            await reload();
                            onChanged();
                          },
                        })
                      }
                    >
                      <Trash2 size={12} /> Delete…
                    </button>
                  </div>
                </div>
              );
            })}
            {agents.length === 0 && (
              <div className="px-4 py-6 text-xs text-surface-400 dark:text-surface-500">
                No agents — create the first one above.
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

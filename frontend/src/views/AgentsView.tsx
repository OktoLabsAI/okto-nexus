// Agents & API keys (spec S2 / FR5): the AgentsModal mirror. The freshly
// issued key renders ONCE in component state - it is never written to any
// storage, so closing the panel or reloading makes it unrecoverable
// (br_ae340cae); recovery means regenerating. Pulse light/dark grammar.

import { useEffect, useState } from "react";
import { Copy, KeyRound, Plus, Power, Trash2 } from "lucide-react";
import { api, mcpSnippet, type AgentRow } from "../api";
import { useConfirm } from "../components/Confirm";

const FORMATS = [
  ["claude-code", "Claude Code"],
  ["claude-desktop", "Claude Desktop"],
  ["cursor", "Cursor"],
  ["vscode", "VS Code"],
  ["windsurf", "Windsurf"],
  ["okto-cli", "Okto CLI"],
] as const;

const inputCls =
  "rounded-lg border border-surface-200 dark:border-surface-700 bg-white dark:bg-surface-800 px-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-accent-500/40";

export function AgentsView({ onChanged }: { onChanged: () => void }) {
  const { confirm, dialog } = useConfirm();
  const [agents, setAgents] = useState<AgentRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  // The ONE place a plaintext key ever lives in the UI (state only).
  const [freshKey, setFreshKey] = useState<{ agentId: string; key: string } | null>(
    null,
  );
  const [format, setFormat] = useState<string>("claude-code");
  const [creating, setCreating] = useState(false);
  const [newAgent, setNewAgent] = useState({ agent_id: "", role: "", capabilities: "" });

  const reload = () =>
    api
      .agents()
      .then(({ items }) => setAgents(items))
      .catch((exc) => setError((exc as Error).message));

  useEffect(() => {
    reload();
  }, []);

  const create = async () => {
    try {
      const created = await api.createAgent({
        agent_id: newAgent.agent_id.trim(),
        role: newAgent.role.trim() || undefined,
        capabilities: newAgent.capabilities
          ? newAgent.capabilities.split(",").map((c) => c.trim()).filter(Boolean)
          : undefined,
      });
      setFreshKey({ agentId: created.agent_id, key: created.api_key });
      setCreating(false);
      setNewAgent({ agent_id: "", role: "", capabilities: "" });
      setError(null);
      await reload();
      onChanged();
    } catch (exc) {
      setError((exc as Error).message);
    }
  };

  return (
    <div className="h-full overflow-y-auto p-6">
      {dialog}
      <div className="max-w-3xl mx-auto panel overflow-hidden" data-testid="agents-view">
        <div className="flex items-center justify-between px-4 h-12 border-b border-surface-200/60 dark:border-surface-700/50">
          <span className="font-display font-semibold text-sm">Agents &amp; API keys</span>
          <button className="btn btn-primary" onClick={() => setCreating((v) => !v)}>
            <Plus size={14} /> New agent
          </button>
        </div>

        {error && <p className="px-4 py-2 text-xs text-red-500">{error}</p>}

        {creating && (
          <div className="px-4 py-3 border-b border-surface-200/60 dark:border-surface-700/50 grid grid-cols-3 gap-2 text-xs">
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
            <div className="flex gap-2">
              <input
                placeholder="capabilities, comma-separated"
                value={newAgent.capabilities}
                onChange={(e) =>
                  setNewAgent({ ...newAgent, capabilities: e.target.value })
                }
                className={`${inputCls} flex-1`}
              />
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

        <div className="divide-y divide-surface-100 dark:divide-surface-700/50 text-sm">
          {agents.map((agent) => (
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
                <span
                  className={`ml-auto chip ${
                    agent.is_active
                      ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300"
                      : "bg-surface-200 text-surface-600 dark:bg-surface-700 dark:text-surface-300"
                  }`}
                >
                  {agent.is_active ? "active" : "inactive"}
                </span>
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
                    <div className="flex gap-2 text-[11px] text-surface-500 dark:text-surface-400 mb-1">
                      {FORMATS.map(([id, label]) => (
                        <button
                          key={id}
                          onClick={() => setFormat(id)}
                          className={
                            id === format
                              ? "text-accent-600 dark:text-accent-400 border-b border-accent-500"
                              : "hover:text-surface-800 dark:hover:text-surface-200"
                          }
                        >
                          {label}
                        </button>
                      ))}
                    </div>
                    <pre className="bg-surface-100 dark:bg-surface-900 border border-surface-200 dark:border-surface-700 rounded-lg p-2 text-[11px] text-surface-600 dark:text-surface-300 overflow-x-auto">
                      {mcpSnippet(format, freshKey.key)}
                    </pre>
                  </div>
                  <button className="btn btn-secondary" onClick={() => setFreshKey(null)}>
                    Close key panel
                  </button>
                </div>
              )}

              <div className="mt-2 flex gap-2 text-xs">
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
          ))}
          {agents.length === 0 && (
            <div className="px-4 py-6 text-xs text-surface-400 dark:text-surface-500">
              No agents — create the first one above.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

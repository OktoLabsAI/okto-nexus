// Steer modal (spec 2948b2a2 FR9, sm_6a7279dd): the operator sends a DIRECT
// message AS the reserved "operator" identity via POST /steering/messages.
// No delivery privilege (BR9): the send goes through the same permission,
// governance and even HITL gates as any agent's message — a require_approval
// policy matching the operator intercepts steering too (surfaced below).

import { useEffect, useState } from "react";
import { Target, X } from "lucide-react";
import {
  api,
  type AgentRow,
  type SteeringResult,
  type WorkspaceListItem,
} from "../api";

const inputCls =
  "rounded-lg border border-surface-200 dark:border-surface-700 bg-white dark:bg-surface-800 px-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-accent-500/40";

export function SteerModal({
  agent,
  workspace,
  onClose,
}: {
  agent: AgentRow;
  // The App scope; "all" forces an explicit workspace pick below.
  workspace: string;
  onClose: () => void;
}) {
  const [workspaces, setWorkspaces] = useState<WorkspaceListItem[]>([]);
  const [target, setTarget] = useState(workspace !== "all" ? workspace : "");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [sending, setSending] = useState(false);
  const [result, setResult] = useState<SteeringResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .workspaces()
      .then(({ workspaces: items }) => {
        setWorkspaces(items);
        // A single known workspace needs no picking ceremony.
        setTarget((current) =>
          current === "" && items.length === 1 ? items[0].workspace_id : current,
        );
      })
      .catch(() => undefined);
  }, []);

  const send = async () => {
    setSending(true);
    setError(null);
    setResult(null);
    try {
      const sent = await api.steerMessage(
        target,
        agent.agent_id,
        subject.trim(),
        body,
      );
      setResult(sent);
      // Clear the draft so a stray second click cannot double-send.
      setBody("");
    } catch (exc) {
      setError((exc as Error).message);
    } finally {
      setSending(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 bg-black/40 flex items-start justify-center pt-24"
      onClick={onClose}
      data-testid="steer-modal"
    >
      <div
        className="relative w-[480px] max-w-[94vw] bg-white dark:bg-surface-900 rounded-xl shadow-2xl border border-surface-200/50 dark:border-surface-700/50 overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="px-5 pt-4 pb-3 border-b border-surface-100 dark:border-surface-800">
          <div className="flex items-center gap-2">
            <Target size={15} className="text-accent-500" />
            <h2 className="text-sm font-semibold text-surface-900 dark:text-surface-100">
              Steer agent
            </h2>
            <button
              className="ml-auto p-1 rounded text-surface-400 hover:text-surface-600 dark:hover:text-surface-300"
              onClick={onClose}
              title="Close"
            >
              <X size={14} />
            </button>
          </div>
          <p className="text-[11px] text-surface-500 dark:text-surface-400 mt-1">
            Sends a direct message as{" "}
            <code className="font-mono bg-surface-100 dark:bg-surface-800 px-1 rounded">
              operator
            </code>{" "}
            — it lands in the agent's inbox like any other message and goes
            through the same permission and governance gates.
          </p>
        </div>

        <div className="px-5 py-4 space-y-3 text-xs">
          <div>
            <label className="text-[11px] uppercase tracking-wide text-surface-500 dark:text-surface-400">
              To
            </label>
            <div className="mt-1 flex items-center gap-2 rounded-lg border border-surface-200 dark:border-surface-700 bg-surface-50 dark:bg-surface-800 px-2 py-1.5">
              <span
                className={`h-2 w-2 rounded-full ${
                  agent.is_active
                    ? "bg-emerald-500"
                    : "bg-surface-400 dark:bg-surface-600"
                }`}
              />
              <span className="font-mono text-surface-800 dark:text-surface-200">
                {agent.agent_id}
              </span>
              <span className="text-[11px] text-surface-400 dark:text-surface-500">
                role: {agent.role ?? "—"} ·{" "}
                {agent.is_active ? "active" : "inactive"}
              </span>
            </div>
          </div>

          <div>
            <label className="text-[11px] uppercase tracking-wide text-surface-500 dark:text-surface-400">
              Workspace
            </label>
            <select
              value={target}
              onChange={(e) => setTarget(e.target.value)}
              className={`${inputCls} mt-1 block w-full font-mono`}
              data-testid="steer-workspace"
            >
              {target === "" && <option value="">Pick a workspace…</option>}
              {workspaces.map((ws) => (
                <option key={ws.workspace_id} value={ws.workspace_id}>
                  {ws.workspace_id.slice(0, 12)}…
                  {ws.display_name ? ` (${ws.display_name})` : ""}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="text-[11px] uppercase tracking-wide text-surface-500 dark:text-surface-400">
              Subject{" "}
              <span className="normal-case text-surface-400 dark:text-surface-500">
                (optional — defaults to "Operator steering")
              </span>
            </label>
            <input
              className={`${inputCls} mt-1 block w-full`}
              placeholder="e.g. Change of plan"
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              data-testid="steer-subject"
            />
          </div>

          <div>
            <label className="text-[11px] uppercase tracking-wide text-surface-500 dark:text-surface-400">
              Message
            </label>
            <textarea
              autoFocus
              rows={4}
              className={`${inputCls} mt-1 block w-full`}
              placeholder="Instructions for the agent…"
              value={body}
              onChange={(e) => setBody(e.target.value)}
              data-testid="steer-body"
            />
          </div>

          {error && (
            <p className="text-xs text-red-500" data-testid="steer-error">
              {error}
            </p>
          )}
          {result &&
            (result.status === "pending_approval" ? (
              <div
                className="rounded-lg bg-amber-50 dark:bg-amber-900/10 border border-amber-200 dark:border-amber-500/30 px-3 py-2 text-[11px] text-amber-700 dark:text-amber-300"
                data-testid="steer-intercepted"
              >
                Intercepted — a{" "}
                <code className="font-mono">require_approval</code> policy
                matches the operator too. Pending as{" "}
                <span className="font-mono">{result.approval_id}</span>; decide
                it on the Approvals screen.
              </div>
            ) : (
              <div
                className="rounded-lg bg-emerald-50 dark:bg-emerald-900/10 border border-emerald-200 dark:border-emerald-500/30 px-3 py-2 text-[11px] text-emerald-700 dark:text-emerald-300"
                data-testid="steer-sent"
              >
                Sent ✓ — delivered to{" "}
                <span className="font-mono">{agent.agent_id}</span>'s inbox.
                Track the conversation in Messages.
              </div>
            ))}
        </div>

        <div className="px-5 pb-4 flex items-center gap-2">
          <span className="text-[11px] text-surface-400 dark:text-surface-500">
            From: <span className="font-mono text-surface-600 dark:text-surface-300">operator</span>
          </span>
          <div className="ml-auto flex gap-2">
            <button className="btn btn-secondary" onClick={onClose}>
              {result ? "Close" : "Cancel"}
            </button>
            <button
              className="btn btn-primary"
              disabled={sending || !body.trim() || !target}
              onClick={send}
              data-testid="steer-send"
            >
              {sending ? "Sending…" : "Send as operator"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

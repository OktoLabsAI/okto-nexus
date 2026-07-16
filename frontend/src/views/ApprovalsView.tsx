// Approvals (spec 2948b2a2, sm_fc0c4173): the operator's HITL queue — actions
// intercepted by require_approval policies wait here until decided. Approving
// re-executes the action exactly as requested; rejecting notifies the
// requester with the justification. Queue reads and decisions work with
// feature_hitl OFF (BR6: the flag gates only the interception), so the
// banner mirrors the PoliciesView enforcement-disabled one. The pending
// table is oldest-first and the detail panel is the ONE surface showing the
// full request_payload (BR5: the queue itself carries routing metadata only).

import { Fragment, useCallback, useEffect, useState } from "react";
import {
  ChevronDown,
  ChevronRight,
  RefreshCw,
  ShieldOff,
} from "lucide-react";
import { api, type ApprovalDetail, type ApprovalRow } from "../api";
import { PageContainer } from "../components/PageContainer";

const inputCls =
  "rounded-lg border border-surface-200 dark:border-surface-700 bg-white dark:bg-surface-800 px-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-accent-500/40";

function ago(iso: string | null): string {
  if (!iso) return "—";
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return "—";
  const s = Math.max(0, Math.floor((Date.now() - t) / 1000));
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`;
  return `${Math.floor(s / 86400)}d`;
}

// Compact "who does it address" line from the BR5 metadata (never content).
function describeTarget(meta: ApprovalRow["payload_meta"]): string {
  const target = meta.target as
    | {
        strategy?: string;
        agent_id?: string;
        capability?: unknown;
        role?: string;
      }
    | null
    | undefined;
  if (!target || typeof target !== "object") {
    return meta.kind === "handoff_create" ? "—" : "broadcast";
  }
  switch (target.strategy) {
    case "direct":
      return `direct → ${target.agent_id ?? "?"}`;
    case "capability":
      return `capability: ${JSON.stringify(target.capability)}`;
    case "role":
      return `role: ${target.role ?? "?"}`;
    default:
      return target.strategy ?? "—";
  }
}

function actionChip(action: string): string {
  return action === "broadcast"
    ? "bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300"
    : "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300";
}

function DetailPanel({ detail }: { detail: ApprovalDetail | null }) {
  if (detail === null) {
    return (
      <p className="text-xs text-surface-400 dark:text-surface-500 py-2">
        Loading detail…
      </p>
    );
  }
  return (
    <div
      className="rounded-lg bg-surface-50 dark:bg-surface-900 border border-surface-200 dark:border-surface-700 p-3 space-y-2 text-xs"
      data-testid={`approval-detail-${detail.approval_id}`}
    >
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-surface-500 dark:text-surface-400">
        <span>
          workspace <span className="font-mono">{detail.workspace_id.slice(0, 12)}…</span>
        </span>
        <span>
          policy <span className="font-mono">{detail.policy_id}</span>
        </span>
        {detail.trace_id && (
          <span>
            trace <span className="font-mono">{detail.trace_id}</span>
          </span>
        )}
      </div>
      <div>
        <div className="text-[11px] uppercase tracking-wide text-surface-400 dark:text-surface-500 mb-1">
          Request payload (executed verbatim on approve)
        </div>
        <pre className="font-mono text-[11px] whitespace-pre-wrap break-all max-h-64 overflow-y-auto bg-white dark:bg-surface-950 rounded-lg border border-surface-200 dark:border-surface-800 p-2">
          {JSON.stringify(detail.request_payload, null, 2)}
        </pre>
      </div>
      {detail.executed_result !== undefined && (
        <div>
          <div className="text-[11px] uppercase tracking-wide text-surface-400 dark:text-surface-500 mb-1">
            Executed result
          </div>
          <pre className="font-mono text-[11px] whitespace-pre-wrap break-all max-h-40 overflow-y-auto bg-white dark:bg-surface-950 rounded-lg border border-surface-200 dark:border-surface-800 p-2">
            {JSON.stringify(detail.executed_result, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}

export function ApprovalsView({
  workspace,
  refreshTick,
  onChanged,
}: {
  workspace: string;
  // Bumped by App on every approval.* SSE event (and the header refresh).
  refreshTick: number;
  // Lets App refresh the sidebar badge right after a decision.
  onChanged: () => void;
}) {
  const [pending, setPending] = useState<ApprovalRow[]>([]);
  const [decided, setDecided] = useState<ApprovalRow[]>([]);
  // null = still probing /settings; the banner renders only on a firm false
  // (the PoliciesView enforcement-banner pattern).
  const [interceptionOn, setInterceptionOn] = useState<boolean | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [rejecting, setRejecting] = useState<string | null>(null);
  const [justification, setJustification] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [detailOpen, setDetailOpen] = useState<string | null>(null);
  const [detail, setDetail] = useState<ApprovalDetail | null>(null);

  const reload = useCallback(async () => {
    try {
      // GET /approvals is workspace-scoped; the "all" scope fans out over
      // every known workspace and merges client-side.
      const ids =
        workspace === "all"
          ? (await api.workspaces()).workspaces.map((w) => w.workspace_id)
          : [workspace];
      const pages = await Promise.all(
        ids.map((id) => api.approvals(id, "all")),
      );
      const rows = pages.flatMap((page) => page.items);
      setPending(
        rows
          .filter((row) => row.status === "pending")
          .sort((a, b) => a.created_at.localeCompare(b.created_at)),
      );
      setDecided(
        rows
          .filter((row) => row.status !== "pending")
          .sort((a, b) =>
            (b.decided_at ?? "").localeCompare(a.decided_at ?? ""),
          )
          .slice(0, 20),
      );
      setLoadError(null);
    } catch (exc) {
      setLoadError((exc as Error).message);
    }
    api
      .settings()
      .then(({ items }) => {
        const flag = items.find((item) => item.key === "feature_hitl");
        setInterceptionOn(flag ? flag.value === true : null);
      })
      .catch(() => setInterceptionOn(null));
  }, [workspace]);

  useEffect(() => {
    reload();
  }, [reload, refreshTick]);

  const openDetail = async (approvalId: string) => {
    if (detailOpen === approvalId) {
      setDetailOpen(null);
      setDetail(null);
      return;
    }
    setDetailOpen(approvalId);
    setDetail(null);
    try {
      setDetail(await api.approvalDetail(approvalId));
    } catch (exc) {
      setActionError((exc as Error).message);
      setDetailOpen(null);
    }
  };

  const decide = async (
    approvalId: string,
    decision: "approve" | "reject",
    just?: string,
  ) => {
    setBusy(approvalId);
    try {
      await api.decideApproval(approvalId, decision, just?.trim() || undefined);
      setRejecting(null);
      setJustification("");
      setActionError(null);
    } catch (exc) {
      // Includes CONFLICT (409): someone decided first — the reload below
      // folds the surviving decision into "Recent decisions".
      setActionError((exc as Error).message);
    } finally {
      setBusy(null);
      await reload();
      onChanged();
    }
  };

  const chevron = (row: ApprovalRow) => (
    <button
      className="p-1 rounded text-surface-400 hover:text-surface-600 dark:hover:text-surface-300"
      onClick={() => openDetail(row.approval_id)}
      title="Request detail"
      data-testid={`detail-${row.approval_id}`}
    >
      {detailOpen === row.approval_id ? (
        <ChevronDown size={13} />
      ) : (
        <ChevronRight size={13} />
      )}
    </button>
  );

  return (
    <PageContainer width="readable" scroll="y" testId="approvals-view">
      {/* Header */}
      <div className="mb-3">
        <h1 className="text-lg font-display font-semibold text-surface-900 dark:text-surface-100">
          Approvals
        </h1>
        <p className="text-xs text-surface-500 dark:text-surface-400 mt-1">
          Actions intercepted by{" "}
          <code className="font-mono">require_approval</code> policies wait
          here until you decide. Approving executes the action exactly as
          requested, with the same effects as the normal flow; rejecting
          notifies the requester with your justification.
        </p>
      </div>

      {/* Flag-OFF banner (BR6: pending items stay decidable) */}
      {interceptionOn === false && (
        <div
          className="mb-4 flex items-center gap-2 rounded-lg border border-amber-300 dark:border-amber-500/30 bg-amber-50 dark:bg-amber-900/10 px-3 py-2"
          data-testid="interception-disabled-banner"
        >
          <ShieldOff
            size={14}
            className="text-amber-600 dark:text-amber-400 shrink-0"
          />
          <p className="text-xs text-amber-700 dark:text-amber-300">
            <b>Interception disabled</b> — the{" "}
            <code className="font-mono">feature_hitl</code> flag is off, so no
            new actions are being intercepted. Pending items below remain
            decidable. Enable it under Settings &rsaquo; Features.
          </p>
        </div>
      )}

      {loadError && <p className="mb-3 text-xs text-red-500">{loadError}</p>}
      {actionError && (
        <p className="mb-3 text-xs text-red-500" data-testid="approval-action-error">
          {actionError}
        </p>
      )}

      {/* Pending queue (oldest first) */}
      <section className="panel p-4" data-testid="pending-approvals">
        <div className="flex items-center gap-2 mb-3">
          <h2 className="text-sm font-semibold text-surface-900 dark:text-surface-100">
            Pending
          </h2>
          {pending.length > 0 && (
            <span className="chip bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300">
              {pending.length} waiting
            </span>
          )}
          <span className="text-[11px] text-surface-400 dark:text-surface-500 ml-auto">
            oldest first
          </span>
          <button
            className="btn btn-secondary !px-2 !py-1"
            onClick={reload}
            title="Refresh"
            data-testid="refresh-approvals"
          >
            <RefreshCw size={12} />
          </button>
        </div>
        {pending.length === 0 ? (
          <p className="text-xs text-surface-400 dark:text-surface-500">
            No pending approvals — intercepted actions will appear here.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-left text-[11px] uppercase tracking-wide text-surface-400 dark:text-surface-500">
                  <th className="py-1.5 pr-1 font-medium w-6" />
                  <th className="py-1.5 pr-3 font-medium">Waiting</th>
                  <th className="py-1.5 pr-3 font-medium">Agent</th>
                  <th className="py-1.5 pr-3 font-medium">Action</th>
                  <th className="py-1.5 pr-3 font-medium">Summary</th>
                  <th className="py-1.5 pr-3 font-medium">Policy</th>
                  <th className="py-1.5 pr-0 font-medium text-right">
                    Decision
                  </th>
                </tr>
              </thead>
              <tbody>
                {pending.map((row) => (
                  <Fragment key={row.approval_id}>
                    <tr
                      className="border-t border-surface-100 dark:border-surface-800"
                      data-testid={`approval-${row.approval_id}`}
                    >
                      <td className="py-2 pr-1">{chevron(row)}</td>
                      <td className="py-2 pr-3 whitespace-nowrap text-surface-500 dark:text-surface-400">
                        {ago(row.created_at)}
                      </td>
                      <td className="py-2 pr-3 font-mono">{row.agent_id}</td>
                      <td className="py-2 pr-3">
                        <span
                          className={`chip font-mono text-[11px] ${actionChip(row.action)}`}
                        >
                          {row.action}
                        </span>
                      </td>
                      <td className="py-2 pr-3 text-surface-600 dark:text-surface-300">
                        {describeTarget(row.payload_meta)}
                        <span className="text-surface-400 dark:text-surface-500">
                          {" "}
                          · {row.payload_meta.byte_size} bytes
                        </span>
                      </td>
                      <td className="py-2 pr-3 font-mono text-surface-500 dark:text-surface-400">
                        {row.policy_id.slice(0, 12)}…
                      </td>
                      <td className="py-2 pr-0 text-right whitespace-nowrap">
                        {rejecting === row.approval_id ? (
                          <span className="inline-flex items-center gap-1">
                            <input
                              autoFocus
                              className={`${inputCls} !border-red-300 dark:!border-red-500/40 w-48`}
                              placeholder="Justification (sent to the agent)"
                              value={justification}
                              onChange={(e) => setJustification(e.target.value)}
                              onKeyDown={(e) =>
                                e.key === "Enter" &&
                                decide(row.approval_id, "reject", justification)
                              }
                              data-testid={`justification-${row.approval_id}`}
                            />
                            <button
                              className="text-[11px] px-2 py-1 rounded-lg bg-red-600 text-white font-medium disabled:opacity-50"
                              disabled={busy === row.approval_id}
                              onClick={() =>
                                decide(row.approval_id, "reject", justification)
                              }
                              data-testid={`confirm-reject-${row.approval_id}`}
                            >
                              Confirm reject
                            </button>
                            <button
                              className="text-[11px] px-2 py-1 rounded-lg border border-surface-200 dark:border-surface-700 text-surface-500"
                              onClick={() => {
                                setRejecting(null);
                                setJustification("");
                              }}
                            >
                              Cancel
                            </button>
                          </span>
                        ) : (
                          <>
                            <button
                              className="text-[11px] px-2 py-1 rounded-lg bg-emerald-600 text-white font-medium mr-1 disabled:opacity-50"
                              disabled={busy === row.approval_id}
                              onClick={() => decide(row.approval_id, "approve")}
                              data-testid={`approve-${row.approval_id}`}
                            >
                              Approve
                            </button>
                            <button
                              className="text-[11px] px-2 py-1 rounded-lg border border-red-300 dark:border-red-500/40 text-red-600 dark:text-red-400 disabled:opacity-50"
                              disabled={busy === row.approval_id}
                              onClick={() => {
                                setRejecting(row.approval_id);
                                setJustification("");
                              }}
                              data-testid={`reject-${row.approval_id}`}
                            >
                              Reject
                            </button>
                          </>
                        )}
                      </td>
                    </tr>
                    {detailOpen === row.approval_id && (
                      <tr>
                        <td colSpan={7} className="py-2">
                          <DetailPanel detail={detail} />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Recent decisions — self-gated by the data (the DenialsPanel pattern) */}
      {decided.length > 0 && (
        <section className="mt-5 panel p-4" data-testid="recent-decisions">
          <h2 className="text-sm font-semibold text-surface-900 dark:text-surface-100 mb-3">
            Recent decisions
          </h2>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <tbody>
                {decided.map((row) => (
                  <Fragment key={row.approval_id}>
                    <tr
                      className="border-t border-surface-100 dark:border-surface-800"
                      data-testid={`decided-${row.approval_id}`}
                    >
                      <td className="py-1.5 pr-1 w-6">{chevron(row)}</td>
                      <td className="py-1.5 pr-3 whitespace-nowrap text-surface-500 dark:text-surface-400">
                        {ago(row.decided_at)} ago
                      </td>
                      <td className="py-1.5 pr-3 font-mono">{row.agent_id}</td>
                      <td className="py-1.5 pr-3 font-mono text-[11px]">
                        {row.action}
                      </td>
                      <td className="py-1.5 pr-3">
                        <span
                          className={`chip text-[11px] ${
                            row.status === "approved"
                              ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300"
                              : "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300"
                          }`}
                        >
                          {row.status}
                        </span>
                      </td>
                      <td className="py-1.5 pr-0 text-surface-400 dark:text-surface-500">
                        by <span className="font-mono">{row.decided_by ?? "—"}</span>
                        {row.status === "rejected" && row.justification && (
                          <span> · “{row.justification}”</span>
                        )}
                      </td>
                    </tr>
                    {detailOpen === row.approval_id && (
                      <tr>
                        <td colSpan={6} className="py-2">
                          <DetailPanel detail={detail} />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </PageContainer>
  );
}

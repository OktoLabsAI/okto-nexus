// Approvals (spec 2948b2a2, sm_fc0c4173): the operator's HITL queue — actions
// intercepted by require_approval policies wait here until decided. Approving
// re-executes the action exactly as requested; rejecting notifies the
// requester with the justification. Queue reads and decisions work with
// feature_hitl OFF (BR6: the flag gates only the interception), so the
// banner mirrors the PoliciesView enforcement-disabled one. The pending
// table is oldest-first and the detail panel is the ONE surface showing the
// full request_payload (BR5: the queue itself carries routing metadata only).

import { Fragment, useCallback, useEffect, useRef, useState } from "react";
import {
  ChevronDown,
  ChevronRight,
  RefreshCw,
  ShieldOff,
} from "lucide-react";
import { api, type ApprovalDetail, type ApprovalRow } from "../api";
import { PageContainer } from "../components/PageContainer";
import { useWorkspaceName } from "../components/WorkspaceNames";
import { NativeApprovalInput } from "../components/NativeApprovalInput";
import { CanonicalNativeDecision } from "../components/CanonicalNativeDecision";

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
  if (["runtime_native_approval", "execution.native.respond"].includes(meta.kind)) return "Runtime request";
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

function DetailPanel({ detail, busy = false, onApprove, onChanged = () => {} }: {
  detail: ApprovalDetail | null; busy?: boolean;
  onApprove?: (response?: Record<string, unknown>) => void;
  onChanged?: () => void;
}) {
  const workspaceName = useWorkspaceName(detail?.workspace_id);
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
          workspace <span>{workspaceName}</span>
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
      {detail.status === "archived" && <p role="status">Archived by {detail.archived_by}. Previous status: {detail.original_status}. Archiving does not send a decision to the runtime.</p>}
      {detail.status !== "archived" && detail.action === "runtime_native_approval" && <NativeApprovalInput key={detail.approval_id}
        detail={detail} busy={busy} onApprove={onApprove ?? (() => {})} />}
      {detail.status !== "archived" && detail.action === "execution.native.respond" && <CanonicalNativeDecision key={detail.approval_id}
        detail={detail} onChanged={onChanged} />}
      <div>
        <div className="text-[11px] uppercase tracking-wide text-surface-400 dark:text-surface-500 mb-1">
          {["runtime_native_approval", "execution.native.respond"].includes(detail.action) ? "Runtime request details" : "Request payload (executed verbatim on approve)"}
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
  const [rows, setRows] = useState<ApprovalRow[]>([]);
  const [status, setStatus] = useState("all");
  const [agent, setAgent] = useState("");
  const [action, setAction] = useState("");
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [loading, setLoading] = useState(false);
  const loadRequest = useRef(0);
  const invalidDates = !!(fromDate && toDate && fromDate > toDate);
  const filtered = rows.filter(row => {
    const created = new Date(row.created_at);
    const start = fromDate ? new Date(`${fromDate}T00:00:00`) : null;
    const end = toDate ? new Date(`${toDate}T00:00:00`) : null;
    if (end) end.setDate(end.getDate() + 1);
    return !invalidDates && (!agent || row.agent_id === agent) && (!action || row.action === action)
      && (!start || created >= start) && (!end || created < end);
  });
  const visible = filtered.filter(row => status === "all" || row.status === status);
  const pending = visible.filter(row => row.status === "pending")
    .sort((a, b) => a.created_at.localeCompare(b.created_at));
  const decided = visible.filter(row => row.status !== "pending")
    .sort((a, b) => (b.decided_at ?? b.created_at).localeCompare(a.decided_at ?? a.created_at));
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
  const detailRequest = useRef(0);
  useEffect(() => {
    detailRequest.current += 1;
    setDetailOpen(null);
    setDetail(null);
    setRows([]);
    setAgent("");
    setAction("");
  }, [workspace]);

  const reload = useCallback(async () => {
    const generation = ++loadRequest.current;
    setLoading(true);
    try {
      // GET /approvals is workspace-scoped; the "all" scope fans out over
      // every known workspace and merges client-side.
      const ids =
        workspace === "all"
          ? (await api.workspaces()).workspaces.map((w) => w.workspace_id)
          : [workspace];
      const pages = await Promise.all(
        ids.map(async (id) => {
          const items: ApprovalRow[] = [];
          for (let offset = 0; ; offset += 100) {
            const page = await api.approvals(id, "all", offset);
            items.push(...page.items);
            if (page.items.length < 100 || generation !== loadRequest.current) break;
          }
          return items;
        }),
      );
      if (generation !== loadRequest.current) return;
      setRows([...new Map(pages.flat().map(row => [row.approval_id, row])).values()]);
      setLoadError(null);
    } catch (exc) {
      if (generation === loadRequest.current) setLoadError((exc as Error).message);
    } finally {
      if (generation === loadRequest.current) setLoading(false);
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

  const openDetail = (approvalId: string) => {
    detailRequest.current += 1;
    setDetailOpen(current => current === approvalId ? null : approvalId);
    setDetail(null);
  };

  useEffect(() => {
    if (!detailOpen) return;
    const generation = ++detailRequest.current;
    let active = true;
    api.approvalDetail(detailOpen).then(loaded => {
      if (active && generation === detailRequest.current) setDetail(loaded);
    }).catch(exc => {
      if (active && generation === detailRequest.current) {
        setActionError((exc as Error).message);
        setDetail(null);
      }
    });
    return () => { active = false; };
  }, [detailOpen, refreshTick]);

  const decide = async (
    approvalId: string,
    decision: "approve" | "reject",
    just?: string,
    response?: Record<string, unknown>,
  ) => {
    setBusy(approvalId);
    try {
      await api.decideApproval(approvalId, decision, just?.trim() || undefined, response);
      detailRequest.current += 1;
      setDetailOpen(null);
      setDetail(null);
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

  const archive = async (approvalId: string) => {
    setBusy(approvalId);
    try {
      await api.archiveApproval(approvalId);
      detailRequest.current += 1;
      setDetailOpen(null); setDetail(null); setRejecting(null); setActionError(null);
    } catch (exc) {
      setActionError((exc as Error).message);
    } finally {
      setBusy(null); await reload(); onChanged();
    }
  };

  const archiveButton = (row: ApprovalRow) => row.status !== "archived" && (
    <button className="btn btn-secondary ml-2" disabled={busy !== null}
      title="Remove from the pending queue and badge. Keep the history without approving or sending a runtime decision."
      data-testid={`archive-${row.approval_id}`} onClick={() => void archive(row.approval_id)}>Archive</button>
  );

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
          Runtime requests and actions intercepted by{" "}
          <code className="font-mono">require_approval</code> policies wait
          here until you decide. Review native questions to provide an explicit
          answer. A recorded decision does not prove delivery to the runtime.
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

      <div className="panel p-3 mb-4 space-y-3">
        <div role="tablist" aria-label="Approval status" className="flex flex-wrap gap-2">
          {(["all", "pending", "approved", "rejected", "archived"] as const).map(value => (
            <button key={value} role="tab" aria-selected={status === value}
              className={`rounded-lg px-3 py-2 text-xs font-medium ${status === value
                ? "bg-accent-600 text-white" : "bg-surface-100 dark:bg-surface-800 text-surface-600 dark:text-surface-300"}`}
              onClick={() => { setStatus(value); setDetailOpen(null); setRejecting(null); }}>
              {value === "all" ? "All" : value[0].toUpperCase() + value.slice(1)}
              {" "}
              <span className="ml-2 opacity-75">{filtered.filter(row => value === "all" || row.status === value).length}</span>
            </button>
          ))}
        </div>
        <div className="flex flex-wrap items-end gap-3 text-xs">
          <label className="flex flex-col gap-1">Created from
            <input type="date" className={inputCls} value={fromDate} max={toDate || undefined}
              onChange={event => setFromDate(event.target.value)} />
          </label>
          <label className="flex flex-col gap-1">Created through
            <input type="date" className={inputCls} value={toDate} min={fromDate || undefined}
              onChange={event => setToDate(event.target.value)} />
          </label>
          <label className="flex flex-col gap-1">Action
            <select aria-label="Action" className={inputCls} value={action} onChange={event => setAction(event.target.value)}>
              <option value="">All actions</option>
              {[...new Set(rows.map(row => row.action))].sort().map(value => <option key={value}>{value}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1">Agent
            <select aria-label="Agent" className={inputCls} value={agent} onChange={event => setAgent(event.target.value)}>
              <option value="">All agents</option>
              {[...new Set(rows.map(row => row.agent_id))].sort().map(value => <option key={value}>{value}</option>)}
            </select>
          </label>
          <button className="btn btn-secondary" onClick={() => {setAgent(""); setAction(""); setFromDate(""); setToDate("");}}>Clear filters</button>
          <button className="btn btn-secondary" onClick={reload} disabled={loading} aria-label="Refresh approvals"><RefreshCw size={12} /></button>
        </div>
        <p className="text-xs text-surface-500" role="status">{loading ? "Loading approvals…" : `${visible.length} approval(s)`} · Dates use local time.</p>
        {invalidDates && <p role="alert" className="text-xs text-red-500">The start date must be on or before the end date.</p>}
      </div>
      {!loading && !visible.length && <p className="text-sm text-surface-500 py-4">No approvals match these filters.</p>}

      {/* Pending queue (oldest first) */}
      {(status === "all" || status === "pending") && <section className="panel p-4" data-testid="pending-approvals">
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
                        {row.action === "execution.native.respond" ? <button className="btn btn-secondary"
                          onClick={() => detailOpen !== row.approval_id && openDetail(row.approval_id)}
                          data-testid={`approve-${row.approval_id}`}>Review request</button> : rejecting === row.approval_id ? (
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
                              onClick={() => row.action === "runtime_native_approval"
                                ? (detailOpen !== row.approval_id && openDetail(row.approval_id))
                                : decide(row.approval_id, "approve")}
                              data-testid={`approve-${row.approval_id}`}
                            >
                              {row.action === "runtime_native_approval" ? "Review request" : "Approve"}
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
                        {archiveButton(row)}
                      </td>
                    </tr>
                    {detailOpen === row.approval_id && (
                      <tr>
                        <td colSpan={7} className="py-2">
                          <DetailPanel detail={detail?.approval_id === row.approval_id ? detail : null}
                            busy={busy === row.approval_id}
                            onChanged={() => { void reload(); onChanged(); }}
                            onApprove={response => decide(row.approval_id, "approve", undefined, response)} />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>}

      {/* Recent decisions — self-gated by the data (the DenialsPanel pattern) */}
      {decided.length > 0 && (
        <section className="mt-5 panel p-4" data-testid="recent-decisions">
          <h2 className="text-sm font-semibold text-surface-900 dark:text-surface-100 mb-3">
            History
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
                        {ago(row.archived_at ?? row.decided_at)} ago
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
                        by <span className="font-mono">{row.archived_by ?? row.decided_by ?? "—"}</span>
                        {row.status === "rejected" && row.justification && (
                          <span> · “{row.justification}”</span>
                        )}
                        {archiveButton(row)}
                      </td>
                    </tr>
                    {detailOpen === row.approval_id && (
                      <tr>
                        <td colSpan={6} className="py-2">
                          <DetailPanel detail={detail?.approval_id === row.approval_id ? detail : null}
                            onChanged={() => { void reload(); onChanged(); }} />
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

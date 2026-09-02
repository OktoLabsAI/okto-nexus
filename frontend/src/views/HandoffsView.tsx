// Handoffs as a Pulse-style kanban (owner-requested): columns with the
// kanban-column/kanban-card grammar, top border colour per status, header
// with counter, dashed empty state. Cancel stays confirm-guarded (FR6).
//
// Verification (R-I4, FR7): a sixth VERIFYING column sits between Claimed and
// Completed; verifiable cards show their acceptance criteria, verifier badge
// and latest rework feedback, and expose Pass/Fail actions. Everything is
// self-gated by DATA (the trace_id/D7 pattern): the UI never consults the
// feature flag, and cards without criteria render exactly as before (BR1).
//
// Dependencies (R-I5, FR7): Open cards with a dependencies aggregate wear a
// "Blocked" badge while satisfied < total - "Blocked · dead" when failed > 0,
// meaning a dependency was rejected/cancelled and the card can never unblock
// on its own. A "Depends on" line lists short dependency ids with the k/n
// progress. Same self-gating: cards without the fields render unchanged
// (BR11) and the flag is never consulted.

import { useCallback, useEffect, useState } from "react";
import { Ban, CheckCircle2, ShieldCheck, UserCheck, X } from "lucide-react";
import { api, type AgentRow, type GraphHandoff } from "../api";
import { useConfirm } from "../components/Confirm";
import {
  TargetDescriptor,
  targetCapabilityNames,
} from "../components/TargetDescriptor";
import { useWorkspaceName } from "../components/WorkspaceNames";
import { AgentSelect } from "../components/AgentSelect";

const CARDS_PER_PAGE = 3;
const inputCls =
  "rounded-lg border border-surface-200 dark:border-surface-700 bg-white dark:bg-surface-800 px-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-accent-500/40";

function asIso(value: string): string | undefined {
  if (!value) return undefined;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? undefined : date.toISOString();
}

const COLUMNS: { status: string; label: string; top: string; chip: string }[] = [
  {
    status: "OPEN",
    label: "Open",
    top: "border-t-accent-500",
    chip: "bg-accent-100 text-accent-700 dark:bg-accent-900/40 dark:text-accent-300",
  },
  {
    status: "CLAIMED",
    label: "Claimed",
    top: "border-t-amber-500",
    chip: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  },
  {
    // Amber family like Claimed (work still in flight) but the darker orange
    // shade so the two in-flight columns stay distinguishable at a glance.
    status: "VERIFYING",
    label: "Verifying",
    top: "border-t-orange-500",
    chip: "bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-300",
  },
  {
    status: "COMPLETED",
    label: "Completed",
    top: "border-t-emerald-500",
    chip: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300",
  },
  {
    status: "REJECTED",
    label: "Rejected",
    top: "border-t-red-500",
    chip: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300",
  },
  {
    status: "CANCELLED",
    label: "Cancelled",
    top: "border-t-surface-400",
    chip: "bg-surface-200 text-surface-600 dark:bg-surface-700 dark:text-surface-300",
  },
];

// Human label of the contracted verifier, derived from the materialised
// verify_by descriptor (creator resolves to the actual creator id).
function verifierLabel(h: GraphHandoff): string {
  const vb = h.verify_by;
  if (!vb) return "";
  if (vb.kind === "agent") return vb.agent_id ?? "?";
  if (vb.kind === "capability") return `cap:${vb.capability ?? "?"}`;
  return h.from_agent_id ?? "creator";
}

function outcomeText(value: string): string {
  if (!value) return "(empty response)";
  try {
    return JSON.stringify(JSON.parse(value), null, 2);
  } catch {
    return value;
  }
}

function outcomePreview(value: string): string {
  return outcomeText(value).replace(/\s+/g, " ").trim();
}

function HandoffDetailModal({
  handoff,
  onClose,
}: {
  handoff: GraphHandoff;
  onClose: () => void;
}) {
  const workspaceName = useWorkspaceName(handoff.workspace_id);
  return (
    <div className="modal-overlay">
      <div
        className="modal-content w-[720px] max-w-[94vw] max-h-[86vh] flex flex-col"
        role="dialog"
        aria-modal="true"
        data-testid={`handoff-detail-${handoff.handoff_id}`}
      >
        <div className="px-5 py-4 border-b border-surface-200/60 dark:border-surface-700/50 flex items-start gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="chip bg-fuchsia-100 text-fuchsia-700 dark:bg-fuchsia-900/40 dark:text-fuchsia-300">
                {handoff.status}
              </span>
              {handoff.trace_id && (
                <span className="text-[11px] text-surface-400 dark:text-surface-500 font-mono truncate">
                  trace {handoff.trace_id}
                </span>
              )}
            </div>
            <h3 className="mt-2 font-display font-semibold text-sm text-surface-900 dark:text-surface-100 font-mono truncate">
              {handoff.handoff_id}
            </h3>
          </div>
          <button
            className="ml-auto p-1.5 rounded-lg text-surface-400 hover:text-surface-700 hover:bg-surface-100 dark:hover:text-surface-200 dark:hover:bg-white/10"
            onClick={onClose}
            title="Close"
            data-testid="close-handoff-detail"
          >
            <X size={16} />
          </button>
        </div>

        <div className="px-5 py-4 overflow-auto space-y-4 text-xs text-surface-600 dark:text-surface-300">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <Meta label="workspace" value={workspaceName} />
            <Meta label="created" value={handoff.created_at} />
            {handoff.updated_at && <Meta label="updated" value={handoff.updated_at} />}
            <Meta label="from" value={handoff.from_agent_id ?? "—"} mono />
            <Meta label="claimed by" value={handoff.claimed_by ?? "—"} mono />
            <Meta label="visibility" value={handoff.visibility ?? "—"} mono />
            <Meta
              label="lease expires"
              value={handoff.lease_expires_at ?? "—"}
            />
            <Meta label="verifier" value={verifierLabel(handoff) || "—"} mono />
            <Meta
              label="verify kind"
              value={handoff.verify_by?.kind ?? "—"}
              mono
            />
          </div>

          <section>
            <h4 className="font-semibold text-surface-800 dark:text-surface-100 mb-2">
              Target
            </h4>
            <TargetDescriptor
              target={handoff.target}
              testId={`handoff-target-${handoff.handoff_id}`}
            />
          </section>

          {handoff.dependencies && (
            <section className="rounded-lg border border-surface-200 dark:border-surface-700 p-3">
              <h4 className="font-semibold text-surface-800 dark:text-surface-100 mb-2">
                Dependencies
              </h4>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                <Meta label="total" value={String(handoff.dependencies.total)} />
                <Meta
                  label="satisfied"
                  value={String(handoff.dependencies.satisfied)}
                />
                <Meta label="pending" value={String(handoff.dependencies.pending)} />
                <Meta label="failed" value={String(handoff.dependencies.failed)} />
              </div>
              {handoff.depends_on && handoff.depends_on.length > 0 && (
                <div className="mt-2 font-mono text-[11px] break-all text-surface-500 dark:text-surface-400">
                  {handoff.depends_on.join(", ")}
                </div>
              )}
            </section>
          )}

          {handoff.acceptance_criteria && handoff.acceptance_criteria.length > 0 && (
            <section className="rounded-lg border border-surface-200 dark:border-surface-700 p-3">
              <h4 className="font-semibold text-surface-800 dark:text-surface-100 mb-2">
                Acceptance criteria
              </h4>
              <ul className="space-y-1">
                {handoff.acceptance_criteria.map((item, index) => (
                  <li key={index} className="flex gap-2">
                    <span className="text-surface-400">•</span>
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {handoff.verification_feedback && (
            <section className="rounded-lg border border-orange-300 dark:border-orange-700 bg-orange-50 dark:bg-orange-900/20 p-3 text-orange-800 dark:text-orange-200">
              <h4 className="font-semibold mb-1">Verification feedback</h4>
              <p>{handoff.verification_feedback}</p>
            </section>
          )}

          {"result" in handoff && handoff.result != null && (
            <section
              className="rounded-lg border border-emerald-300 dark:border-emerald-700 bg-emerald-50 dark:bg-emerald-900/20 p-3"
              data-testid="handoff-agent-response"
            >
              <h4 className="font-semibold text-emerald-800 dark:text-emerald-200 mb-2">
                Agent response
              </h4>
              <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-words text-[11px] font-mono text-emerald-900 dark:text-emerald-100">
                {outcomeText(handoff.result)}
              </pre>
            </section>
          )}

          {"rejected_reason" in handoff && handoff.rejected_reason != null && (
            <section
              className="rounded-lg border border-red-300 dark:border-red-700 bg-red-50 dark:bg-red-900/20 p-3"
              data-testid="handoff-rejection-reason"
            >
              <h4 className="font-semibold text-red-800 dark:text-red-200 mb-1">
                Rejection reason
              </h4>
              <p className="whitespace-pre-wrap break-words text-red-900 dark:text-red-100">
                {handoff.rejected_reason || "(no reason provided)"}
              </p>
            </section>
          )}

          {"payload" in handoff && (
            <section>
              <h4 className="font-semibold text-surface-800 dark:text-surface-100 mb-2">
                Original request (payload)
              </h4>
              <pre className="rounded-lg bg-surface-100 dark:bg-surface-950 border border-surface-200 dark:border-surface-800 p-3 overflow-auto max-h-56 text-[11px] font-mono text-surface-700 dark:text-surface-200">
                {JSON.stringify(handoff.payload ?? null, null, 2)}
              </pre>
            </section>
          )}
        </div>
      </div>
    </div>
  );
}

function Meta({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wide text-surface-400 dark:text-surface-500">
        {label}
      </div>
      <div
        className={`mt-0.5 break-all text-surface-700 dark:text-surface-200 ${
          mono ? "font-mono" : ""
        }`}
      >
        {value}
      </div>
    </div>
  );
}

export function HandoffsView({
  workspace,
  refreshTick,
  onChanged,
}: {
  workspace: string;
  // The single header refresh is contextual: while this view is mounted,
  // each tick reloads the filtered kanban cards.
  refreshTick: number;
  onChanged: () => void;
}) {
  const { confirm, dialog } = useConfirm();
  const [items, setItems] = useState<GraphHandoff[]>([]);
  const [error, setError] = useState<string | null>(null);
  // Capabilities announced by the operator agent: the data behind the
  // capability-kind eligibility check of the Pass/Fail gating.
  const [operatorCaps, setOperatorCaps] = useState<Set<string>>(new Set());
  // Handoff whose Fail feedback box is open, and its draft text.
  const [failFor, setFailFor] = useState<string | null>(null);
  const [feedback, setFeedback] = useState("");
  const [busy, setBusy] = useState(false);
  const [detail, setDetail] = useState<GraphHandoff | null>(null);
  const [agents, setAgents] = useState<AgentRow[]>([]);
  const [since, setSince] = useState("");
  const [until, setUntil] = useState("");
  const [fromAgent, setFromAgent] = useState("");
  const [toAgent, setToAgent] = useState("");
  const [pages, setPages] = useState<Record<string, number>>({});

  const reload = useCallback(() => {
    const filters: Record<string, string> = {};
    const sinceIso = asIso(since);
    const untilIso = asIso(until);
    if (sinceIso) filters.since = sinceIso;
    if (untilIso) filters.until = untilIso;
    if (fromAgent) filters.from_agent = fromAgent;
    if (toAgent) filters.to_agent = toAgent;
    return api
      .handoffs(workspace === "all" ? undefined : workspace, filters)
      .then(({ items }) => {
        setItems(items);
        setPages({});
        setError(null);
      })
      .catch((exc) => setError((exc as Error).message));
  }, [workspace, since, until, fromAgent, toAgent]);

  useEffect(() => {
    reload();
  }, [reload, refreshTick]);

  useEffect(() => {
    api
      .agents()
      .then(({ items }) => {
        setAgents(items);
        const op = items.find((a) => a.agent_id === "operator");
        setOperatorCaps(new Set(op ? Object.keys(op.capabilities ?? {}) : []));
      })
      .catch(() => setOperatorCaps(new Set()));
  }, []);

  // The dashboard acts as the operator: enabled only when the operator is the
  // ELIGIBLE verifier of this handoff (verify_by agent "operator", creator
  // handoffs the operator created, or a capability the operator announces)
  // and never for its own deliveries (anti-self-verification, BR3). Pure
  // data - the backend re-applies the same domain rule anyway.
  const operatorCanVerify = (h: GraphHandoff): boolean => {
    const vb = h.verify_by;
    if (!vb || h.claimed_by === "operator") return false;
    if (vb.kind === "agent") return vb.agent_id === "operator";
    if (vb.kind === "capability") return operatorCaps.has(vb.capability ?? "");
    return h.from_agent_id === "operator";
  };

  const decide = async (h: GraphHandoff, verdict: "pass" | "fail", text?: string) => {
    setBusy(true);
    try {
      await api.verifyHandoff(h.handoff_id, h.workspace_id, verdict, text || undefined);
      setFailFor(null);
      setFeedback("");
      setError(null);
      await reload();
      onChanged();
    } catch (exc) {
      setError((exc as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="h-full min-h-0 flex flex-col p-4 gap-3">
      {dialog}
      {detail && (
        <HandoffDetailModal handoff={detail} onClose={() => setDetail(null)} />
      )}
      <div className="panel shrink-0 px-3 py-2 flex items-end gap-2 flex-wrap" data-testid="handoff-filters">
        <label className="text-[10px] uppercase tracking-wide text-surface-400 dark:text-surface-500">
          From date
          <input
            type="datetime-local"
            value={since}
            onChange={(event) => setSince(event.target.value)}
            className={`${inputCls} block mt-1 normal-case`}
          />
        </label>
        <label className="text-[10px] uppercase tracking-wide text-surface-400 dark:text-surface-500">
          To date
          <input
            type="datetime-local"
            value={until}
            onChange={(event) => setUntil(event.target.value)}
            className={`${inputCls} block mt-1 normal-case`}
          />
        </label>
        <AgentSelect label="From agent" value={fromAgent} onChange={setFromAgent} agents={agents} />
        <AgentSelect label="To agent" value={toAgent} onChange={setToAgent} agents={agents} />
        <button
          className="btn btn-secondary"
          onClick={() => {
            setSince("");
            setUntil("");
            setFromAgent("");
            setToAgent("");
          }}
        >
          Clear filters
        </button>
        <span className="ml-auto text-xs text-surface-500 dark:text-surface-400">
          {items.length} handoff{items.length === 1 ? "" : "s"}
        </span>
      </div>
      {error && <p className="text-xs text-red-500">{error}</p>}
      <div className="flex-1 min-h-0 overflow-auto">
      <div className="flex gap-4 min-w-max items-start" data-testid="handoffs-view">
        {COLUMNS.map(({ status, label, top, chip }) => {
          const allCards = items.filter((h) => h.status === status);
          const totalPages = Math.max(1, Math.ceil(allCards.length / CARDS_PER_PAGE));
          const page = Math.min(pages[status] ?? 1, totalPages);
          const column = allCards.slice(
            (page - 1) * CARDS_PER_PAGE,
            page * CARDS_PER_PAGE,
          );
          return (
            <div
              key={status}
              className={`kanban-column border-t-4 ${top} self-start flex flex-col`}
            >
              <div className="flex items-center justify-between mb-3 shrink-0">
                <div className="flex items-center gap-2">
                  <h3 className="kanban-column-header text-surface-700 dark:text-surface-200">
                    {label}
                  </h3>
                  <span className="text-xs bg-surface-200 dark:bg-surface-600 text-surface-600 dark:text-surface-300 px-1.5 py-0.5 rounded">
                    {allCards.length}
                  </span>
                </div>
                {allCards.length > CARDS_PER_PAGE && (
                  <span className="text-[10px] text-surface-400">{page}/{totalPages}</span>
                )}
              </div>

              <div className="space-y-2">
                {column.map((h) => {
                  const capabilityNames = targetCapabilityNames(h.target);
                  const canVerify = operatorCanVerify(h);
                  return (
                    <div
                      key={h.handoff_id}
                      className="kanban-card overflow-hidden cursor-pointer hover:border-accent-300 dark:hover:border-accent-700 transition-colors"
                      role="button"
                      tabIndex={0}
                      data-testid={`handoff-card-${h.handoff_id}`}
                      onClick={(event) => {
                        const targetEl = event.target as HTMLElement;
                        if (targetEl.closest("button, textarea, input, select")) {
                          return;
                        }
                        setDetail(h);
                      }}
                      onKeyDown={(event) => {
                        if (event.currentTarget !== event.target) return;
                        if (event.key === "Enter" || event.key === " ") {
                          event.preventDefault();
                          setDetail(h);
                        }
                      }}
                    >
                      <div className="flex items-center gap-1.5 mb-1.5 flex-wrap">
                        <span className={`chip ${chip}`}>{h.status}</span>
                        {status === "OPEN" &&
                          h.dependencies &&
                          h.dependencies.satisfied < h.dependencies.total &&
                          (h.dependencies.failed > 0 ? (
                            <span
                              className="chip bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300"
                              title="A dependency was rejected or cancelled. This handoff can no longer unblock — cancel it or re-plan."
                            >
                              Blocked · dead
                            </span>
                          ) : (
                            <span
                              className="chip bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-200"
                              title={`Waiting on dependencies: ${h.dependencies.satisfied}/${h.dependencies.total} completed`}
                            >
                              Blocked
                            </span>
                          ))}
                        {capabilityNames.length > 0 && (
                          <span
                            className="chip max-w-40 truncate bg-violet-100 text-violet-700 dark:bg-violet-900/40 dark:text-violet-300"
                            title={capabilityNames.join(" / ")}
                          >
                            {capabilityNames.join(" / ")}
                          </span>
                        )}
                        {h.verify_by && (
                          <span
                            className="chip max-w-40 truncate bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-300"
                            title={`Contracted verifier (${h.verify_by.kind})`}
                          >
                            <ShieldCheck size={10} /> verify: {verifierLabel(h)}
                          </span>
                        )}
                      </div>
                      <div className="text-sm font-medium text-surface-800 dark:text-surface-200 font-mono truncate">
                        {h.handoff_id}
                      </div>
                      <div className="mt-1 text-xs text-surface-500 dark:text-surface-400 space-y-0.5">
                        <div className="flex items-center gap-1">
                          <span className="text-surface-400">from</span>
                          <b>{h.from_agent_id ?? "—"}</b>
                        </div>
                        {h.claimed_by && (
                          <div className="flex items-center gap-1">
                            <UserCheck size={11} className="text-amber-500" />
                            <b>{h.claimed_by}</b>
                          </div>
                        )}
                        <div className="text-[10px] text-surface-400 dark:text-surface-500">
                          {h.created_at}
                        </div>
                      </div>

                      {h.depends_on && h.dependencies && (
                        <div className="mt-1.5 text-[11px] text-surface-500 dark:text-surface-400 truncate">
                          Depends on:{" "}
                          <span className="font-mono">
                            {h.depends_on
                              .slice(0, 3)
                              .map((id) => id.slice(0, 8))
                              .join(", ")}
                            {h.depends_on.length > 3
                              ? ` +${h.depends_on.length - 3}`
                              : ""}
                          </span>{" "}
                          ·{" "}
                          <span
                            className={
                              h.dependencies.failed > 0
                                ? "text-red-500 dark:text-red-300"
                                : "text-surface-600 dark:text-surface-300"
                            }
                          >
                            {h.dependencies.satisfied}/{h.dependencies.total} done
                            {h.dependencies.failed > 0 &&
                              ` · ${h.dependencies.failed} failed`}
                          </span>
                        </div>
                      )}

                      {h.acceptance_criteria && (
                        <ul className="mt-1.5 space-y-0.5">
                          {h.acceptance_criteria.slice(0, 2).map((c, i) => (
                            <li
                              key={i}
                              className="flex items-start gap-1 text-[11px] text-surface-500 dark:text-surface-400"
                            >
                              <span className="text-surface-400">•</span>
                              <span className="truncate">{c}</span>
                            </li>
                          ))}
                          {h.acceptance_criteria.length > 2 && (
                            <li className="pl-3 text-[10px] text-surface-400 dark:text-surface-500">
                              +{h.acceptance_criteria.length - 2} more criteria
                            </li>
                          )}
                        </ul>
                      )}

                      {h.verification_feedback && (
                        <div className="mt-1.5 rounded border border-orange-300 dark:border-orange-700 bg-orange-50 dark:bg-orange-900/20 px-2 py-1 text-[11px] text-orange-800 dark:text-orange-200">
                          <div className="line-clamp-3 break-words">
                            <b>Rework:</b> {h.verification_feedback}
                          </div>
                        </div>
                      )}

                      {"result" in h && h.result != null && (
                        <div
                          className="mt-1.5 rounded border border-emerald-300 dark:border-emerald-700 bg-emerald-50 dark:bg-emerald-900/20 px-2 py-1.5 text-[11px] text-emerald-800 dark:text-emerald-200"
                          data-testid={`handoff-result-${h.handoff_id}`}
                        >
                          <div className="line-clamp-3 break-words">
                            <b>Agent response:</b> {outcomePreview(h.result)}
                          </div>
                        </div>
                      )}

                      {"rejected_reason" in h && h.rejected_reason != null && (
                        <div
                          className="mt-1.5 rounded border border-red-300 dark:border-red-700 bg-red-50 dark:bg-red-900/20 px-2 py-1.5 text-[11px] text-red-800 dark:text-red-200"
                          data-testid={`handoff-rejection-${h.handoff_id}`}
                        >
                          <div className="line-clamp-3 break-words">
                            <b>Rejection reason:</b>{" "}
                            {h.rejected_reason || "(no reason provided)"}
                          </div>
                        </div>
                      )}

                      {((h.acceptance_criteria?.length ?? 0) > 2 ||
                        (h.verification_feedback?.length ?? 0) > 180 ||
                        (h.result?.length ?? 0) > 180 ||
                        (h.rejected_reason?.length ?? 0) > 180) && (
                        <div className="mt-1.5 text-[10px] font-medium text-accent-600 dark:text-accent-400">
                          Open card for complete details →
                        </div>
                      )}

                      {status === "COMPLETED" && h.verify_by && (
                        // A verifiable handoff only reaches COMPLETED through
                        // a pass verdict; the label is the contracted
                        // verify_by descriptor (the full audit trail lives in
                        // the handoff.completed event's verified_by).
                        <div
                          className="mt-1.5 flex items-center gap-1 text-[11px] text-emerald-600 dark:text-emerald-400"
                          title="Passed verification (see the handoff.completed event for the verdict author)"
                        >
                          <CheckCircle2 size={11} /> verified by {verifierLabel(h)}
                        </div>
                      )}

                      {status === "VERIFYING" && (
                        <div className="mt-2 space-y-1.5">
                          {failFor === h.handoff_id ? (
                            <div className="space-y-1.5">
                              <textarea
                                className="w-full rounded-lg border border-surface-200 dark:border-surface-700 bg-white dark:bg-surface-800 px-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-accent-500/40"
                                rows={2}
                                maxLength={2000}
                                placeholder="Rework feedback for the claimant (optional)"
                                value={feedback}
                                onChange={(e) => setFeedback(e.target.value)}
                              />
                              <div className="flex gap-1.5">
                                <button
                                  className="btn btn-secondary !py-1 !text-xs text-red-500"
                                  disabled={busy}
                                  onClick={() => decide(h, "fail", feedback)}
                                >
                                  Fail handoff
                                </button>
                                <button
                                  className="btn btn-secondary !py-1 !text-xs"
                                  disabled={busy}
                                  onClick={() => {
                                    setFailFor(null);
                                    setFeedback("");
                                  }}
                                >
                                  Back
                                </button>
                              </div>
                            </div>
                          ) : (
                            <div className="flex gap-1.5">
                              <button
                                className="btn btn-secondary !py-1 !text-xs text-emerald-600"
                                disabled={!canVerify || busy}
                                title={
                                  canVerify
                                    ? "Approve the delivery: handoff completes"
                                    : `Only the contracted verifier may decide (verify: ${verifierLabel(h)})`
                                }
                                onClick={() =>
                                  confirm({
                                    title: "Pass verification?",
                                    body: (
                                      <span>
                                        Handoff <code>{h.handoff_id}</code> will be
                                        marked COMPLETED, verified by the operator.
                                      </span>
                                    ),
                                    onConfirm: () => decide(h, "pass"),
                                  })
                                }
                              >
                                Pass
                              </button>
                              <button
                                className="btn btn-secondary !py-1 !text-xs text-red-500"
                                disabled={!canVerify || busy}
                                title={
                                  canVerify
                                    ? "Send back to the claimant for rework"
                                    : `Only the contracted verifier may decide (verify: ${verifierLabel(h)})`
                                }
                                onClick={() => {
                                  setFailFor(h.handoff_id);
                                  setFeedback("");
                                }}
                              >
                                Fail…
                              </button>
                            </div>
                          )}
                        </div>
                      )}

                      {(status === "OPEN" || status === "CLAIMED") && (
                        <button
                          className="btn btn-secondary !py-1 !text-xs mt-2 text-red-500"
                          onClick={() =>
                            confirm({
                              title: "Cancel handoff?",
                              body: (
                                <span>
                                  Handoff <code>{h.handoff_id}</code> will be
                                  moved to CANCELLED and leaves the pool.
                                </span>
                              ),
                              onConfirm: async () => {
                                await api.cancelHandoff(h.handoff_id, h.workspace_id);
                                await reload();
                                onChanged();
                              },
                            })
                          }
                        >
                          <Ban size={12} /> Cancel…
                        </button>
                      )}
                    </div>
                  );
                })}

                {column.length === 0 && (
                  <div className="flex items-center justify-center rounded-lg border-2 border-dashed py-10 text-sm border-surface-300 text-surface-400 dark:border-surface-600 dark:text-surface-500">
                    No handoffs
                  </div>
                )}
              </div>
              {allCards.length > CARDS_PER_PAGE && (
                <div className="shrink-0 pt-2 mt-2 border-t border-surface-200 dark:border-surface-700 flex items-center justify-between text-[10px] text-surface-500">
                  <button
                    className="btn btn-secondary !px-2 !py-1"
                    disabled={page <= 1}
                    onClick={() => setPages((current) => ({ ...current, [status]: page - 1 }))}
                  >
                    ←
                  </button>
                  <span>page {page} of {totalPages}</span>
                  <button
                    className="btn btn-secondary !px-2 !py-1"
                    disabled={page >= totalPages}
                    onClick={() => setPages((current) => ({ ...current, [status]: page + 1 }))}
                  >
                    →
                  </button>
                </div>
              )}
            </div>
          );
        })}
      </div>
      </div>
    </div>
  );
}

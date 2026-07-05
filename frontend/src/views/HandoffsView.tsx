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

import { useEffect, useState } from "react";
import { Ban, CheckCircle2, ShieldCheck, UserCheck } from "lucide-react";
import { api, type GraphHandoff } from "../api";
import { useConfirm } from "../components/Confirm";

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

export function HandoffsView({
  workspace,
  onChanged,
}: {
  workspace: string;
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

  const reload = () =>
    api
      .handoffs(workspace === "all" ? undefined : workspace)
      .then(({ items }) => {
        setItems(items);
        setError(null);
      })
      .catch((exc) => setError((exc as Error).message));

  useEffect(() => {
    reload();
  }, [workspace]);

  useEffect(() => {
    api
      .agents()
      .then(({ items }) => {
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
    <div className="h-full overflow-x-auto overflow-y-hidden p-6">
      {dialog}
      {error && <p className="text-xs text-red-500 mb-2">{error}</p>}
      <div className="flex gap-4 h-full min-w-max" data-testid="handoffs-view">
        {COLUMNS.map(({ status, label, top, chip }) => {
          const column = items.filter((h) => h.status === status);
          return (
            <div
              key={status}
              className={`kanban-column border-t-4 ${top} h-full overflow-y-auto`}
            >
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <h3 className="kanban-column-header text-surface-700 dark:text-surface-200">
                    {label}
                  </h3>
                  <span className="text-xs bg-surface-200 dark:bg-surface-600 text-surface-600 dark:text-surface-300 px-1.5 py-0.5 rounded">
                    {column.length}
                  </span>
                </div>
              </div>

              <div className="space-y-2 flex-1">
                {column.map((h) => {
                  const target = h.target as {
                    capability?: string;
                    role?: string;
                    strategy?: string;
                  } | null;
                  const canVerify = operatorCanVerify(h);
                  return (
                    <div key={h.handoff_id} className="kanban-card">
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
                        {target?.capability && (
                          <span className="chip bg-violet-100 text-violet-700 dark:bg-violet-900/40 dark:text-violet-300">
                            {target.capability}
                          </span>
                        )}
                        {h.verify_by && (
                          <span
                            className="chip bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-300"
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
                        <div className="mt-1.5 text-[11px] text-surface-500 dark:text-surface-400">
                          Depends on:{" "}
                          <span className="font-mono">
                            {h.depends_on.map((id) => id.slice(0, 8)).join(", ")}
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
                          {h.acceptance_criteria.map((c, i) => (
                            <li
                              key={i}
                              title={c}
                              className="flex items-start gap-1 text-[11px] text-surface-500 dark:text-surface-400"
                            >
                              <span className="text-surface-400">•</span>
                              <span className="truncate">{c}</span>
                            </li>
                          ))}
                        </ul>
                      )}

                      {h.verification_feedback && (
                        <div className="mt-1.5 rounded border border-orange-300 dark:border-orange-700 bg-orange-50 dark:bg-orange-900/20 px-2 py-1 text-[11px] text-orange-800 dark:text-orange-200">
                          <b>Rework:</b> {h.verification_feedback}
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
            </div>
          );
        })}
      </div>
    </div>
  );
}

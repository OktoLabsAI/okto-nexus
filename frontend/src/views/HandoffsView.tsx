// Handoffs as a Pulse-style kanban (owner-requested): columns with the
// kanban-column/kanban-card grammar, top border colour per status, header
// with counter, dashed empty state. Cancel stays confirm-guarded (FR6).

import { useEffect, useState } from "react";
import { Ban, UserCheck } from "lucide-react";
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
                  return (
                    <div key={h.handoff_id} className="kanban-card">
                      <div className="flex items-center gap-1.5 mb-1.5">
                        <span className={`chip ${chip}`}>{h.status}</span>
                        {target?.capability && (
                          <span className="chip bg-violet-100 text-violet-700 dark:bg-violet-900/40 dark:text-violet-300">
                            {target.capability}
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

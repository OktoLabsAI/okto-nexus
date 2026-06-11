// Message history (FR4 of spec S2): paginated table with lane/agent/period
// filters straight onto GET /api/v1/messages. Pulse light/dark grammar.

import { useEffect, useState } from "react";
import { api, type MessageRow } from "../api";

const LANES = ["", "unread", "delivered", "read", "parked"];

const LANE_CHIP: Record<string, string> = {
  unread: "bg-accent-100 text-accent-700 dark:bg-accent-900/40 dark:text-accent-300",
  delivered: "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300",
  parked: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300",
  read: "bg-surface-200 text-surface-600 dark:bg-surface-700 dark:text-surface-300",
};

export function MessagesView({ workspace }: { workspace: string }) {
  const [items, setItems] = useState<MessageRow[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [lane, setLane] = useState("");
  const [agent, setAgent] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const params: Record<string, string> = {
      page: String(page),
      page_size: "25",
    };
    if (workspace !== "all") params.workspace = workspace;
    if (lane) params.lane = lane;
    if (agent) params.agent = agent;
    api
      .messages(params)
      .then((data) => {
        setItems(data.items);
        setTotal(data.total);
        setError(null);
      })
      .catch((exc) => setError((exc as Error).message));
  }, [workspace, page, lane, agent]);

  const inputCls =
    "rounded-lg border border-surface-200 dark:border-surface-700 bg-white dark:bg-surface-800 px-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-accent-500/40";

  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="max-w-5xl mx-auto space-y-3" data-testid="messages-view">
        <div className="flex items-center gap-2 text-xs">
          <select
            value={lane}
            onChange={(e) => {
              setLane(e.target.value);
              setPage(1);
            }}
            className={inputCls}
          >
            {LANES.map((l) => (
              <option key={l} value={l}>
                {l || "all lanes"}
              </option>
            ))}
          </select>
          <input
            placeholder="filter by agent…"
            value={agent}
            onChange={(e) => {
              setAgent(e.target.value);
              setPage(1);
            }}
            className={`${inputCls} font-mono`}
          />
          <span className="ml-auto text-surface-500">{total} messages</span>
          <button
            className="btn btn-secondary"
            disabled={page <= 1}
            onClick={() => setPage(page - 1)}
          >
            ←
          </button>
          <span className="text-surface-500">page {page}</span>
          <button
            className="btn btn-secondary"
            disabled={page * 25 >= total}
            onClick={() => setPage(page + 1)}
          >
            →
          </button>
        </div>

        {error && <p className="text-xs text-red-500">{error}</p>}

        <div className="panel divide-y divide-surface-100 dark:divide-surface-700/50 text-xs">
          {items.map((m) => (
            <div key={m.message_id} className="px-3 py-2">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-mono text-accent-600 dark:text-accent-400">
                  {m.from_agent_id}
                </span>
                <span className="text-surface-400">→</span>
                {m.deliveries.map((d) => (
                  <span
                    key={d.delivery_id}
                    className="font-mono text-surface-700 dark:text-surface-300"
                  >
                    {d.recipient_agent_id}
                    <span className={`ml-1 chip ${LANE_CHIP[d.status] ?? LANE_CHIP.read}`}>
                      {d.status}
                    </span>
                  </span>
                ))}
                {m.deliveries.length === 0 && (
                  <span className="chip bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300">
                    no recipient
                  </span>
                )}
                <span className="ml-auto text-surface-400 dark:text-surface-500">
                  {m.created_at}
                </span>
              </div>
              <div className="text-surface-600 dark:text-surface-400 mt-1">
                {m.subject ?? m.preview ?? ""}
              </div>
            </div>
          ))}
          {items.length === 0 && (
            <div className="px-3 py-6 text-surface-400 dark:text-surface-500">
              No messages for these filters.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

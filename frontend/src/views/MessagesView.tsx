// Message history (FR4 of spec S2): structured filters (lane + DE/PARA agent
// comboboxes) straight onto GET /api/v1/messages, with a per-message detail
// modal. Plus semantic search (Frente 3): GET /api/v1/messages/search ranks by
// cosine over message embeddings, degrading gracefully when embeddings are off.
// Pulse light/dark grammar.

import { Search, X } from "lucide-react";
import { useEffect, useState } from "react";
import {
  api,
  ApiError,
  type AgentRow,
  type MessageRow,
  type MessageSearchHit,
} from "../api";
import { AgentSelect } from "../components/AgentSelect";
import { MessageDetailModal } from "../components/MessageDetailModal";

const LANES = ["", "unread", "delivered", "read", "parked"];

const LANE_CHIP: Record<string, string> = {
  unread: "bg-accent-100 text-accent-700 dark:bg-accent-900/40 dark:text-accent-300",
  delivered: "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300",
  parked: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300",
  read: "bg-surface-200 text-surface-600 dark:bg-surface-700 dark:text-surface-300",
};

const PAGE_SIZE = 25;

export function MessagesView({ workspace }: { workspace: string }) {
  const [items, setItems] = useState<MessageRow[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [lane, setLane] = useState("");
  const [fromAgent, setFromAgent] = useState("");
  const [toAgent, setToAgent] = useState("");
  const [agents, setAgents] = useState<AgentRow[]>([]);
  const [selected, setSelected] = useState<MessageRow | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Semantic search (Frente 3): a non-null hits array switches the panel into
  // results mode; searchNote carries the graceful-degradation message.
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<MessageSearchHit[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [searchNote, setSearchNote] = useState<string | null>(null);

  // Known agents feed both DE/PARA comboboxes (loaded once).
  useEffect(() => {
    api
      .agents()
      .then(({ items }) => setAgents(items))
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    const params: Record<string, string> = {
      page: String(page),
      page_size: String(PAGE_SIZE),
      include_body: "true", // body travels with the row so the modal is instant
    };
    if (workspace !== "all") params.workspace = workspace;
    if (lane) params.lane = lane;
    if (fromAgent) params.from_agent = fromAgent;
    if (toAgent) params.to_agent = toAgent;
    api
      .messages(params)
      .then((data) => {
        setItems(data.items);
        setTotal(data.total);
        setError(null);
      })
      .catch((exc) => setError((exc as Error).message));
  }, [workspace, page, lane, fromAgent, toAgent]);

  const runSearch = () => {
    const q = query.trim();
    if (!q) {
      clearSearch();
      return;
    }
    setSearching(true);
    setSearchNote(null);
    api
      .searchMessages(q, 25)
      .then((data) => {
        setHits(data.items);
        setSearchNote(
          data.items.length === 0 ? "Nenhuma mensagem semelhante encontrada." : null,
        );
      })
      .catch((exc) => {
        setHits(null);
        if (exc instanceof ApiError && exc.code === "EMBEDDINGS_UNAVAILABLE") {
          setSearchNote(
            "Busca semântica indisponível: ative embedding_mode (stub/local) em Settings.",
          );
        } else {
          setSearchNote((exc as Error).message);
        }
      })
      .finally(() => setSearching(false));
  };

  const clearSearch = () => {
    setQuery("");
    setHits(null);
    setSearchNote(null);
  };

  const inputCls =
    "rounded-lg border border-surface-200 dark:border-surface-700 bg-white dark:bg-surface-800 px-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-accent-500/40";

  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="max-w-5xl mx-auto space-y-3" data-testid="messages-view">
        {/* Semantic search bar (Frente 3) */}
        <div className="flex items-center gap-2 text-xs">
          <div className="relative flex-1">
            <Search
              size={14}
              className="absolute left-2.5 top-1/2 -translate-y-1/2 text-surface-400 dark:text-surface-500"
            />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && runSearch()}
              placeholder="Busca semântica por conteúdo das mensagens…"
              className={`${inputCls} w-full pl-8 pr-8`}
              data-testid="semantic-search-input"
            />
            {(query || hits !== null) && (
              <button
                onClick={clearSearch}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-surface-400 hover:text-surface-600 dark:hover:text-surface-300"
                title="Limpar busca"
              >
                <X size={14} />
              </button>
            )}
          </div>
          <button
            className="btn btn-secondary"
            onClick={runSearch}
            disabled={searching || !query.trim()}
          >
            {searching ? "Buscando…" : "Buscar"}
          </button>
        </div>

        {searchNote && (
          <p className="text-xs text-surface-500 dark:text-surface-400">{searchNote}</p>
        )}

        {hits !== null ? (
          /* ----- Semantic search results (ranked by cosine) ----- */
          <>
            <div className="flex items-center gap-2 text-xs">
              <span className="text-surface-500 dark:text-surface-400">
                {hits.length} resultado{hits.length === 1 ? "" : "s"} por similaridade
              </span>
            </div>
            <div className="panel divide-y divide-surface-100 dark:divide-surface-700/50 text-xs">
              {hits.map((h, i) => (
                <div
                  key={h.message_id}
                  className="px-3 py-2"
                  data-testid="search-hit"
                >
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-surface-400 dark:text-surface-500 w-5 tabular-nums">
                      {i + 1}.
                    </span>
                    <span className="font-mono text-accent-600 dark:text-accent-400">
                      {h.from_agent_id}
                    </span>
                    <span
                      className="chip bg-accent-100 text-accent-700 dark:bg-accent-900/40 dark:text-accent-300 tabular-nums"
                      title="Similaridade cosseno"
                    >
                      {h.score.toFixed(3)}
                    </span>
                    <span className="ml-auto text-surface-400 dark:text-surface-500">
                      {h.created_at}
                    </span>
                  </div>
                  <div className="text-surface-600 dark:text-surface-400 mt-1 truncate pl-7">
                    {h.subject ?? "(sem assunto)"}
                  </div>
                </div>
              ))}
              {hits.length === 0 && (
                <div className="px-3 py-6 text-surface-400 dark:text-surface-500">
                  Nenhuma mensagem semelhante.
                </div>
              )}
            </div>
          </>
        ) : (
          /* ----- Structured filter list (default) ----- */
          <>
            <div className="flex items-center gap-2 text-xs flex-wrap">
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
              <AgentSelect
                label="DE"
                value={fromAgent}
                onChange={(v) => {
                  setFromAgent(v);
                  setPage(1);
                }}
                agents={agents}
              />
              <AgentSelect
                label="PARA"
                value={toAgent}
                onChange={(v) => {
                  setToAgent(v);
                  setPage(1);
                }}
                agents={agents}
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
                disabled={page * PAGE_SIZE >= total}
                onClick={() => setPage(page + 1)}
              >
                →
              </button>
            </div>

            {error && <p className="text-xs text-red-500">{error}</p>}

            <div className="panel divide-y divide-surface-100 dark:divide-surface-700/50 text-xs">
              {items.map((m) => (
                <button
                  key={m.message_id}
                  onClick={() => setSelected(m)}
                  className="w-full text-left px-3 py-2 hover:bg-surface-50 dark:hover:bg-surface-800/50 transition-colors"
                  data-testid="message-row"
                >
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
                  <div className="text-surface-600 dark:text-surface-400 mt-1 truncate">
                    {m.subject ?? m.preview ?? ""}
                  </div>
                </button>
              ))}
              {items.length === 0 && (
                <div className="px-3 py-6 text-surface-400 dark:text-surface-500">
                  No messages for these filters.
                </div>
              )}
            </div>
          </>
        )}
      </div>

      {selected && (
        <MessageDetailModal message={selected} onClose={() => setSelected(null)} />
      )}
    </div>
  );
}

// Messages (FR4): a full-bleed master-detail screen — a left filter rail
// (lane facets + from/to), a middle message list (Flat or Threads grouped by
// from->to pair), and an inline ResizablePanel detail (no blocking modal).
// Live-aware (debounced refetch on SSE ticks), keyboard navigable. Semantic
// search (Frente 3) ranks by cosine and degrades gracefully when off.

import { useCallback, useEffect, useRef, useState } from "react";
import {
  ChevronDown,
  ChevronRight,
  Inbox,
  MessagesSquare,
  Search,
  X,
} from "lucide-react";
import {
  api,
  ApiError,
  type AgentRow,
  type MessageRow,
  type MessageSearchHit,
} from "../api";
import type { SSEStatus } from "../useSSE";
import { AgentSelect } from "../components/AgentSelect";
import { LiveChip } from "../components/LiveChip";
import { MessageDetail } from "../components/MessageDetailModal";
import { PageContainer } from "../components/PageContainer";
import { ResizablePanel } from "../components/ResizablePanel";

const PAGE_SIZE = 25;

// Lane facets shown in the rail (value -> label + active chip colour).
const LANES: { value: string; label: string; dot: string }[] = [
  { value: "", label: "All", dot: "bg-surface-400" },
  { value: "unread", label: "Unread", dot: "bg-accent-500" },
  { value: "delivered", label: "Delivered", dot: "bg-blue-500" },
  { value: "read", label: "Read", dot: "bg-surface-400" },
  { value: "parked", label: "Parked", dot: "bg-red-500" },
];

const LANE_CHIP: Record<string, string> = {
  unread: "bg-accent-100 text-accent-700 dark:bg-accent-900/40 dark:text-accent-300",
  delivered: "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300",
  parked: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300",
  read: "bg-surface-200 text-surface-600 dark:bg-surface-700 dark:text-surface-300",
};

const inputCls =
  "rounded-lg border border-surface-200 dark:border-surface-700 bg-white dark:bg-surface-800 px-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-accent-500/40";

function recipientsKey(m: MessageRow): string {
  const to = m.deliveries.map((d) => d.recipient_agent_id).sort();
  return `${m.from_agent_id} → ${to.length ? to.join(", ") : "(no recipient)"}`;
}

function MessageRowItem({
  m,
  active,
  onClick,
}: {
  m: MessageRow;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`w-full text-left px-3 py-2 border-l-2 transition-colors ${
        active
          ? "border-accent-500 bg-accent-50 dark:bg-accent-900/20"
          : "border-transparent hover:bg-surface-50 dark:hover:bg-surface-800/50"
      }`}
      data-testid="message-row"
    >
      <div className="flex items-center gap-2 flex-wrap text-xs">
        <span className="font-mono text-accent-600 dark:text-accent-400">
          {m.from_agent_id}
        </span>
        <span className="text-surface-400">→</span>
        {m.deliveries.slice(0, 3).map((d) => (
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
        {m.deliveries.length > 3 && (
          <span className="text-surface-400">+{m.deliveries.length - 3}</span>
        )}
        {m.deliveries.length === 0 && (
          <span className="chip bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300">
            no recipient
          </span>
        )}
        <span className="ml-auto text-surface-400 dark:text-surface-500">
          {m.created_at}
        </span>
      </div>
      <div className="text-surface-600 dark:text-surface-400 mt-1 truncate text-xs">
        {m.subject ?? m.preview ?? ""}
      </div>
    </button>
  );
}

export function MessagesView({
  workspace,
  liveTick,
  sseStatus,
  onOpenTrace,
}: {
  workspace: string;
  liveTick?: number;
  sseStatus?: SSEStatus;
  // TraceChip click-through (R-I1): jumps to Events with the trace applied.
  onOpenTrace?: (traceId: string) => void;
}) {
  const [items, setItems] = useState<MessageRow[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [lane, setLane] = useState("");
  const [fromAgent, setFromAgent] = useState("");
  const [toAgent, setToAgent] = useState("");
  const [grouped, setGrouped] = useState(false);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [agents, setAgents] = useState<AgentRow[]>([]);
  const [selected, setSelected] = useState<MessageRow | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Semantic search (Frente 3): a non-null hits array switches the body into
  // results mode; searchNote carries the graceful-degradation message.
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<MessageSearchHit[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [searchNote, setSearchNote] = useState<string | null>(null);
  const searchRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api
      .agents()
      .then(({ items }) => setAgents(items))
      .catch(() => undefined);
  }, []);

  const fetchList = useCallback(() => {
    const params: Record<string, string> = {
      page: String(page),
      page_size: String(PAGE_SIZE),
      include_body: "true", // body travels with the row so detail is instant
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
        // Keep the open detail in sync with the refreshed page.
        setSelected((cur) =>
          cur ? data.items.find((m) => m.message_id === cur.message_id) ?? cur : cur,
        );
      })
      .catch((exc) => setError((exc as Error).message));
  }, [workspace, page, lane, fromAgent, toAgent]);

  useEffect(() => {
    fetchList();
  }, [fetchList]);

  // Live: a debounced refetch of the current page on SSE ticks (list mode only).
  useEffect(() => {
    if (hits !== null || !liveTick) return;
    const t = window.setTimeout(fetchList, 500);
    return () => window.clearTimeout(t);
  }, [liveTick, hits, fetchList]);

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
          data.items.length === 0 ? "No similar messages found." : null,
        );
      })
      .catch((exc) => {
        setHits(null);
        if (exc instanceof ApiError && exc.code === "EMBEDDINGS_UNAVAILABLE") {
          setSearchNote(
            "Semantic search is unavailable: enable embedding_mode (stub/local) in Settings.",
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

  const reset = () => {
    setLane("");
    setFromAgent("");
    setToAgent("");
    setPage(1);
    clearSearch();
  };

  // Search hits are deliberately lean. Hydrate the exact message by id and
  // keep the current query/results intact while the inline inspector opens.
  const openSearchHit = async (hit: MessageSearchHit) => {
    try {
      const message = await api.message(hit.message_id);
      setSelected(message);
      setError(null);
    } catch (exc) {
      setError((exc as Error).message);
    }
  };

  // Keyboard: ↑/↓ (or j/k) move the selection; Esc clears; "/" focuses search.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement | null)?.tagName;
      const typing = tag === "INPUT" || tag === "TEXTAREA";
      if (e.key === "/" && !typing) {
        e.preventDefault();
        searchRef.current?.focus();
        return;
      }
      if (typing) return;
      if (e.key === "Escape") {
        if (selected) setSelected(null);
        else if (hits !== null) clearSearch();
        return;
      }
      if (hits !== null || items.length === 0) return;
      if (e.key === "ArrowDown" || e.key === "j") {
        e.preventDefault();
        const i = selected
          ? items.findIndex((m) => m.message_id === selected.message_id)
          : -1;
        setSelected(items[Math.min(items.length - 1, i + 1)]);
      } else if (e.key === "ArrowUp" || e.key === "k") {
        e.preventDefault();
        const i = selected
          ? items.findIndex((m) => m.message_id === selected.message_id)
          : items.length;
        setSelected(items[Math.max(0, i - 1)]);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [selected, hits, items]);

  const toggleGroup = (key: string) =>
    setCollapsed((prev) => {
      const next = new Set(prev);
      next.has(key) ? next.delete(key) : next.add(key);
      return next;
    });

  // Threads: group the current page by from->to pair (most recent first).
  const groups: { key: string; rows: MessageRow[] }[] = [];
  if (grouped) {
    const byKey = new Map<string, MessageRow[]>();
    for (const m of items) {
      const k = recipientsKey(m);
      (byKey.get(k) ?? byKey.set(k, []).get(k)!).push(m);
    }
    for (const [key, rows] of byKey) groups.push({ key, rows });
  }

  return (
    <PageContainer width="bleed" scroll="none" className="flex" testId="messages-view">
      {/* ----- Filter rail ----- */}
      <aside className="w-60 shrink-0 border-r border-surface-200 dark:border-surface-700/60 overflow-y-auto p-4 space-y-4">
        <div>
          <div className="text-[11px] font-medium uppercase tracking-wider text-surface-400 dark:text-surface-500 mb-1.5">
            Lanes
          </div>
          <div className="space-y-0.5">
            {LANES.map((l) => {
              const active = lane === l.value;
              return (
                <button
                  key={l.value}
                  onClick={() => {
                    setLane(l.value);
                    setPage(1);
                  }}
                  className={`w-full flex items-center gap-2 px-2.5 py-1.5 rounded-lg text-left text-xs transition-colors ${
                    active
                      ? "bg-accent-100 text-accent-700 dark:bg-accent-900/50 dark:text-accent-200"
                      : "text-surface-600 hover:bg-surface-100 dark:text-surface-300 dark:hover:bg-surface-800"
                  }`}
                  data-testid={`lane-${l.value || "all"}`}
                >
                  <span className={`w-1.5 h-1.5 rounded-full ${l.dot}`} />
                  {l.label}
                </button>
              );
            })}
          </div>
        </div>

        <div className="space-y-2">
          <div className="text-[11px] font-medium uppercase tracking-wider text-surface-400 dark:text-surface-500">
            Participants
          </div>
          <AgentSelect
            label="From"
            value={fromAgent}
            onChange={(v) => {
              setFromAgent(v);
              setPage(1);
            }}
            agents={agents}
          />
          <AgentSelect
            label="To"
            value={toAgent}
            onChange={(v) => {
              setToAgent(v);
              setPage(1);
            }}
            agents={agents}
          />
        </div>

        <button className="btn btn-secondary w-full justify-center" onClick={reset}>
          Reset filters
        </button>
      </aside>

      {/* ----- List pane ----- */}
      <div className="flex-1 min-w-0 flex flex-col">
        {/* Header: search + mode + count + pagination + live */}
        <div className="shrink-0 border-b border-surface-200/60 dark:border-surface-700/60 px-4 py-3 space-y-2">
          <div className="flex items-center gap-2">
            <div className="relative flex-1">
              <Search
                size={14}
                className="absolute left-2.5 top-1/2 -translate-y-1/2 text-surface-400 dark:text-surface-500"
              />
              <input
                ref={searchRef}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && runSearch()}
                placeholder="Search message content…  ( / )"
                className={`${inputCls} w-full pl-8 pr-8`}
                data-testid="semantic-search-input"
              />
              {(query || hits !== null) && (
                <button
                  onClick={clearSearch}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-surface-400 hover:text-surface-600 dark:hover:text-surface-300"
                  title="Clear search"
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
              {searching ? "Searching…" : "Search"}
            </button>
          </div>

          <div className="flex items-center gap-2 text-xs">
            {hits === null && (
              <div className="flex items-center rounded-lg border border-surface-200 dark:border-surface-700 overflow-hidden">
                {([["Flat", false], ["Threads", true]] as const).map(([label, val]) => (
                  <button
                    key={label}
                    onClick={() => setGrouped(val)}
                    className={`px-2.5 py-1 ${
                      grouped === val
                        ? "bg-accent-100 text-accent-700 dark:bg-accent-900/50 dark:text-accent-200"
                        : "text-surface-500 hover:bg-surface-100 dark:hover:bg-surface-800"
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>
            )}
            {sseStatus && <LiveChip status={sseStatus} />}
            <span className="ml-auto text-surface-500">
              {hits !== null ? `${hits.length} results` : `${total} messages`}
            </span>
            {hits === null && (
              <>
                <button
                  className="btn btn-secondary !px-2"
                  disabled={page <= 1}
                  onClick={() => setPage(page - 1)}
                >
                  ←
                </button>
                <span className="text-surface-500">page {page}</span>
                <button
                  className="btn btn-secondary !px-2"
                  disabled={page * PAGE_SIZE >= total}
                  onClick={() => setPage(page + 1)}
                >
                  →
                </button>
              </>
            )}
          </div>
          {error && <p className="text-xs text-red-500">{error}</p>}
          {searchNote && (
            <p className="text-xs text-surface-500 dark:text-surface-400">{searchNote}</p>
          )}
        </div>

        {/* Body: search results, threads, or flat list */}
        <div className="flex-1 overflow-y-auto" data-testid="messages-list">
          {hits !== null ? (
            hits.length === 0 ? (
              <EmptyState icon="search" text="No similar messages." />
            ) : (
              <div className="divide-y divide-surface-100 dark:divide-surface-700/50">
                {hits.map((h, i) => (
                  <button
                    key={h.message_id}
                    onClick={() => openSearchHit(h)}
                    className={`w-full text-left px-3 py-2 transition-colors border-l-2 ${
                      selected?.message_id === h.message_id
                        ? "border-accent-500 bg-accent-50 dark:bg-accent-900/20"
                        : "border-transparent hover:bg-surface-50 dark:hover:bg-surface-800/50"
                    }`}
                    data-testid="search-hit"
                    title="Open message details"
                  >
                    <div className="flex items-center gap-2 flex-wrap text-xs">
                      <span className="text-surface-400 dark:text-surface-500 w-5 tabular-nums">
                        {i + 1}.
                      </span>
                      <span className="font-mono text-accent-600 dark:text-accent-400">
                        {h.from_agent_id}
                      </span>
                      <span
                        className="chip bg-accent-100 text-accent-700 dark:bg-accent-900/40 dark:text-accent-300 tabular-nums"
                        title="Cosine similarity"
                      >
                        {h.score.toFixed(3)}
                      </span>
                      <span className="ml-auto text-surface-400 dark:text-surface-500">
                        {h.created_at}
                      </span>
                    </div>
                    <div className="text-surface-600 dark:text-surface-400 mt-1 truncate pl-7 text-xs">
                      {h.subject ?? "(no subject)"}
                    </div>
                  </button>
                ))}
              </div>
            )
          ) : items.length === 0 ? (
            <EmptyState icon="inbox" text="No messages match these filters." onReset={reset} />
          ) : grouped ? (
            <div className="divide-y divide-surface-100 dark:divide-surface-700/50">
              {groups.map((g) => {
                const open = !collapsed.has(g.key);
                return (
                  <div key={g.key}>
                    <button
                      onClick={() => toggleGroup(g.key)}
                      className="w-full flex items-center gap-2 px-3 py-2 text-xs bg-surface-50/60 dark:bg-surface-800/40 hover:bg-surface-100 dark:hover:bg-surface-800 transition-colors sticky top-0"
                    >
                      {open ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
                      <span className="font-mono text-surface-700 dark:text-surface-300 truncate">
                        {g.key}
                      </span>
                      <span className="ml-auto chip bg-surface-200 text-surface-600 dark:bg-surface-700 dark:text-surface-300">
                        {g.rows.length}
                      </span>
                    </button>
                    {open &&
                      g.rows.map((m) => (
                        <MessageRowItem
                          key={m.message_id}
                          m={m}
                          active={selected?.message_id === m.message_id}
                          onClick={() => setSelected(m)}
                        />
                      ))}
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="divide-y divide-surface-100 dark:divide-surface-700/50">
              {items.map((m) => (
                <MessageRowItem
                  key={m.message_id}
                  m={m}
                  active={selected?.message_id === m.message_id}
                  onClick={() => setSelected(m)}
                />
              ))}
            </div>
          )}
        </div>
      </div>

      {/* ----- Inline detail ----- */}
      {selected && (
        <ResizablePanel
          storageKey="okto-nexus-messages-panel"
          testId="message-detail-panel"
        >
          <MessageDetail
            message={selected}
            onClose={() => setSelected(null)}
            onOpenTrace={onOpenTrace}
          />
        </ResizablePanel>
      )}
    </PageContainer>
  );
}

function EmptyState({
  icon,
  text,
  onReset,
}: {
  icon: "inbox" | "search";
  text: string;
  onReset?: () => void;
}) {
  const Icon = icon === "search" ? Search : icon === "inbox" ? Inbox : MessagesSquare;
  return (
    <div className="h-full flex flex-col items-center justify-center gap-3 text-surface-400 dark:text-surface-500 p-10">
      <Icon size={28} />
      <p className="text-sm">{text}</p>
      {onReset && (
        <button className="btn btn-secondary" onClick={onReset}>
          Clear filters
        </button>
      )}
    </div>
  );
}

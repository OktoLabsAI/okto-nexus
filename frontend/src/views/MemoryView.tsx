// Memory screen (spec 8928b320 FR8): the operator's read-and-curate browser
// over ONE workspace's shared memory store. Master-detail in the house
// full-bleed grammar (list pane + ResizablePanel detail). The toolbar search
// reuses the agents' ranking engine - the server DECLARES the effective
// search_mode (semantic | lexical | recent) and the UI surfaces it as a chip,
// never guessing. The dashboard shell normally hides this experimental view
// unless feature_memory is ON; the local banner remains as a defensive stale-
// session hint. Delete is the operator's physical curation (BR9).

import { useCallback, useEffect, useMemo, useState } from "react";
import { Brain, BrainCircuit, Search, Trash2, X } from "lucide-react";
import { api, type MemoryDetail, type MemoryItem } from "../api";
import { PageContainer } from "../components/PageContainer";
import { ResizablePanel } from "../components/ResizablePanel";
import { TraceChip } from "../components/TraceChip";

const inputCls =
  "rounded-lg border border-surface-200 dark:border-surface-700 bg-white dark:bg-surface-800 px-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-accent-500/40";

const MODE_CHIP: Record<string, string> = {
  semantic:
    "bg-indigo-100 text-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-300",
  lexical: "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300",
  recent:
    "bg-surface-200 text-surface-600 dark:bg-surface-700 dark:text-surface-300",
};

function relTime(iso: string, nowMs: number): string {
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return iso;
  const mins = Math.floor((nowMs - t) / 60_000);
  if (mins < 1) return "Just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return new Date(t).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  });
}

function TopicChip({
  topic,
  active,
  onClick,
}: {
  topic: string;
  active?: boolean;
  onClick?: () => void;
}) {
  const cls = active
    ? "bg-accent-600 text-white dark:bg-accent-500"
    : "bg-surface-200 text-surface-600 dark:bg-surface-700 dark:text-surface-300 hover:bg-surface-300 dark:hover:bg-surface-600";
  if (!onClick) {
    return <span className={`chip ${cls}`}>{topic}</span>;
  }
  return (
    <button
      onClick={onClick}
      className={`chip transition-colors ${cls}`}
      data-testid="memory-topic-chip"
    >
      {topic}
    </button>
  );
}

function MemoryRow({
  item,
  active,
  showScore,
  nowMs,
  onClick,
}: {
  item: MemoryItem;
  active: boolean;
  showScore: boolean;
  nowMs: number;
  onClick: () => void;
}) {
  const superseded = item.superseded_by != null;
  return (
    <button
      onClick={onClick}
      className={`w-full text-left px-4 py-2.5 border-l-2 transition-colors ${
        active
          ? "border-accent-500 bg-accent-50 dark:bg-accent-900/20"
          : "border-transparent hover:bg-surface-50 dark:hover:bg-surface-800/50"
      } ${superseded ? "opacity-60" : ""}`}
      data-testid="memory-row"
    >
      <div className="flex items-center gap-2">
        <span className="text-sm font-medium text-surface-800 dark:text-surface-100 truncate">
          {item.title}
        </span>
        {superseded && (
          <span className="chip bg-surface-200 text-surface-600 dark:bg-surface-700 dark:text-surface-300 shrink-0">
            Superseded
          </span>
        )}
        {showScore && item.score != null && (
          <span
            className="ml-auto shrink-0 text-xs font-mono text-indigo-600 dark:text-indigo-400"
            title="cosine score"
          >
            {item.score.toFixed(4)}
          </span>
        )}
      </div>
      <p className="mt-0.5 truncate text-xs text-surface-500 dark:text-surface-400">
        {item.content_preview}
      </p>
      <div className="mt-1 flex items-center gap-2 text-[11px] text-surface-500 dark:text-surface-400">
        <span className="font-medium">{item.author_agent_id}</span>
        <span>&middot;</span>
        <span>{relTime(item.created_at, nowMs)}</span>
        {item.topics.slice(0, 4).map((t) => (
          <TopicChip key={t} topic={t} />
        ))}
      </div>
    </button>
  );
}

export function MemoryView({
  workspace,
  liveTick,
  onOpenTrace,
}: {
  workspace: string;
  liveTick?: number;
  onOpenTrace?: (traceId: string) => void;
}) {
  const [qInput, setQInput] = useState("");
  const [q, setQ] = useState("");
  const [topic, setTopic] = useState<string | null>(null);
  const [includeSuperseded, setIncludeSuperseded] = useState(false);
  const [items, setItems] = useState<MemoryItem[]>([]);
  const [mode, setMode] = useState<string | null>(null);
  const [selected, setSelected] = useState<MemoryDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  // null = still probing; the banner renders only on a firm false.
  const [flagOn, setFlagOn] = useState<boolean | null>(null);
  const nowMs = Date.now();

  // Debounced search: the input is instant, the fetch waits for the pause.
  useEffect(() => {
    const t = window.setTimeout(() => setQ(qInput.trim()), 300);
    return () => window.clearTimeout(t);
  }, [qInput]);

  useEffect(() => {
    api
      .settings()
      .then(({ items: settings }) => {
        const flag = settings.find((item) => item.key === "feature_memory");
        setFlagOn(flag ? flag.value === true : null);
      })
      .catch(() => setFlagOn(null));
  }, []);

  const fetchList = useCallback(() => {
    if (workspace === "all") {
      setItems([]);
      setMode(null);
      return;
    }
    const params: Record<string, string> = { workspace, limit: "50" };
    if (q) params.q = q;
    if (topic) params.topic = topic;
    if (includeSuperseded) params.include_superseded = "true";
    api
      .memories(params)
      .then((data) => {
        setItems(data.items);
        setMode(data.search_mode);
        setError(null);
      })
      .catch((exc) => setError((exc as Error).message));
  }, [workspace, q, topic, includeSuperseded]);

  useEffect(() => {
    fetchList();
  }, [fetchList]);

  // Live: debounced refetch on SSE ticks (memory.created/superseded ride the
  // workspace stream, so the list stays fresh while agents write).
  useEffect(() => {
    if (!liveTick) return;
    const t = window.setTimeout(fetchList, 500);
    return () => window.clearTimeout(t);
  }, [liveTick, fetchList]);

  const openDetail = useCallback(
    (memoryId: string) => {
      if (workspace === "all") return;
      api
        .memoryDetail(workspace, memoryId)
        .then((detail) => {
          setSelected(detail);
          setError(null);
        })
        .catch((exc) => setError((exc as Error).message));
    },
    [workspace],
  );

  const handleDelete = useCallback(() => {
    if (!selected) return;
    if (
      !window.confirm(
        `Permanently delete memory "${selected.title}"? This is physical curation - no event is emitted and it cannot be undone.`,
      )
    ) {
      return;
    }
    api
      .deleteMemory(workspace, selected.memory_id)
      .then(() => {
        setSelected(null);
        fetchList();
      })
      .catch((exc) => setError((exc as Error).message));
  }, [selected, workspace, fetchList]);

  // Topic facet derived from the DATA on screen (most frequent first).
  const topicFacet = useMemo(() => {
    const freq = new Map<string, number>();
    for (const item of items) {
      for (const t of item.topics) freq.set(t, (freq.get(t) ?? 0) + 1);
    }
    if (topic) freq.set(topic, freq.get(topic) ?? 0); // keep the active filter visible
    return [...freq.entries()]
      .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
      .slice(0, 10)
      .map(([t]) => t);
  }, [items, topic]);

  const reset = () => {
    setQInput("");
    setTopic(null);
    setIncludeSuperseded(false);
  };

  return (
    <PageContainer width="bleed" scroll="none" className="flex" testId="memory-view">
      {/* List pane */}
      <div className="flex-1 min-w-0 flex flex-col">
        <div className="shrink-0 border-b border-surface-200 dark:border-surface-700 px-4 py-3 space-y-2">
          {flagOn === false && (
            <div
              className="flex items-center gap-2 rounded-lg border border-amber-300 dark:border-amber-500/30 bg-amber-50 dark:bg-amber-900/10 px-3 py-2"
              data-testid="memory-disabled-banner"
            >
              <BrainCircuit
                size={14}
                className="text-amber-600 dark:text-amber-400 shrink-0"
              />
              <p className="text-xs text-amber-700 dark:text-amber-300">
                <b>Memory disabled</b> &mdash; the{" "}
                <code className="font-mono">feature_memory</code> flag is off, so
                agents cannot read or write memory. Existing entries stay
                browsable here. Enable it under Settings &rsaquo; Features.
              </p>
            </div>
          )}
          <div className="flex items-center gap-2 flex-wrap">
            <div className="relative w-72 max-w-full">
              <Search
                size={14}
                className="absolute left-2.5 top-1/2 -translate-y-1/2 text-surface-400"
              />
              <input
                className={`${inputCls} w-full pl-8 pr-8`}
                placeholder="Search memories&hellip;"
                value={qInput}
                onChange={(e) => setQInput(e.target.value)}
                data-testid="memory-search"
              />
              {qInput && (
                <button
                  onClick={() => setQInput("")}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-surface-400 hover:text-surface-600"
                  title="Clear search"
                >
                  <X size={14} />
                </button>
              )}
            </div>
            {mode && items.length > 0 && (
              <span
                className={`chip ${MODE_CHIP[mode] ?? MODE_CHIP.recent}`}
                title="Ranking mode declared by the server"
                data-testid="memory-mode-chip"
              >
                mode: {mode}
              </span>
            )}
            <span className="text-xs text-surface-500 dark:text-surface-400">
              {items.length} {items.length === 1 ? "entry" : "entries"}
            </span>
            <label className="ml-auto flex items-center gap-1.5 text-xs text-surface-600 dark:text-surface-300 cursor-pointer">
              <input
                type="checkbox"
                className="rounded"
                checked={includeSuperseded}
                onChange={(e) => setIncludeSuperseded(e.target.checked)}
                data-testid="memory-include-superseded"
              />
              include superseded
            </label>
          </div>
          {topicFacet.length > 0 && (
            <div className="flex items-center gap-1.5 flex-wrap">
              {topicFacet.map((t) => (
                <TopicChip
                  key={t}
                  topic={t}
                  active={topic === t}
                  onClick={() => setTopic(topic === t ? null : t)}
                />
              ))}
            </div>
          )}
          {error && (
            <p className="text-xs text-red-600 dark:text-red-400">{error}</p>
          )}
        </div>

        <div className="flex-1 overflow-y-auto" data-testid="memory-list">
          {workspace === "all" ? (
            <EmptyState text="Memory is browsed per workspace - pick one in the header." />
          ) : items.length === 0 ? (
            <EmptyState
              text={
                q || topic || includeSuperseded
                  ? "No memories match these filters."
                  : "No memories in this workspace yet. Agents write them with memory_put."
              }
              onReset={q || topic || includeSuperseded ? reset : undefined}
            />
          ) : (
            items.map((item) => (
              <MemoryRow
                key={item.memory_id}
                item={item}
                active={selected?.memory_id === item.memory_id}
                showScore={mode === "semantic"}
                nowMs={nowMs}
                onClick={() => openDetail(item.memory_id)}
              />
            ))
          )}
        </div>
      </div>

      {/* Detail pane */}
      {selected && (
        <ResizablePanel
          storageKey="okto-nexus-memory-panel"
          testId="memory-detail-panel"
        >
          <div className="flex flex-col h-full min-h-0">
            <div className="shrink-0 flex items-start justify-between gap-2 border-b border-surface-200 dark:border-surface-700 px-4 py-3">
              <div className="min-w-0">
                <h2 className="text-sm font-semibold text-surface-800 dark:text-surface-100">
                  {selected.title}
                </h2>
                <div className="mt-1 flex items-center gap-2 flex-wrap text-xs text-surface-500 dark:text-surface-400">
                  <span>
                    by <b>{selected.author_agent_id}</b>
                  </span>
                  <span>&middot;</span>
                  <span>{new Date(selected.created_at).toLocaleString()}</span>
                  <span className="rounded bg-surface-100 dark:bg-surface-700 px-1.5 font-mono">
                    {selected.memory_id}
                  </span>
                  <TraceChip traceId={selected.trace_id} onClick={onOpenTrace} />
                </div>
              </div>
              <div className="flex items-center gap-1 shrink-0">
                <button
                  onClick={handleDelete}
                  className="btn btn-danger !px-2 !py-1 text-xs inline-flex items-center gap-1"
                  title="Operator curation: physically remove this entry (no event)"
                  data-testid="memory-delete"
                >
                  <Trash2 size={13} /> Delete
                </button>
                <button
                  onClick={() => setSelected(null)}
                  className="p-1 rounded-md text-surface-400 hover:text-surface-600 hover:bg-surface-100 dark:hover:bg-surface-700"
                  title="Close"
                >
                  <X size={16} />
                </button>
              </div>
            </div>
            <div className="flex-1 min-h-0 overflow-y-auto px-4 py-3 space-y-4">
              {selected.superseded_by && (
                <div className="rounded-lg border border-surface-200 dark:border-surface-700 bg-surface-50 dark:bg-surface-800/60 px-3 py-2 text-xs text-surface-600 dark:text-surface-300">
                  This entry was superseded by{" "}
                  <button
                    className="font-mono text-accent-600 dark:text-accent-400 hover:underline"
                    onClick={() => openDetail(selected.superseded_by as string)}
                    data-testid="memory-superseded-by-link"
                  >
                    {selected.superseded_by}
                  </button>
                  .
                </div>
              )}
              <pre className="whitespace-pre-wrap rounded-lg bg-surface-50 dark:bg-surface-800/60 p-3 text-sm text-surface-700 dark:text-surface-200 font-sans">
                {selected.content}
              </pre>
              <div className="space-y-1.5 text-xs text-surface-600 dark:text-surface-300">
                {selected.source_kind && (
                  <div data-testid="memory-source">
                    <span className="font-medium">Source:</span>{" "}
                    <span className="capitalize">{selected.source_kind}</span>{" "}
                    <span className="font-mono text-surface-500 dark:text-surface-400">
                      {selected.source_id}
                    </span>
                  </div>
                )}
                {selected.supersedes && (
                  <div>
                    <span className="font-medium">Supersedes:</span>{" "}
                    <button
                      className="font-mono text-accent-600 dark:text-accent-400 hover:underline"
                      onClick={() => openDetail(selected.supersedes as string)}
                      data-testid="memory-supersedes-link"
                    >
                      {selected.supersedes}
                    </button>{" "}
                    <span className="text-surface-400">
                      (view previous version)
                    </span>
                  </div>
                )}
                {selected.topics.length > 0 && (
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <span className="font-medium">Topics:</span>
                    {selected.topics.map((t) => (
                      <TopicChip key={t} topic={t} />
                    ))}
                  </div>
                )}
                <div className="text-surface-400 dark:text-surface-500">
                  {selected.content_bytes} bytes
                </div>
              </div>
            </div>
          </div>
        </ResizablePanel>
      )}
    </PageContainer>
  );
}

function EmptyState({ text, onReset }: { text: string; onReset?: () => void }) {
  return (
    <div className="h-full flex flex-col items-center justify-center gap-3 text-surface-400 dark:text-surface-500 p-10">
      <Brain size={28} />
      <p className="text-sm text-center">{text}</p>
      {onReset && (
        <button className="btn btn-secondary" onClick={onReset}>
          Clear filters
        </button>
      )}
    </div>
  );
}

// Events screen (spec bde3a3ee): the DEFAULT mode is a server-side paged,
// filtered list (actor agent + event type + stream) with a per-event detail
// modal — mirroring MessagesView. A "Live tail" toggle flips to the realtime
// SSE feed (the previous EventsView behaviour, fed by App's eventLog buffer).
// No embeddings / semantic search (owner decision 2026-06-18).

import { useEffect, useMemo, useRef, useState } from "react";
import { Radio, RotateCw } from "lucide-react";
import { api, type AgentRow, type NexusEvent } from "../api";
import { AgentSelect } from "../components/AgentSelect";
import { TypeSelect } from "../components/TypeSelect";
import { EventDetailModal } from "../components/EventDetailModal";

const PAGE_SIZE = 25;

const STREAMS = ["", "workspace", "agent", "handoff"];

function previewPayload(payload: unknown): string {
  if (payload === null || payload === undefined || payload === "") return "";
  try {
    return typeof payload === "string" ? payload : JSON.stringify(payload);
  } catch {
    return String(payload);
  }
}

// One clickable event row, shared by the paged and live modes.
function EventRow({
  event,
  onClick,
}: {
  event: NexusEvent;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className="w-full text-left px-3 py-2 hover:bg-surface-50 dark:hover:bg-surface-800/50 transition-colors"
      data-testid="event-row"
    >
      <div className="flex items-center gap-2 flex-wrap">
        <span className="font-mono text-surface-400 dark:text-surface-600 tabular-nums">
          #{event.event_id}
        </span>
        <span className="chip bg-accent-100 text-accent-700 dark:bg-accent-900/40 dark:text-accent-300 font-mono">
          {event.type}
        </span>
        <span className="text-surface-400 dark:text-surface-500">{event.stream}</span>
        {event.actor_agent_id && (
          <span className="font-mono text-accent-600 dark:text-accent-400">
            {event.actor_agent_id}
          </span>
        )}
        <span className="ml-auto text-surface-400 dark:text-surface-500">
          {event.created_at}
        </span>
      </div>
      <div className="text-surface-500 dark:text-surface-400 mt-1 truncate font-mono">
        {previewPayload(event.payload)}
      </div>
    </button>
  );
}

export function EventsView({
  workspace,
  log,
}: {
  workspace: string;
  log: NexusEvent[];
}) {
  const [live, setLive] = useState(false);
  const [stream, setStream] = useState("");
  const [type, setType] = useState("");
  const [agent, setAgent] = useState("");
  const [agents, setAgents] = useState<AgentRow[]>([]);
  const [types, setTypes] = useState<string[]>([]);
  const [selected, setSelected] = useState<NexusEvent | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Paged mode state: `stack` holds the `after` cursor of each visited page
  // (events_after is event_id-ascending), current page = stack[last].
  const [items, setItems] = useState<NexusEvent[]>([]);
  const [nextCursor, setNextCursor] = useState(0);
  const [stack, setStack] = useState<number[]>([0]);

  // Known agents feed the actor filter; distinct types feed the type filter.
  useEffect(() => {
    api
      .agents()
      .then(({ items }) => setAgents(items))
      .catch(() => undefined);
  }, []);
  useEffect(() => {
    api
      .eventTypes(workspace === "all" ? undefined : workspace)
      .then(({ items }) => setTypes(items))
      .catch(() => undefined);
  }, [workspace]);

  const load = (after: number) => {
    const params: Record<string, string> = {
      after: String(after),
      limit: String(PAGE_SIZE),
    };
    if (workspace !== "all") params.workspace = workspace;
    if (stream) params.stream = stream;
    if (type) params.type = type;
    if (agent) params.agent = agent;
    api
      .events(params)
      .then((data) => {
        setItems(data.items);
        setNextCursor(data.next_cursor);
        setError(null);
      })
      .catch((exc) => setError((exc as Error).message));
  };

  // Any filter change (or workspace scope) resets to page 1. Only the paged
  // mode hits the server; the live mode reads the in-memory SSE buffer.
  useEffect(() => {
    if (live) return;
    setStack([0]);
    load(0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspace, stream, type, agent, live]);

  const goNext = () => {
    const c = nextCursor;
    setStack((s) => [...s, c]);
    load(c);
  };
  const goPrev = () => {
    if (stack.length <= 1) return;
    const ns = stack.slice(0, -1);
    setStack(ns);
    load(ns[ns.length - 1]);
  };

  // Live mode: the SSE buffer, with the SAME structured filters applied
  // client-side so the toggle keeps the operator's current selection.
  const liveRows = useMemo(
    () =>
      log.filter(
        (e) =>
          (workspace === "all" || e.workspace_id === workspace) &&
          (!stream || e.stream === stream) &&
          (!type || e.type === type) &&
          (!agent || e.actor_agent_id === agent),
      ),
    [log, workspace, stream, type, agent],
  );

  const endRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (live) endRef.current?.scrollIntoView({ behavior: "auto", block: "end" });
  }, [live, liveRows.length]);

  const inputCls =
    "rounded-lg border border-surface-200 dark:border-surface-700 bg-white dark:bg-surface-800 px-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-accent-500/40";

  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="max-w-5xl mx-auto space-y-3" data-testid="events-view">
        {/* Filter + mode toolbar */}
        <div className="flex items-center gap-2 text-xs flex-wrap">
          <select
            value={stream}
            onChange={(e) => setStream(e.target.value)}
            className={inputCls}
          >
            {STREAMS.map((s) => (
              <option key={s} value={s}>
                {s || "all streams"}
              </option>
            ))}
          </select>
          <TypeSelect label="Tipo" value={type} onChange={setType} types={types} />
          <AgentSelect
            label="Ator"
            value={agent}
            onChange={setAgent}
            agents={agents}
          />

          {!live ? (
            <>
              <span className="ml-auto text-surface-500">page {stack.length}</span>
              <button
                className="btn btn-secondary !px-2"
                onClick={() => load(stack[stack.length - 1])}
                title="Refresh"
              >
                <RotateCw size={14} />
              </button>
              <button
                className="btn btn-secondary"
                disabled={stack.length <= 1}
                onClick={goPrev}
              >
                ←
              </button>
              <button
                className="btn btn-secondary"
                disabled={items.length < PAGE_SIZE}
                onClick={goNext}
              >
                →
              </button>
            </>
          ) : (
            <span className="ml-auto text-surface-500">
              {liveRows.length} live events
            </span>
          )}
          <button
            className={`btn ${live ? "btn-primary" : "btn-secondary"} flex items-center gap-1`}
            onClick={() => setLive((v) => !v)}
            title="Toggle live tail (realtime SSE)"
            data-testid="live-toggle"
          >
            <Radio size={14} /> Live tail
          </button>
        </div>

        {error && <p className="text-xs text-red-500">{error}</p>}

        {/* List (paged or live) — clickable rows open the detail modal */}
        <div className="panel divide-y divide-surface-100 dark:divide-surface-700/50 text-xs">
          {(live ? liveRows : items).map((event) => (
            <EventRow
              key={event.event_id}
              event={event}
              onClick={() => setSelected(event)}
            />
          ))}
          {(live ? liveRows : items).length === 0 && (
            <div className="px-3 py-6 text-surface-400 dark:text-surface-500">
              {live
                ? "waiting for events… (any message/handoff/session writes entries)"
                : "No events for these filters."}
            </div>
          )}
          <div ref={endRef} />
        </div>
      </div>

      {selected && (
        <EventDetailModal event={selected} onClose={() => setSelected(null)} />
      )}
    </div>
  );
}

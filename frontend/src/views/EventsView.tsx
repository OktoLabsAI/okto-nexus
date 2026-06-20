// Events screen (spec bde3a3ee): a full-bleed master-detail. A sticky filter
// header (stream segmented control + type/actor + grouping + live toggle) over
// a scannable, colour-coded event stream (stream icon + left-border banding +
// category-tinted type chip + time dividers), with an inline ResizablePanel
// detail (no blocking modal). Paged mode hits the server; "Live tail" reads the
// SSE buffer newest-first and shows true connection state via LiveChip.

import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  Bot,
  Globe,
  Radio,
  RotateCw,
  Waypoints,
  type LucideIcon,
} from "lucide-react";
import { api, type AgentRow, type NexusEvent } from "../api";
import type { SSEStatus } from "../useSSE";
import { AgentSelect } from "../components/AgentSelect";
import { TypeSelect } from "../components/TypeSelect";
import { LiveChip } from "../components/LiveChip";
import { EventDetail, payloadSummary } from "../components/EventDetailModal";
import { PageContainer } from "../components/PageContainer";
import { ResizablePanel } from "../components/ResizablePanel";

const PAGE_SIZE = 25;

const STREAMS: { value: string; label: string; icon: LucideIcon }[] = [
  { value: "", label: "All", icon: Activity },
  { value: "workspace", label: "Workspace", icon: Globe },
  { value: "agent", label: "Agent", icon: Bot },
  { value: "handoff", label: "Handoff", icon: Waypoints },
];

const STREAM_META: Record<string, { icon: LucideIcon; border: string; tint: string }> = {
  workspace: {
    icon: Globe,
    border: "border-blue-400 dark:border-blue-500/60",
    tint: "text-blue-500 dark:text-blue-400",
  },
  agent: {
    icon: Bot,
    border: "border-accent-400 dark:border-accent-500/60",
    tint: "text-accent-500 dark:text-accent-400",
  },
  handoff: {
    icon: Waypoints,
    border: "border-violet-400 dark:border-violet-500/60",
    tint: "text-violet-500 dark:text-violet-400",
  },
};
const DEFAULT_META = {
  icon: Activity,
  border: "border-surface-300 dark:border-surface-600",
  tint: "text-surface-400 dark:text-surface-500",
};

function typeChip(type: string): string {
  if (type.startsWith("message."))
    return "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300";
  if (type.startsWith("handoff."))
    return "bg-violet-100 text-violet-700 dark:bg-violet-900/40 dark:text-violet-300";
  if (type.startsWith("session."))
    return "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300";
  return "bg-accent-100 text-accent-700 dark:bg-accent-900/40 dark:text-accent-300";
}

function relBucket(iso: string, nowMs: number): string {
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return "—";
  const s = Math.max(0, (nowMs - t) / 1000);
  if (s < 60) return "Just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return new Date(iso).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  });
}

const inputCls =
  "rounded-lg border border-surface-200 dark:border-surface-700 bg-white dark:bg-surface-800 px-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-accent-500/40";

function EventRow({
  event,
  active,
  onClick,
}: {
  event: NexusEvent;
  active: boolean;
  onClick: () => void;
}) {
  const meta = STREAM_META[event.stream] ?? DEFAULT_META;
  const Icon = meta.icon;
  const summary = payloadSummary(event);
  return (
    <button
      onClick={onClick}
      className={`w-full text-left px-3 py-2 border-l-2 transition-colors ${meta.border} ${
        active
          ? "bg-accent-50 dark:bg-accent-900/20"
          : "hover:bg-surface-50 dark:hover:bg-surface-800/50"
      }`}
      data-testid="event-row"
    >
      <div className="flex items-center gap-2 flex-wrap text-xs">
        <Icon size={13} className={`shrink-0 ${meta.tint}`} />
        <span className="font-mono text-surface-400 dark:text-surface-600 tabular-nums">
          #{event.event_id}
        </span>
        <span className={`chip font-mono ${typeChip(event.type)}`}>{event.type}</span>
        {event.actor_agent_id && (
          <span className="font-mono text-accent-600 dark:text-accent-400">
            {event.actor_agent_id}
          </span>
        )}
        <span className="ml-auto text-surface-400 dark:text-surface-500">
          {event.created_at}
        </span>
      </div>
      {summary.length > 0 && (
        <div className="mt-1 flex flex-wrap gap-1 pl-5">
          {summary.slice(0, 4).map(([k, v]) => (
            <span
              key={k}
              className="text-[11px] font-mono text-surface-500 dark:text-surface-400"
            >
              {k}=<span className="text-surface-700 dark:text-surface-300">{v}</span>
            </span>
          ))}
        </div>
      )}
    </button>
  );
}

export function EventsView({
  workspace,
  log,
  sseStatus,
}: {
  workspace: string;
  log: NexusEvent[];
  liveTick?: number;
  sseStatus?: SSEStatus;
}) {
  const [live, setLive] = useState(false);
  const [stream, setStream] = useState("");
  const [type, setType] = useState("");
  const [agent, setAgent] = useState("");
  const [grouped, setGrouped] = useState(true);
  const [agents, setAgents] = useState<AgentRow[]>([]);
  const [types, setTypes] = useState<string[]>([]);
  const [selected, setSelected] = useState<NexusEvent | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Paged mode: `stack` holds the `after` cursor of each visited page.
  const [items, setItems] = useState<NexusEvent[]>([]);
  const [nextCursor, setNextCursor] = useState(0);
  const [stack, setStack] = useState<number[]>([0]);

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

  // Live mode: the SSE buffer, filtered client-side, NEWEST-FIRST so fresh
  // events appear at the top without disturbing the reader's scroll.
  const liveRows = useMemo(
    () =>
      log
        .filter(
          (e) =>
            (workspace === "all" || e.workspace_id === workspace) &&
            (!stream || e.stream === stream) &&
            (!type || e.type === type) &&
            (!agent || e.actor_agent_id === agent),
        )
        .slice()
        .reverse(),
    [log, workspace, stream, type, agent],
  );

  const rows = live ? liveRows : items;

  // Build rows with time-bucket dividers (newest-relative).
  const body = useMemo(() => {
    if (rows.length === 0) return null;
    const nowMs = Date.now();
    const out: { divider?: string; event?: NexusEvent; key: string }[] = [];
    let last = "";
    for (const e of rows) {
      if (grouped) {
        const b = relBucket(e.created_at, nowMs);
        if (b !== last) {
          last = b;
          out.push({ divider: b, key: `d-${e.event_id}` });
        }
      }
      out.push({ event: e, key: String(e.event_id) });
    }
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows, grouped]);

  const segActive = (val: string) =>
    stream === val
      ? "bg-accent-100 text-accent-700 dark:bg-accent-900/50 dark:text-accent-200"
      : "text-surface-500 hover:bg-surface-100 dark:hover:bg-surface-800";

  return (
    <PageContainer width="bleed" scroll="none" className="flex" testId="events-view">
      <div className="flex-1 min-w-0 flex flex-col">
        {/* Sticky filter header */}
        <div className="shrink-0 border-b border-surface-200/60 dark:border-surface-700/60 bg-white/80 dark:bg-surface-900/80 backdrop-blur-md px-4 py-3 space-y-2">
          <div className="flex items-center gap-2 flex-wrap text-xs">
            <div className="flex items-center rounded-lg border border-surface-200 dark:border-surface-700 overflow-hidden">
              {STREAMS.map((s) => {
                const Icon = s.icon;
                return (
                  <button
                    key={s.value}
                    onClick={() => setStream(s.value)}
                    className={`flex items-center gap-1 px-2.5 py-1 ${segActive(s.value)}`}
                    data-testid={`stream-${s.value || "all"}`}
                  >
                    <Icon size={13} /> {s.label}
                  </button>
                );
              })}
            </div>
            <TypeSelect label="Type" value={type} onChange={setType} types={types} />
            <AgentSelect label="Actor" value={agent} onChange={setAgent} agents={agents} />

            <button
              className="flex items-center rounded-lg border border-surface-200 dark:border-surface-700 overflow-hidden"
              onClick={() => setGrouped((g) => !g)}
              title="Toggle time grouping"
            >
              <span
                className={`px-2.5 py-1 ${
                  grouped
                    ? "bg-accent-100 text-accent-700 dark:bg-accent-900/50 dark:text-accent-200"
                    : "text-surface-500"
                }`}
              >
                Time
              </span>
              <span
                className={`px-2.5 py-1 ${
                  !grouped
                    ? "bg-accent-100 text-accent-700 dark:bg-accent-900/50 dark:text-accent-200"
                    : "text-surface-500"
                }`}
              >
                Flat
              </span>
            </button>

            {sseStatus && <LiveChip status={sseStatus} />}

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
                  className="btn btn-secondary !px-2"
                  disabled={stack.length <= 1}
                  onClick={goPrev}
                >
                  ←
                </button>
                <button
                  className="btn btn-secondary !px-2"
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
        </div>

        {/* Event stream */}
        <div className="flex-1 overflow-y-auto" data-testid="events-list">
          {body === null ? (
            <div className="h-full flex flex-col items-center justify-center gap-3 text-surface-400 dark:text-surface-500 p-10">
              <Activity size={28} />
              <p className="text-sm">
                {live
                  ? "Waiting for events… (any message / handoff / session write appears here)"
                  : "No events match these filters."}
              </p>
            </div>
          ) : (
            body.map((item) =>
              item.divider !== undefined ? (
                <div
                  key={item.key}
                  className="sticky top-0 z-[1] px-3 py-1 text-[10px] uppercase tracking-wider text-surface-400 dark:text-surface-500 bg-surface-50/90 dark:bg-surface-900/90 backdrop-blur-sm border-b border-surface-100 dark:border-surface-800"
                >
                  {item.divider}
                </div>
              ) : (
                <EventRow
                  key={item.key}
                  event={item.event!}
                  active={selected?.event_id === item.event!.event_id}
                  onClick={() => setSelected(item.event!)}
                />
              ),
            )
          )}
        </div>
      </div>

      {/* Inline detail */}
      {selected && (
        <ResizablePanel
          storageKey="okto-nexus-events-panel"
          testId="event-detail-panel"
        >
          <EventDetail event={selected} onClose={() => setSelected(null)} />
        </ResizablePanel>
      )}
    </PageContainer>
  );
}

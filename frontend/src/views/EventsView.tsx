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
  Download,
  Globe,
  Radio,
  RotateCw,
  Route,
  Waypoints,
  X,
  type LucideIcon,
} from "lucide-react";
import {
  api,
  type AgentRow,
  type EventTimeline,
  type NexusEvent,
} from "../api";
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

function localDateTime(date: Date): string {
  const offset = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
}

function isoDate(value: string): string | null {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date.toISOString();
}

function hasRecipient(event: NexusEvent, recipient: string): boolean {
  if (!recipient) return true;
  const records = [event.target, event.payload].filter(
    (value): value is Record<string, unknown> =>
      !!value && typeof value === "object" && !Array.isArray(value),
  );
  return records.some((record) => {
    if (record.agent_id === recipient || record.to_agent_id === recipient) return true;
    if (record.recipient_agent_id === recipient) return true;
    return Array.isArray(record.recipients) && record.recipients.includes(recipient);
  });
}

const CHART_COLORS = [
  "#8b5cf6",
  "#0ea5e9",
  "#10b981",
  "#f59e0b",
  "#ef4444",
  "#ec4899",
  "#64748b",
];

function curvePath(points: { x: number; y: number }[]): string {
  if (!points.length) return "";
  if (points.length === 1) return `M ${points[0].x} ${points[0].y}`;
  let path = `M ${points[0].x} ${points[0].y}`;
  for (let index = 1; index < points.length; index += 1) {
    const previous = points[index - 1];
    const point = points[index];
    const middle = (previous.x + point.x) / 2;
    path += ` C ${middle} ${previous.y}, ${middle} ${point.y}, ${point.x} ${point.y}`;
  }
  return path;
}

function TimelineChart({ timeline }: { timeline: EventTimeline }) {
  const [hovered, setHovered] = useState<number | null>(null);
  const width = 900;
  const height = 300;
  const pad = { left: 44, right: 18, top: 18, bottom: 34 };
  const plotWidth = width - pad.left - pad.right;
  const plotHeight = height - pad.top - pad.bottom;
  const totals = timeline.types
    .map((type) => ({
      type,
      count: timeline.buckets.reduce(
        (total, bucket) => total + (bucket.by_type[type] ?? 0),
        0,
      ),
    }))
    .sort((a, b) => b.count - a.count)
    .slice(0, CHART_COLORS.length);
  const max = Math.max(
    1,
    ...timeline.buckets.flatMap((bucket) => [
      bucket.total,
      ...totals.map(({ type }) => bucket.by_type[type] ?? 0),
    ]),
  );
  const x = (index: number) =>
    pad.left +
    (timeline.buckets.length <= 1
      ? plotWidth / 2
      : (index / (timeline.buckets.length - 1)) * plotWidth);
  const y = (value: number) => pad.top + plotHeight - (value / max) * plotHeight;
  const totalPoints = timeline.buckets.map((bucket, index) => ({
    x: x(index),
    y: y(bucket.total),
  }));
  const totalPath = curvePath(totalPoints);
  const areaPath = totalPoints.length
    ? `${totalPath} L ${totalPoints.at(-1)!.x} ${pad.top + plotHeight} L ${totalPoints[0].x} ${pad.top + plotHeight} Z`
    : "";
  const hoverBucket = hovered === null ? null : timeline.buckets[hovered];

  if (timeline.total === 0) {
    return (
      <div className="h-full min-h-[300px] flex flex-col items-center justify-center gap-2 text-surface-400 dark:text-surface-500">
        <Activity size={28} />
        <p className="text-sm">No events in this range.</p>
      </div>
    );
  }

  return (
    <div className="h-full min-h-0 overflow-y-auto p-4 space-y-3" data-testid="events-timeline">
      <div className="panel p-4">
        <div className="flex items-start gap-4 flex-wrap mb-3">
          <div>
            <div className="text-2xl font-semibold text-surface-900 dark:text-white tabular-nums">
              {timeline.total.toLocaleString()}
            </div>
            <div className="text-[11px] text-surface-500 dark:text-surface-400">events in range</div>
          </div>
          <div className="flex-1 flex flex-wrap justify-end gap-1.5">
            {totals.map((series, index) => (
              <span key={series.type} className="chip bg-surface-100 dark:bg-surface-800 text-surface-600 dark:text-surface-300">
                <span className="w-2 h-2 rounded-full" style={{ backgroundColor: CHART_COLORS[index] }} />
                {series.type} · {series.count}
              </span>
            ))}
          </div>
        </div>
        <div className="relative w-full" style={{ aspectRatio: `${width}/${height}`, minHeight: 250 }}>
          <svg
            viewBox={`0 0 ${width} ${height}`}
            className="absolute inset-0 w-full h-full overflow-visible"
            onMouseLeave={() => setHovered(null)}
            onMouseMove={(event) => {
              const rect = event.currentTarget.getBoundingClientRect();
              const relative = ((event.clientX - rect.left) / rect.width) * width;
              const ratio = Math.max(0, Math.min(1, (relative - pad.left) / plotWidth));
              setHovered(Math.round(ratio * Math.max(0, timeline.buckets.length - 1)));
            }}
          >
            <defs>
              <linearGradient id="event-total-area" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#8b5cf6" stopOpacity="0.22" />
                <stop offset="100%" stopColor="#8b5cf6" stopOpacity="0" />
              </linearGradient>
            </defs>
            {[0, 0.5, 1].map((ratio) => {
              const lineY = pad.top + plotHeight * ratio;
              return (
                <g key={ratio}>
                  <line x1={pad.left} y1={lineY} x2={width - pad.right} y2={lineY} stroke="currentColor" className="text-surface-200 dark:text-surface-800" strokeWidth="1" />
                  <text x={pad.left - 8} y={lineY + 3} textAnchor="end" className="fill-surface-400 dark:fill-surface-500 text-[10px]">
                    {Math.round(max * (1 - ratio))}
                  </text>
                </g>
              );
            })}
            <path d={areaPath} fill="url(#event-total-area)" />
            <path d={totalPath} fill="none" stroke="#8b5cf6" strokeOpacity="0.35" strokeWidth="5" />
            {totals.map(({ type }, seriesIndex) => {
              const points = timeline.buckets.map((bucket, index) => ({
                x: x(index),
                y: y(bucket.by_type[type] ?? 0),
              }));
              return (
                <path key={type} d={curvePath(points)} fill="none" stroke={CHART_COLORS[seriesIndex]} strokeWidth="2.2" />
              );
            })}
            {hovered !== null && (
              <line x1={x(hovered)} y1={pad.top} x2={x(hovered)} y2={pad.top + plotHeight} stroke="#94a3b8" strokeDasharray="3 3" />
            )}
            <text x={pad.left} y={height - 8} className="fill-surface-400 dark:fill-surface-500 text-[10px]">
              {new Date(timeline.since).toLocaleString()}
            </text>
            <text x={width - pad.right} y={height - 8} textAnchor="end" className="fill-surface-400 dark:fill-surface-500 text-[10px]">
              {new Date(timeline.until).toLocaleString()}
            </text>
          </svg>
          {hoverBucket && hovered !== null && (
            <div
              className="absolute z-10 pointer-events-none min-w-[190px] rounded-lg border border-surface-200 dark:border-surface-700 bg-white dark:bg-surface-800 shadow-xl p-2 text-[10px]"
              style={{ left: `${(x(hovered) / width) * 100}%`, top: 12, transform: hovered > timeline.buckets.length / 2 ? "translateX(-100%)" : undefined }}
            >
              <div className="font-medium text-surface-700 dark:text-surface-200 mb-1">
                {new Date(hoverBucket.bucket_start).toLocaleString()}
              </div>
              {totals.map(({ type }, index) => (
                <div key={type} className="flex items-center justify-between gap-3 text-surface-500 dark:text-surface-400">
                  <span className="flex items-center gap-1 truncate"><span className="w-2 h-2 rounded-full" style={{ backgroundColor: CHART_COLORS[index] }} />{type}</span>
                  <b className="text-surface-700 dark:text-surface-200">{hoverBucket.by_type[type] ?? 0}</b>
                </div>
              ))}
              <div className="mt-1 pt-1 border-t border-surface-200 dark:border-surface-700 flex justify-between font-medium"><span>Total</span><span>{hoverBucket.total}</span></div>
            </div>
          )}
        </div>
      </div>
      {timeline.types.length > CHART_COLORS.length && (
        <p className="text-[10px] text-surface-400 dark:text-surface-500">
          Showing the {CHART_COLORS.length} most frequent event types. The total curve includes every type.
        </p>
      )}
    </div>
  );
}

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
  trace,
  onTraceChange,
}: {
  workspace: string;
  log: NexusEvent[];
  liveTick?: number;
  sseStatus?: SSEStatus;
  // Trajectory filter (R-I1). Lifted to the App shell so a TraceChip click on
  // ANY screen can land here with the filter already applied.
  trace: string;
  onTraceChange: (trace: string) => void;
}) {
  const [live, setLive] = useState(false);
  const [viewMode, setViewMode] = useState<"list" | "timeline">("list");
  const [stream, setStream] = useState("");
  const [type, setType] = useState("");
  const [agent, setAgent] = useState("");
  const [recipient, setRecipient] = useState("");
  const [since, setSince] = useState(() =>
    localDateTime(new Date(Date.now() - 24 * 60 * 60 * 1000)),
  );
  const [until, setUntil] = useState(() => localDateTime(new Date()));
  const [intervalValue, setIntervalValue] = useState("1");
  const [intervalUnit, setIntervalUnit] = useState<"minutes" | "hours" | "days">("hours");
  const [grouped, setGrouped] = useState(true);
  const [agents, setAgents] = useState<AgentRow[]>([]);
  const [types, setTypes] = useState<string[]>([]);
  const [selected, setSelected] = useState<NexusEvent | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [timeline, setTimeline] = useState<EventTimeline | null>(null);
  const [timelineLoading, setTimelineLoading] = useState(false);
  // I8 replay/export: self-gated on the live feature_replay flag (defense in
  // depth with the endpoint gate). default_workspace_id lets the "all" view
  // still export the serve's primary workspace.
  const [replayEnabled, setReplayEnabled] = useState(false);
  const [defaultWorkspace, setDefaultWorkspace] = useState<string | null>(null);

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
  useEffect(() => {
    api
      .info()
      .then((info) => {
        setReplayEnabled(Boolean(info.features?.feature_replay));
        setDefaultWorkspace(info.default_workspace_id ?? null);
      })
      .catch(() => undefined);
  }, []);

  // The export always targets a CONCRETE workspace; on the "all" view fall back
  // to the serve's default workspace (null -> button hidden).
  const exportWorkspace = workspace !== "all" ? workspace : defaultWorkspace;
  const runExport = (params: Record<string, string>) => {
    if (!exportWorkspace) return;
    api
      .exportEventLog(exportWorkspace, params)
      .catch((exc) => setError((exc as Error).message));
  };

  const load = (after: number) => {
    const params: Record<string, string> = {
      after: String(after),
      limit: String(PAGE_SIZE),
    };
    if (workspace !== "all") params.workspace = workspace;
    if (stream) params.stream = stream;
    if (type) params.type = type;
    if (agent) params.agent = agent;
    if (recipient) params.recipient = recipient;
    if (trace) params.trace = trace;
    const sinceIso = isoDate(since);
    const untilIso = isoDate(until);
    if (sinceIso && untilIso && sinceIso > untilIso) {
      setItems([]);
      setError("The end of the range must be after its start.");
      return;
    }
    if (sinceIso) params.since = sinceIso;
    if (untilIso) params.until = untilIso;
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
    if (live || viewMode !== "list") return;
    setStack([0]);
    load(0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspace, stream, type, agent, recipient, trace, live, viewMode, since, until]);

  useEffect(() => {
    if (viewMode !== "timeline") return;
    const sinceIso = isoDate(since);
    const untilIso = isoDate(until);
    if (!sinceIso || !untilIso || sinceIso > untilIso) {
      setTimeline(null);
      setError("The end of the range must be after its start.");
      return;
    }
    const multipliers = { minutes: 60, hours: 3600, days: 86400 };
    const bucketSeconds =
      Math.max(1, Number.parseInt(intervalValue, 10) || 1) * multipliers[intervalUnit];
    const params: Record<string, string> = {
      since: sinceIso,
      until: untilIso,
      bucket_seconds: String(bucketSeconds),
    };
    if (workspace !== "all") params.workspace = workspace;
    if (stream) params.stream = stream;
    if (type) params.type = type;
    if (agent) params.agent = agent;
    if (recipient) params.recipient = recipient;
    if (trace) params.trace = trace;
    setTimelineLoading(true);
    api
      .eventTimeline(params)
      .then((data) => {
        setTimeline(data);
        setError(null);
      })
      .catch((exc) => {
        setTimeline(null);
        setError((exc as Error).message);
      })
      .finally(() => setTimelineLoading(false));
  }, [workspace, stream, type, agent, recipient, trace, viewMode, since, until, intervalValue, intervalUnit]);

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
            (!agent || e.actor_agent_id === agent) &&
            hasRecipient(e, recipient) &&
            (!isoDate(since) || new Date(e.created_at).getTime() >= new Date(since).getTime()) &&
            (!isoDate(until) || new Date(e.created_at).getTime() <= new Date(until).getTime()) &&
            (!trace || e.trace_id === trace),
        )
        .slice()
        .reverse(),
    [log, workspace, stream, type, agent, recipient, trace, since, until],
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
              {(["list", "timeline"] as const).map((mode) => (
                <button
                  key={mode}
                  className={`px-2.5 py-1 capitalize ${
                    viewMode === mode
                      ? "bg-accent-100 text-accent-700 dark:bg-accent-900/50 dark:text-accent-200"
                      : "text-surface-500 hover:bg-surface-100 dark:hover:bg-surface-800"
                  }`}
                  onClick={() => {
                    setViewMode(mode);
                    if (mode === "timeline") setLive(false);
                  }}
                  data-testid={`events-mode-${mode}`}
                >
                  {mode}
                </button>
              ))}
            </div>
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
            <AgentSelect label="Sender" value={agent} onChange={setAgent} agents={agents} />
            <AgentSelect label="Recipient" value={recipient} onChange={setRecipient} agents={agents} />
            {trace && (
              <span
                className="flex items-center gap-1 rounded-lg border border-violet-200 dark:border-violet-800/60 bg-violet-50 dark:bg-violet-900/30 text-violet-700 dark:text-violet-300 pl-2 pr-1 py-1 font-mono"
                data-testid="trace-filter-pill"
              >
                <Route size={12} className="shrink-0" />
                <span className="max-w-[160px] truncate" title={trace}>
                  {trace}
                </span>
                <button
                  onClick={() => onTraceChange("")}
                  className="p-0.5 rounded hover:bg-violet-100 dark:hover:bg-violet-900/60 transition-colors"
                  title="Clear trace filter"
                  data-testid="trace-filter-clear"
                >
                  <X size={12} />
                </button>
              </span>
            )}

            {viewMode === "list" && <button
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
            </button>}

            {sseStatus && <LiveChip status={sseStatus} />}

            {viewMode === "list" && !live ? (
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
            ) : viewMode === "list" ? (
              <span className="ml-auto text-surface-500">
                {liveRows.length} live events
              </span>
            ) : <span className="ml-auto text-surface-500">{timeline?.total ?? 0} events</span>}
            {replayEnabled && exportWorkspace && (
              <>
                <button
                  className="btn btn-secondary flex items-center gap-1"
                  onClick={() => runExport(stream ? { stream } : {})}
                  title="Download the workspace event log as NDJSON (replay/eval)"
                  data-testid="export-log"
                >
                  <Download size={14} /> Export event log (NDJSON)
                </button>
                {trace && (
                  <button
                    className="btn btn-secondary flex items-center gap-1"
                    onClick={() => runExport({ trace })}
                    title="Download just this trace as NDJSON"
                    data-testid="export-trace"
                  >
                    <Download size={14} /> Export this trace
                  </button>
                )}
              </>
            )}
            {viewMode === "list" && <button
              className={`btn ${live ? "btn-primary" : "btn-secondary"} flex items-center gap-1`}
              onClick={() => setLive((v) => !v)}
              title="Toggle live tail (realtime SSE)"
              data-testid="live-toggle"
            >
              <Radio size={14} /> Live tail
            </button>}
          </div>
          <div className="flex items-end gap-2 flex-wrap text-xs">
            <label className="text-[10px] uppercase tracking-wide text-surface-400 dark:text-surface-500">
              From
              <input
                type="datetime-local"
                value={since}
                onChange={(event) => setSince(event.target.value)}
                className={`${inputCls} block mt-1 normal-case`}
                data-testid="events-since"
              />
            </label>
            <label className="text-[10px] uppercase tracking-wide text-surface-400 dark:text-surface-500">
              To
              <input
                type="datetime-local"
                value={until}
                onChange={(event) => setUntil(event.target.value)}
                className={`${inputCls} block mt-1 normal-case`}
                data-testid="events-until"
              />
            </label>
            {viewMode === "timeline" && (
              <label className="text-[10px] uppercase tracking-wide text-surface-400 dark:text-surface-500">
                Interval
                <span className="flex mt-1">
                  <input
                    type="number"
                    min={1}
                    max={1440}
                    value={intervalValue}
                    onChange={(event) => setIntervalValue(event.target.value)}
                    className={`${inputCls} w-16 rounded-r-none normal-case`}
                    aria-label="Interval value"
                  />
                  <select
                    value={intervalUnit}
                    onChange={(event) => setIntervalUnit(event.target.value as typeof intervalUnit)}
                    className={`${inputCls} rounded-l-none border-l-0 normal-case`}
                    aria-label="Interval unit"
                  >
                    <option value="minutes">minutes</option>
                    <option value="hours">hours</option>
                    <option value="days">days</option>
                  </select>
                </span>
              </label>
            )}
            <button
              className="btn btn-secondary"
              onClick={() => {
                setSince(localDateTime(new Date(Date.now() - 24 * 60 * 60 * 1000)));
                setUntil(localDateTime(new Date()));
                setRecipient("");
                setAgent("");
                setType("");
              }}
            >
              Reset range & filters
            </button>
          </div>
          {trace && (
            <div
              className="flex items-center gap-2 text-[11px] text-violet-600 dark:text-violet-300"
              data-testid="trace-count-header"
            >
              <Route size={12} className="shrink-0" />
              <span className="font-mono truncate" title={trace}>
                {trace}
              </span>
              <span className="text-surface-400 dark:text-surface-500">
                · {rows.length} event{rows.length === 1 ? "" : "s"}{" "}
                {live ? "in live buffer" : "on this page"}
              </span>
            </div>
          )}
          {error && <p className="text-xs text-red-500">{error}</p>}
        </div>

        {/* Event stream / distribution timeline */}
        {viewMode === "timeline" ? (
          <div className="flex-1 min-h-0">
            {timelineLoading && !timeline ? (
              <div className="h-full flex items-center justify-center text-sm text-surface-400">Loading timeline…</div>
            ) : timeline ? (
              <TimelineChart timeline={timeline} />
            ) : null}
          </div>
        ) : <div className="flex-1 overflow-y-auto" data-testid="events-list">
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
        </div>}
      </div>

      {/* Inline detail */}
      {selected && viewMode === "list" && (
        <ResizablePanel
          storageKey="okto-nexus-events-panel"
          testId="event-detail-panel"
        >
          <EventDetail
            event={selected}
            onClose={() => setSelected(null)}
            onOpenTrace={onTraceChange}
          />
        </ResizablePanel>
      )}
    </PageContainer>
  );
}

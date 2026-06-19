// Workspaces panel (spec bf6e06dc): a first-class operator view of each
// workspace — identity + presence + activity + health (overview) — plus a
// message-distribution analytics surface (volume x size-in-TOKENS over time,
// broken down by sender). Read-only MVP. All copy is English.

import { useCallback, useEffect, useMemo, useState } from "react";
import { FolderOpen, RotateCw } from "lucide-react";
import {
  api,
  type AnalyticsWindow,
  type SessionRow,
  type WorkspaceAnalytics,
  type WorkspaceListItem,
} from "../api";

const WINDOWS: AnalyticsWindow[] = ["24h", "7d", "30d"];
const AUTO_REFRESH_MS = 15_000;
const OTHERS = "others";

// Stable per-series colours (top-8 agents + a grey "others"); inline styles so
// Tailwind's purge never drops a dynamically-built class.
const SERIES_COLORS = [
  "#818cf8", "#34d399", "#fbbf24", "#a78bfa",
  "#f472b6", "#22d3ee", "#fb923c", "#4ade80",
];
const OTHERS_COLOR = "#94a3b8";

function compact(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(n >= 10_000_000 ? 0 : 1) + "M";
  if (n >= 1_000) return (n / 1_000).toFixed(n >= 10_000 ? 0 : 1) + "K";
  return String(Math.round(n));
}

function shortTime(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function bucketLabel(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleString(undefined, { hour: "2-digit", minute: "2-digit" });
}

export function WorkspacesView({
  scope,
  refreshTick,
}: {
  scope?: string;
  refreshTick?: number;
}) {
  const [list, setList] = useState<WorkspaceListItem[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [windowSel, setWindowSel] = useState<AnalyticsWindow>("24h");
  const [metric, setMetric] = useState<"volume" | "tokens">("volume");
  const [analytics, setAnalytics] = useState<WorkspaceAnalytics | null>(null);
  const [roster, setRoster] = useState<SessionRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  // Light auto-refresh: snapshot + poll (NOT SSE per message).
  useEffect(() => {
    const id = window.setInterval(() => setTick((t) => t + 1), AUTO_REFRESH_MS);
    return () => window.clearInterval(id);
  }, []);

  const loadList = useCallback(async () => {
    try {
      const { workspaces } = await api.workspaces();
      setList(workspaces);
      setError(null);
      setSelected((cur) => {
        if (cur && workspaces.some((w) => w.workspace_id === cur)) return cur;
        const scoped =
          scope && scope !== "all"
            ? workspaces.find((w) => w.workspace_id === scope)
            : undefined;
        return (
          scoped?.workspace_id ??
          workspaces.find((w) => w.is_default)?.workspace_id ??
          workspaces[0]?.workspace_id ??
          null
        );
      });
    } catch (exc) {
      setError((exc as Error).message);
    }
  }, [scope]);

  useEffect(() => {
    loadList();
  }, [loadList, refreshTick, tick]);

  useEffect(() => {
    if (!selected) {
      setAnalytics(null);
      setRoster([]);
      return;
    }
    let alive = true;
    api
      .workspaceAnalytics(selected, windowSel)
      .then((a) => alive && setAnalytics(a))
      .catch(() => alive && setAnalytics(null));
    api
      .sessions(selected)
      .then(({ items }) => alive && setRoster(items))
      .catch(() => alive && setRoster([]));
    return () => {
      alive = false;
    };
  }, [selected, windowSel, refreshTick, tick]);

  const current = useMemo(
    () => list.find((w) => w.workspace_id === selected) ?? null,
    [list, selected],
  );

  if (list.length === 0) {
    return (
      <div className="h-full overflow-y-auto p-6">
        <div className="max-w-3xl mx-auto" data-testid="workspaces-view">
          <div className="panel px-4 py-10 text-center text-sm text-surface-400 dark:text-surface-500">
            {error
              ? `Could not load workspaces: ${error}`
              : "No workspaces yet — they appear as agents coordinate through the bus."}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto p-5" data-testid="workspaces-view">
      <div className="max-w-6xl mx-auto grid grid-cols-1 lg:grid-cols-[260px_1fr] gap-4">
        {/* Workspace selector */}
        <aside className="panel p-2 h-fit">
          <div className="px-2 py-1.5 text-[11px] font-medium uppercase tracking-wider text-surface-400 dark:text-surface-500">
            Workspaces ({list.length})
          </div>
          <ul className="space-y-0.5">
            {list.map((w) => {
              const active = w.workspace_id === selected;
              return (
                <li key={w.workspace_id}>
                  <button
                    onClick={() => setSelected(w.workspace_id)}
                    className={`w-full text-left px-2.5 py-2 rounded-lg transition-colors ${
                      active
                        ? "bg-accent-100 text-accent-700 dark:bg-accent-900/60 dark:text-accent-200"
                        : "hover:bg-surface-100 dark:hover:bg-surface-800 text-surface-700 dark:text-surface-300"
                    }`}
                  >
                    <div className="flex items-center gap-1.5">
                      <FolderOpen size={13} className="shrink-0 opacity-70" />
                      <span className="truncate text-xs font-medium">
                        {w.display_name || w.workspace_id.slice(0, 14) + "…"}
                      </span>
                      {w.is_default && (
                        <span className="ml-auto text-[9px] uppercase rounded bg-surface-200 dark:bg-surface-700 px-1 py-0.5">
                          default
                        </span>
                      )}
                    </div>
                    <div className="mt-1 flex items-center gap-2 text-[10px] text-surface-500 dark:text-surface-400">
                      <span>{w.message_count} msgs / 24h</span>
                      <PresenceDots presence={w.presence} />
                    </div>
                  </button>
                </li>
              );
            })}
          </ul>
        </aside>

        <main className="space-y-4">
          {current && (
            <OverviewCard ws={current} roster={roster} analytics={analytics} />
          )}

          {/* Analytics header / controls */}
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <div>
              <h2 className="text-sm font-semibold text-surface-800 dark:text-surface-100">
                Message distribution
              </h2>
              <p className="text-[11px] text-surface-400 dark:text-surface-500">
                by sender · size in tokens (o200k_base)
                {analytics?.truncated
                  ? ` · sampled most-recent ${analytics.scanned_messages}`
                  : ""}
              </p>
            </div>
            <div className="flex items-center gap-2 text-xs">
              <Toggle
                options={[
                  ["volume", "Volume"],
                  ["tokens", "Tokens"],
                ]}
                value={metric}
                onChange={(v) => setMetric(v as "volume" | "tokens")}
              />
              <Toggle
                options={WINDOWS.map((w) => [w, w] as [string, string])}
                value={windowSel}
                onChange={(v) => setWindowSel(v as AnalyticsWindow)}
              />
              <button
                className="btn btn-secondary !px-2"
                onClick={() => setTick((t) => t + 1)}
                title="Refresh"
              >
                <RotateCw size={13} />
              </button>
            </div>
          </div>

          {analytics ? (
            <AnalyticsBody analytics={analytics} metric={metric} />
          ) : (
            <div className="panel px-4 py-8 text-center text-xs text-surface-400 dark:text-surface-500">
              Loading analytics…
            </div>
          )}
        </main>
      </div>
    </div>
  );
}

function PresenceDots({
  presence,
}: {
  presence: { present: number; stale: number; offline: number };
}) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <Dot color="#22c55e" n={presence.present} title="present" />
      <Dot color="#f59e0b" n={presence.stale} title="stale" />
      <Dot color="#94a3b8" n={presence.offline} title="offline" />
    </span>
  );
}

function Dot({ color, n, title }: { color: string; n: number; title: string }) {
  return (
    <span className="inline-flex items-center gap-0.5" title={`${n} ${title}`}>
      <span
        className="inline-block h-2 w-2 rounded-full"
        style={{ backgroundColor: color }}
      />
      {n}
    </span>
  );
}

function Toggle({
  options,
  value,
  onChange,
}: {
  options: [string, string][];
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <div className="flex rounded-lg border border-surface-200 dark:border-surface-700 overflow-hidden">
      {options.map(([val, label]) => (
        <button
          key={val}
          onClick={() => onChange(val)}
          className={`px-2.5 py-1 ${
            value === val
              ? "bg-accent-100 text-accent-700 dark:bg-accent-900/60 dark:text-accent-200 font-medium"
              : "text-surface-500 dark:text-surface-400 hover:bg-surface-100 dark:hover:bg-surface-800"
          }`}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

function OverviewCard({
  ws,
  roster,
  analytics,
}: {
  ws: WorkspaceListItem;
  roster: SessionRow[];
  analytics: WorkspaceAnalytics | null;
}) {
  const present = roster.filter((s) => s.presence === "present");
  const topAgent = analytics?.agents[0]?.agent_id ?? "—";
  return (
    <div className="panel p-4 space-y-4">
      {/* Identity */}
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-base font-semibold text-surface-800 dark:text-surface-100">
              {ws.display_name || ws.workspace_id}
            </h1>
            {ws.is_default && (
              <span className="text-[9px] uppercase rounded bg-surface-200 dark:bg-surface-700 px-1.5 py-0.5">
                default
              </span>
            )}
          </div>
          <div className="mt-0.5 font-mono text-[11px] text-surface-400 dark:text-surface-500">
            {ws.workspace_id}
          </div>
          <div className="mt-0.5 text-[11px] text-surface-500 dark:text-surface-400">
            {ws.path_redacted ? (
              <span className="italic">path hidden</span>
            ) : (
              <span className="font-mono">{ws.root_realpath || "—"}</span>
            )}
          </div>
        </div>
        <div className="text-right text-[11px] text-surface-500 dark:text-surface-400 space-y-0.5">
          <div>created {shortTime(ws.created_at)}</div>
          <div>last seen {shortTime(ws.last_seen_at)}</div>
          <div>last event {shortTime(ws.last_event_at)}</div>
        </div>
      </div>

      {/* Activity cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2.5">
        <Stat label="Messages (24h)" value={compact(ws.message_count)} />
        <Stat label="Events (24h)" value={compact(ws.event_count)} />
        <Stat label="Open handoffs" value={String(ws.open_handoff_count)} />
        <Stat label="Most active agent" value={topAgent} mono />
      </div>

      {/* Presence + health */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div className="rounded-xl border border-surface-200 dark:border-surface-700/60 p-3">
          <div className="text-[11px] font-medium text-surface-500 dark:text-surface-400 mb-2">
            Agents in workspace
          </div>
          <div className="flex items-center gap-4 text-xs">
            <PresenceDots presence={ws.presence} />
          </div>
          {present.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1">
              {present.slice(0, 8).map((s) => (
                <span
                  key={s.session_id}
                  className="font-mono text-[10px] rounded bg-surface-100 dark:bg-surface-800 px-1.5 py-0.5"
                  title={s.agent_id}
                >
                  {s.agent_id}
                </span>
              ))}
            </div>
          )}
        </div>
        <div className="rounded-xl border border-surface-200 dark:border-surface-700/60 p-3">
          <div className="text-[11px] font-medium text-surface-500 dark:text-surface-400 mb-2">
            Health / coordination
          </div>
          <dl className="grid grid-cols-2 gap-y-1.5 gap-x-3 text-xs">
            <HealthRow label="Open handoffs (unclaimed)" value={ws.health.open_handoffs_unclaimed} />
            <HealthRow label="Stale sessions" value={ws.health.stale_sessions} />
            <HealthRow label="Parked messages (dead-letter)" value={ws.health.parked_messages_deadletter} />
            <HealthRow label="Inbox backlog (unread)" value={ws.health.inbox_backlog_unread} />
          </dl>
        </div>
      </div>
      <p className="text-[10px] text-surface-400 dark:text-surface-500">
        Read-only in the MVP. Rename / pin / archive and the multi-workspace
        overview are phase 2.
      </p>
    </div>
  );
}

function Stat({
  label,
  value,
  mono,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="rounded-xl border border-surface-200 dark:border-surface-700/60 p-2.5">
      <div className="text-[10px] text-surface-400 dark:text-surface-500">{label}</div>
      <div
        className={`mt-0.5 text-lg font-semibold text-surface-800 dark:text-surface-100 truncate ${
          mono ? "font-mono text-sm" : ""
        }`}
      >
        {value}
      </div>
    </div>
  );
}

function HealthRow({ label, value }: { label: string; value: number }) {
  const warn = value > 0;
  return (
    <>
      <dt className="text-surface-500 dark:text-surface-400">{label}</dt>
      <dd
        className={`text-right font-semibold ${
          warn ? "text-amber-600 dark:text-amber-400" : "text-surface-700 dark:text-surface-200"
        }`}
      >
        {value}
      </dd>
    </>
  );
}

function AnalyticsBody({
  analytics,
  metric,
}: {
  analytics: WorkspaceAnalytics;
  metric: "volume" | "tokens";
}) {
  const { summary, buckets, agents, others } = analytics;

  // Series order = top-8 agents (+ an others lane when present). Colour by index.
  const series = useMemo(() => {
    const items = agents.map((a, i) => ({
      key: a.agent_id,
      color: SERIES_COLORS[i % SERIES_COLORS.length],
    }));
    if (others) items.push({ key: OTHERS, color: OTHERS_COLOR });
    return items;
  }, [agents, others]);

  const valueOf = (b: (typeof buckets)[number], key: string): number => {
    const cell = b.by_agent[key];
    if (!cell) return 0;
    return metric === "volume" ? cell.count : cell.tokens;
  };
  const bucketTotal = (b: (typeof buckets)[number]): number =>
    metric === "volume" ? b.total_count : b.total_tokens;
  const maxTotal = Math.max(1, ...buckets.map(bucketTotal));

  return (
    <div className="space-y-4">
      {/* Summary cards */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-2.5">
        <Stat label="Total messages" value={compact(summary.total_messages)} />
        <Stat label="Total tokens" value={compact(summary.total_tokens)} />
        <Stat
          label="Avg tokens/msg"
          value={summary.total_messages ? Math.round(summary.avg_tokens_per_msg).toString() : "0"}
        />
        <Stat label="p95 tokens" value={compact(summary.p95_tokens)} />
        <Stat label="Peak bucket" value={bucketLabel(summary.peak_bucket_start ?? "") || "—"} />
      </div>

      {/* Stacked bar chart */}
      <div className="panel p-4">
        <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
          <h3 className="text-xs font-medium text-surface-700 dark:text-surface-200">
            {metric === "volume" ? "Messages" : "Tokens"} per bucket (stacked by
            agent)
          </h3>
          <div className="flex items-center gap-2.5 text-[10px] text-surface-500 dark:text-surface-400 flex-wrap">
            {series.map((s) => (
              <span key={s.key} className="flex items-center gap-1">
                <span
                  className="h-2.5 w-2.5 rounded-sm"
                  style={{ backgroundColor: s.color }}
                />
                {s.key === OTHERS ? "others" : s.key}
              </span>
            ))}
          </div>
        </div>
        <div className="flex items-end gap-px" style={{ height: 180 }}>
          {buckets.map((b) => {
            const total = bucketTotal(b);
            return (
              <div
                key={b.bucket_start}
                className="flex-1 flex flex-col justify-end group relative"
                style={{ height: "100%" }}
                title={`${bucketLabel(b.bucket_start)} · ${total} ${metric === "volume" ? "msgs" : "tokens"}`}
              >
                {series.map((s, i) => {
                  const v = valueOf(b, s.key);
                  if (v <= 0) return null;
                  const h = (v / maxTotal) * 100;
                  return (
                    <div
                      key={s.key}
                      className={i === 0 ? "rounded-t-sm" : ""}
                      style={{ height: `${h}%`, backgroundColor: s.color }}
                    />
                  );
                })}
              </div>
            );
          })}
        </div>
        <div className="flex justify-between mt-1.5 text-[9px] text-surface-400 dark:text-surface-500">
          <span>{bucketLabel(buckets[0]?.bucket_start ?? "")}</span>
          <span>
            {bucketLabel(buckets[Math.floor(buckets.length / 2)]?.bucket_start ?? "")}
          </span>
          <span>now</span>
        </div>
      </div>

      {/* Top agents table */}
      <div className="panel">
        <div className="px-4 py-2.5 border-b border-surface-200 dark:border-surface-700/60">
          <h3 className="text-xs font-medium text-surface-700 dark:text-surface-200">
            Top agents (by sender)
          </h3>
        </div>
        <table className="w-full text-xs">
          <thead className="text-surface-400 dark:text-surface-500">
            <tr className="border-b border-surface-200/70 dark:border-surface-700/50">
              <th className="text-left font-medium px-4 py-2">Agent</th>
              <th className="text-right font-medium px-4 py-2">Messages</th>
              <th className="text-right font-medium px-4 py-2">Tokens</th>
              <th className="text-right font-medium px-4 py-2">Avg</th>
              <th className="text-right font-medium px-4 py-2">p95</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-surface-100 dark:divide-surface-800">
            {agents.map((a, i) => (
              <tr key={a.agent_id}>
                <td className="px-4 py-2 font-mono text-surface-700 dark:text-surface-200">
                  <span
                    className="inline-block h-2.5 w-2.5 rounded-sm mr-2 align-middle"
                    style={{ backgroundColor: SERIES_COLORS[i % SERIES_COLORS.length] }}
                  />
                  {a.agent_id}
                </td>
                <td className="text-right px-4 py-2 text-surface-700 dark:text-surface-200">{a.count}</td>
                <td className="text-right px-4 py-2 text-surface-700 dark:text-surface-200">{compact(a.tokens)}</td>
                <td className="text-right px-4 py-2 text-surface-500 dark:text-surface-400">{Math.round(a.avg_tokens)}</td>
                <td className="text-right px-4 py-2 text-surface-500 dark:text-surface-400">{compact(a.p95_tokens)}</td>
              </tr>
            ))}
            {others && (
              <tr className="text-surface-400 dark:text-surface-500">
                <td className="px-4 py-2 font-mono">
                  <span
                    className="inline-block h-2.5 w-2.5 rounded-sm mr-2 align-middle"
                    style={{ backgroundColor: OTHERS_COLOR }}
                  />
                  others ({others.agent_count})
                </td>
                <td className="text-right px-4 py-2">{others.count}</td>
                <td className="text-right px-4 py-2">{compact(others.tokens)}</td>
                <td className="text-right px-4 py-2">—</td>
                <td className="text-right px-4 py-2">—</td>
              </tr>
            )}
            {agents.length === 0 && !others && (
              <tr>
                <td colSpan={5} className="px-4 py-6 text-center text-surface-400 dark:text-surface-500">
                  No messages in this window.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <p className="text-[10px] text-surface-400 dark:text-surface-500">
        Source: messages (message_create); size = TOKENS via tiktoken o200k_base
        (offline). By sender. Recipient/fan-out and multi-workspace are phase 2.
      </p>
    </div>
  );
}

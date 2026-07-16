// Workspaces panel (spec bf6e06dc): a first-class operator view of each
// workspace — identity + presence + activity + health (overview) — plus a
// message-distribution analytics surface (volume x size-in-TOKENS over time,
// broken down by sender). Read-only MVP. All copy is English.

import { useCallback, useEffect, useMemo, useState } from "react";
import { FolderOpen, RotateCw } from "lucide-react";
import {
  api,
  type AnalyticsWindow,
  type HealthWindow,
  type SessionRow,
  type WorkspaceAnalytics,
  type WorkspaceHealth,
  type WorkspaceListItem,
} from "../api";
import { PageContainer } from "../components/PageContainer";

const WINDOWS: AnalyticsWindow[] = ["24h", "7d", "30d"];
const HEALTH_WINDOWS: HealthWindow[] = ["1h", "24h", "7d"];
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

function clockLabel(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

// Compact duration for health ages/averages and their thresholds.
function fmtDuration(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
  const h = seconds / 3600;
  return `${h >= 10 ? Math.round(h) : Math.round(h * 10) / 10}h`;
}

function fmtPct(rate: number): string {
  const pct = rate * 100;
  return `${Number.isInteger(pct) ? pct : pct.toFixed(1)}%`;
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
  const [healthWindow, setHealthWindow] = useState<HealthWindow>("24h");
  const [metric, setMetric] = useState<"volume" | "tokens">("volume");
  const [analytics, setAnalytics] = useState<WorkspaceAnalytics | null>(null);
  const [health, setHealth] = useState<WorkspaceHealth | null>(null);
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

  // Coordination health: same 15s poll, refetch on workspace/window change.
  useEffect(() => {
    if (!selected) {
      setHealth(null);
      return;
    }
    let alive = true;
    api
      .workspaceHealth(selected, healthWindow)
      .then((h) => alive && setHealth(h))
      .catch(() => alive && setHealth(null));
    return () => {
      alive = false;
    };
  }, [selected, healthWindow, refreshTick, tick]);

  const current = useMemo(
    () => list.find((w) => w.workspace_id === selected) ?? null,
    [list, selected],
  );

  if (list.length === 0) {
    return (
      <PageContainer width="wide" testId="workspaces-view">
        <div className="panel px-4 py-10 text-center text-sm text-surface-400 dark:text-surface-500">
          {error
            ? `Could not load workspaces: ${error}`
            : "No workspaces yet — they appear as agents coordinate through the bus."}
        </div>
      </PageContainer>
    );
  }

  return (
    <PageContainer width="wide" testId="workspaces-view" className="space-y-4">
      {/* Workspace cards — responsive grid, fills the width */}
      <section>
        <div className="px-1 pb-2 text-[11px] font-medium uppercase tracking-wider text-surface-400 dark:text-surface-500">
          Workspaces ({list.length})
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
          {list.map((w) => {
            const active = w.workspace_id === selected;
            return (
              <button
                key={w.workspace_id}
                onClick={() => setSelected(w.workspace_id)}
                className={`panel text-left p-3 transition-colors ${
                  active
                    ? "ring-2 ring-accent-400 dark:ring-accent-600 bg-accent-50/40 dark:bg-accent-900/20"
                    : "hover:bg-surface-50 dark:hover:bg-surface-800/50"
                }`}
                data-testid={`workspace-card-${w.workspace_id}`}
              >
                <div className="flex items-center gap-1.5">
                  <FolderOpen size={14} className="shrink-0 opacity-70" />
                  <span className="truncate text-sm font-medium text-surface-900 dark:text-surface-100">
                    {w.display_name || w.workspace_id.slice(0, 16) + "…"}
                  </span>
                  {w.is_default && (
                    <span className="ml-auto shrink-0 text-[9px] uppercase rounded bg-surface-200 dark:bg-surface-700 px-1 py-0.5">
                      default
                    </span>
                  )}
                </div>
                <div className="mt-2 flex items-center gap-2 text-[11px] text-surface-500 dark:text-surface-400">
                  <span>{w.message_count} msgs / 24h</span>
                  <PresenceDots presence={w.presence} />
                </div>
              </button>
            );
          })}
        </div>
      </section>

      {/* Selected workspace: overview + analytics at full width */}
      {current && <OverviewCard ws={current} roster={roster} analytics={analytics} />}

      {/* Coordination health (spec 7df9b1e0): windowed metrics + thresholds
          straight from the payload — replaces the old embryo health card. */}
      {current && (
        <HealthSection
          health={health}
          staleAgents={[
            ...new Set(
              roster
                .filter((s) => s.presence === "stale")
                .map((s) => s.agent_id),
            ),
          ]}
          parked={current.health.parked_messages_deadletter}
          window={healthWindow}
          onWindow={setHealthWindow}
        />
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
    </PageContainer>
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

      {/* Presence roster — the windowed health block moved to the dedicated
          "Coordination health" section below (spec 7df9b1e0). */}
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

function StatusBadge({ status }: { status: "ok" | "warn" }) {
  const warn = status === "warn";
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[11px] font-medium ${
        warn
          ? "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/30"
          : "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/30"
      }`}
      data-testid="health-status-badge"
    >
      <span
        className={`h-1.5 w-1.5 rounded-full ${warn ? "bg-amber-500" : "bg-emerald-500"}`}
      />
      {warn ? "WARN" : "OK"}
    </span>
  );
}

function HealthCard({
  label,
  scope,
  value,
  suffix,
  sub,
  warn,
}: {
  label: string;
  scope?: "windowed" | "snapshot";
  value: string;
  suffix?: string;
  sub?: string;
  warn: boolean;
}) {
  return (
    <div
      className={`rounded-xl border p-3 ${
        warn
          ? "border-amber-500/40 bg-amber-500/5"
          : "border-surface-200 dark:border-surface-700/60"
      }`}
    >
      <div
        className={`text-[11px] mb-1 ${
          warn
            ? "text-amber-600 dark:text-amber-400"
            : "text-surface-400 dark:text-surface-500"
        }`}
      >
        {label}
        {scope && <span className="opacity-60"> · {scope}</span>}
      </div>
      <div
        className={`text-2xl font-semibold truncate ${
          warn
            ? "text-amber-600 dark:text-amber-300"
            : "text-surface-800 dark:text-surface-100"
        }`}
      >
        {value}
        {suffix && (
          <span className="text-sm font-normal text-surface-500 dark:text-surface-400">
            {" "}
            {suffix}
          </span>
        )}
      </div>
      {sub && (
        <div
          className={`text-[11px] mt-1 ${
            warn
              ? "text-amber-600/80 dark:text-amber-400/80"
              : "text-surface-400 dark:text-surface-500"
          }`}
        >
          {sub}
        </div>
      )}
    </div>
  );
}

// The "Coordination health" section (spec 7df9b1e0, replaces the old embryo
// card): aggregated OK/WARN badge, 1h/24h/7d window toggle, one card per
// metric block with its declared scope, per-agent unread backlog and the
// thresholds — ALWAYS rendered from the payload, never hardcoded here. The
// parked dead-letter card stays fed by the workspace overview (snapshot; the
// health payload does not carry the parked lane in V1).
function HealthSection({
  health,
  staleAgents,
  parked,
  window: win,
  onWindow,
}: {
  health: WorkspaceHealth | null;
  staleAgents: string[];
  parked: number;
  window: HealthWindow;
  onWindow: (w: HealthWindow) => void;
}) {
  const m = health?.metrics;
  const t = health?.thresholds;
  const maxUnread = m?.inbox_backlog.per_agent[0]?.unread ?? 0;
  return (
    <section className="panel p-4 space-y-4" data-testid="coordination-health">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-3">
          <h2 className="text-sm font-semibold text-surface-800 dark:text-surface-100">
            Coordination health
          </h2>
          {health && <StatusBadge status={health.status} />}
        </div>
        <div className="flex items-center gap-2 text-xs">
          <Toggle
            options={HEALTH_WINDOWS.map((w) => [w, w] as [string, string])}
            value={win}
            onChange={(v) => onWindow(v as HealthWindow)}
          />
          {health && (
            <span className="text-[11px] text-surface-400 dark:text-surface-500">
              as of {clockLabel(health.generated_at)}
            </span>
          )}
        </div>
      </div>

      {!health || !m || !t ? (
        <div className="px-4 py-6 text-center text-xs text-surface-400 dark:text-surface-500">
          Loading health…
        </div>
      ) : (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2.5">
            <HealthCard
              label="Messages"
              scope={m.message_volume.scope}
              value={compact(m.message_volume.count)}
              sub="informational"
              warn={m.message_volume.status === "warn"}
            />
            <HealthCard
              label="Events"
              scope={m.event_volume.scope}
              value={compact(m.event_volume.count)}
              sub="informational"
              warn={m.event_volume.status === "warn"}
            />
            <HealthCard
              label="Unclaimed handoffs"
              scope={m.unclaimed_handoffs.scope}
              value={String(m.unclaimed_handoffs.count)}
              sub={
                m.unclaimed_handoffs.oldest_age_seconds != null
                  ? `oldest ${fmtDuration(m.unclaimed_handoffs.oldest_age_seconds)} (warn > ${fmtDuration(t.unclaimed_handoff_age_seconds)})`
                  : "none open"
              }
              warn={m.unclaimed_handoffs.status === "warn"}
            />
            <HealthCard
              label="Claim → complete"
              scope={m.handoff_completion.scope}
              value={
                m.handoff_completion.avg_claim_to_complete_seconds != null
                  ? fmtDuration(m.handoff_completion.avg_claim_to_complete_seconds)
                  : "—"
              }
              sub={`${m.handoff_completion.completed_pairs} pairs · avg (warn > ${fmtDuration(t.avg_claim_to_complete_seconds)})${m.handoff_completion.truncated ? " · sampled" : ""}`}
              warn={m.handoff_completion.status === "warn"}
            />
            <HealthCard
              label="Rejection rate"
              scope={m.handoff_rejections.scope}
              value={
                m.handoff_rejections.rejection_rate != null
                  ? fmtPct(m.handoff_rejections.rejection_rate)
                  : "—"
              }
              sub={`${m.handoff_rejections.rejected} of ${m.handoff_rejections.created} created (warn > ${fmtPct(t.rejection_rate)})${m.handoff_rejections.truncated ? " · sampled" : ""}`}
              warn={m.handoff_rejections.status === "warn"}
            />
            <HealthCard
              label="Inbox backlog"
              scope={m.inbox_backlog.scope}
              value={compact(m.inbox_backlog.total_unread)}
              sub={`max ${maxUnread} / agent (warn > ${t.per_agent_unread})`}
              warn={m.inbox_backlog.status === "warn"}
            />
            <HealthCard
              label="Agent presence"
              scope={m.agent_presence.scope}
              value={String(m.agent_presence.present)}
              suffix="present"
              sub={`${m.agent_presence.stale} stale · ${m.agent_presence.offline} offline (warn > ${t.stale_agents} stale)`}
              warn={m.agent_presence.status === "warn"}
            />
            <HealthCard
              label="Parked (dead-letter)"
              value={String(parked)}
              sub="from workspace overview"
              warn={parked > 0}
            />
          </div>

          {m.agent_presence.stale > 0 && staleAgents.length > 0 && (
            <div className="flex flex-wrap items-center gap-1.5 text-[11px] text-amber-600 dark:text-amber-400">
              <span className="font-medium">Stale agents:</span>
              {staleAgents.map((a) => (
                <span
                  key={a}
                  className="font-mono text-[10px] rounded border border-amber-500/30 bg-amber-500/10 px-1.5 py-0.5"
                >
                  {a}
                </span>
              ))}
            </div>
          )}

          <div className="rounded-xl border border-surface-200 dark:border-surface-700/60 p-3">
            <div className="text-[11px] font-medium uppercase tracking-wide text-surface-400 dark:text-surface-500 mb-2">
              Unread by agent{" "}
              <span className="normal-case">
                (top {m.inbox_backlog.per_agent.length} · +
                {m.inbox_backlog.others_unread} others)
              </span>
            </div>
            {m.inbox_backlog.per_agent.length === 0 ? (
              <div className="text-xs text-surface-400 dark:text-surface-500">
                No unread deliveries.
              </div>
            ) : (
              <div className="space-y-1.5">
                {m.inbox_backlog.per_agent.map((row) => (
                  <div key={row.agent_id} className="flex items-center gap-2 text-xs">
                    <span
                      className="w-32 truncate font-mono text-surface-600 dark:text-surface-300"
                      title={row.agent_id}
                    >
                      {row.agent_id}
                    </span>
                    <div className="flex-1 h-1.5 rounded bg-surface-100 dark:bg-surface-800">
                      <div
                        className={`h-1.5 rounded ${
                          row.unread > t.per_agent_unread
                            ? "bg-amber-500/80"
                            : "bg-sky-500/70"
                        }`}
                        style={{
                          width: `${(row.unread / Math.max(1, maxUnread)) * 100}%`,
                        }}
                      />
                    </div>
                    <span className="w-8 text-right text-surface-500 dark:text-surface-400">
                      {row.unread}
                    </span>
                  </div>
                ))}
              </div>
            )}
            <div className="mt-3 pt-2 border-t border-surface-200/70 dark:border-surface-700/50 text-[11px] text-surface-400 dark:text-surface-500">
              Thresholds are server defaults echoed in each reply — unclaimed
              &gt; {fmtDuration(t.unclaimed_handoff_age_seconds)} · avg
              claim→complete &gt; {fmtDuration(t.avg_claim_to_complete_seconds)}{" "}
              · rejection &gt; {fmtPct(t.rejection_rate)} · unread/agent &gt;{" "}
              {t.per_agent_unread} · stale agents &gt; {t.stale_agents}
            </div>
          </div>
        </>
      )}
    </section>
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

  // Per-series visibility: click a legend chip to isolate / hide an agent.
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const [hover, setHover] = useState<number | null>(null);
  const toggleSeries = (key: string) =>
    setHidden((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });

  // Series order = top-8 agents (+ an others lane when present). Colour by index.
  const series = useMemo(() => {
    const items = agents.map((a, i) => ({
      key: a.agent_id,
      color: SERIES_COLORS[i % SERIES_COLORS.length],
    }));
    if (others) items.push({ key: OTHERS, color: OTHERS_COLOR });
    return items;
  }, [agents, others]);
  const visible = series.filter((s) => !hidden.has(s.key));

  const valueOf = (b: (typeof buckets)[number], key: string): number => {
    const cell = b.by_agent[key];
    if (!cell) return 0;
    return metric === "volume" ? cell.count : cell.tokens;
  };
  // Totals + the Y-axis scale follow the VISIBLE series only, so filtering an
  // agent out re-scales the chart instead of leaving dead headroom.
  const visibleTotal = (b: (typeof buckets)[number]): number =>
    visible.reduce((sum, s) => sum + valueOf(b, s.key), 0);
  const maxTotal = Math.max(1, ...buckets.map(visibleTotal));
  const unit = metric === "volume" ? "msgs" : "tokens";
  const fmtY = (n: number) =>
    metric === "volume" ? String(Math.round(n)) : compact(Math.round(n));
  const yTicks = [maxTotal, maxTotal / 2, 0];

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
          {/* Clickable legend: toggle a series to isolate / remove agents. */}
          <div className="flex items-center gap-1.5 text-[10px] text-surface-500 dark:text-surface-400 flex-wrap">
            {series.map((s) => {
              const off = hidden.has(s.key);
              return (
                <button
                  key={s.key}
                  onClick={() => toggleSeries(s.key)}
                  title={off ? "Show" : "Hide / isolate"}
                  className={`flex items-center gap-1 px-1 py-0.5 rounded transition-colors ${
                    off
                      ? "opacity-40 line-through"
                      : "hover:bg-surface-100 dark:hover:bg-surface-800"
                  }`}
                >
                  <span
                    className="h-2.5 w-2.5 rounded-sm"
                    style={{ backgroundColor: s.color }}
                  />
                  {s.key === OTHERS ? "others" : s.key}
                </button>
              );
            })}
          </div>
        </div>

        <div
          className="flex"
          style={{ height: 196 }}
          onMouseLeave={() => setHover(null)}
        >
          {/* Y axis (message / token scale) */}
          <div
            className="flex flex-col justify-between pr-2 text-right text-[9px] text-surface-400 dark:text-surface-500 select-none"
            style={{ width: 44 }}
          >
            {yTicks.map((t, i) => (
              <div key={i}>{fmtY(t)}</div>
            ))}
          </div>

          {/* Plot area: gridlines + bars + hover tooltip */}
          <div className="relative flex-1">
            {yTicks.map((_, i) => (
              <div
                key={i}
                className="absolute left-0 right-0 border-t border-surface-100 dark:border-surface-800/70"
                style={{ top: `${(i / (yTicks.length - 1)) * 100}%` }}
              />
            ))}
            <div className="absolute inset-0 flex items-end gap-px">
              {buckets.map((b, idx) => (
                <div
                  key={b.bucket_start}
                  onMouseEnter={() => setHover(idx)}
                  className={`flex-1 flex flex-col justify-end h-full ${
                    hover === idx ? "bg-surface-100/50 dark:bg-white/5" : ""
                  }`}
                >
                  {visible.map((s, i) => {
                    const v = valueOf(b, s.key);
                    if (v <= 0) return null;
                    return (
                      <div
                        key={s.key}
                        className={i === 0 ? "rounded-t-sm" : ""}
                        style={{
                          height: `${(v / maxTotal) * 100}%`,
                          backgroundColor: s.color,
                        }}
                      />
                    );
                  })}
                </div>
              ))}
            </div>

            {hover !== null && buckets[hover] && (
              <div
                className="absolute z-10 pointer-events-none -translate-x-1/2 rounded-lg border border-surface-200 dark:border-surface-700 bg-white dark:bg-surface-800 shadow-xl px-2.5 py-1.5 text-[10px] min-w-[150px]"
                style={{
                  left: `${((hover + 0.5) / buckets.length) * 100}%`,
                  top: 0,
                }}
              >
                <div className="font-medium text-surface-700 dark:text-surface-200 mb-1">
                  {bucketLabel(buckets[hover].bucket_start)}
                </div>
                {visible
                  .filter((s) => valueOf(buckets[hover]!, s.key) > 0)
                  .sort(
                    (a, b) =>
                      valueOf(buckets[hover]!, b.key) -
                      valueOf(buckets[hover]!, a.key),
                  )
                  .map((s) => (
                    <div
                      key={s.key}
                      className="flex items-center justify-between gap-3 leading-relaxed"
                    >
                      <span className="flex items-center gap-1 text-surface-500 dark:text-surface-400 truncate">
                        <span
                          className="h-2 w-2 rounded-sm shrink-0"
                          style={{ backgroundColor: s.color }}
                        />
                        {s.key === OTHERS ? "others" : s.key}
                      </span>
                      <span className="font-mono text-surface-700 dark:text-surface-200">
                        {fmtY(valueOf(buckets[hover]!, s.key))}
                      </span>
                    </div>
                  ))}
                {visibleTotal(buckets[hover]) === 0 && (
                  <div className="text-surface-400 dark:text-surface-500">no messages</div>
                )}
                <div className="mt-1 pt-1 border-t border-surface-200 dark:border-surface-700 flex items-center justify-between gap-3 font-medium">
                  <span className="text-surface-600 dark:text-surface-300">Total</span>
                  <span className="font-mono text-surface-800 dark:text-surface-100">
                    {fmtY(visibleTotal(buckets[hover]))} {unit}
                  </span>
                </div>
              </div>
            )}
          </div>
        </div>

        <div className="flex justify-between mt-1.5 text-[9px] text-surface-400 dark:text-surface-500 pl-[44px]">
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

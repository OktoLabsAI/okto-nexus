// Dashboard shell (spec S2 / FR1) - Pulse visual grammar:
// collapsible left navigation sidebar (the "menu"), slim header with
// workspace scope + live state + theme toggle, light/dark via the html
// class strategy. Every surface beyond the gate talks exclusively to
// /api/v1 (br_4eeb72b0).

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Activity,
  Brain,
  ChartColumn,
  CheckSquare,
  ChevronDown,
  Compass,
  FolderOpen,
  HelpCircle,
  Info,
  KanbanSquare,
  Lock,
  Menu,
  MessageSquare,
  MessagesSquare,
  Moon,
  PanelLeft,
  RotateCw,
  Settings,
  Shield,
  ShieldAlert,
  Sun,
  Tags,
  Users,
  Waypoints,
} from "lucide-react";
import { AboutModal } from "./components/AboutModal";
import { HelpModal } from "./components/HelpModal";
import { LiveChip } from "./components/LiveChip";
import { MetricsSettingsPanel } from "./components/MetricsSettingsPanel";
import {
  dismissMetricsPrompt,
  isMetricsPromptDismissed,
} from "./components/metricsConsentStorage";
import { OnboardingModal } from "./components/onboarding/OnboardingModal";
import {
  isCompleted as onboardingDone,
  reset as resetOnboarding,
} from "./components/onboarding/onboardingStorage";
import {
  api,
  clearApiKey,
  getApiKey,
  setApiKey,
  type GraphSnapshot,
  type NexusInfo,
  type NexusEvent,
} from "./api";
import { useSSE } from "./useSSE";
import { useTheme } from "./hooks/useTheme";
import { GraphView } from "./views/GraphView";
import { AgentsView } from "./views/AgentsView";
import { MessagesView } from "./views/MessagesView";
import { HandoffsView } from "./views/HandoffsView";
import { EventsView } from "./views/EventsView";
import { MemoryView } from "./views/MemoryView";
import { WorkspacesView } from "./views/WorkspacesView";
import { RegistryView } from "./views/RegistryView";
import { PoliciesView } from "./views/PoliciesView";
import { GuardrailsView } from "./views/GuardrailsView";
import { CommunicationView } from "./views/CommunicationView";
import { ApprovalsView } from "./views/ApprovalsView";
import { SettingsView } from "./views/SettingsView";
import {
  WorkspaceNamesProvider,
  workspaceDisplayName,
} from "./components/WorkspaceNames";
import type { WorkspaceListItem } from "./api";

const VIEWS = [
  { name: "Graph", icon: Waypoints },
  { name: "Messages", icon: MessagesSquare },
  { name: "Handoffs", icon: KanbanSquare },
  { name: "Events", icon: Activity },
  // Experimental: listed only when feature_memory is enabled in the effective
  // server config. MCP memory_* tool exposure is gated at server bootstrap too.
  { name: "Memory", icon: Brain },
  { name: "Workspaces", icon: FolderOpen },
  { name: "Agents", icon: Users },
  { name: "Registry", icon: Tags },
  // The named, versioned policy catalog (spec 80624c1a): a policy is STAGED
  // until an agent binds it; enforcement is always-on and binding-driven (the
  // feature_governance flag is gone).
  { name: "Policies", icon: Shield },
  { name: "Guardrails", icon: ShieldAlert },
  // The named, versioned communication-style catalog (spec 6f961722): the
  // reusable half of the 4th per-agent axis — a style tells an agent HOW to
  // communicate and surfaces SELF-ONLY on its whoami once bound.
  { name: "Communication", icon: MessageSquare },
  // Always listed too (spec 2948b2a2 BR6: pending items stay decidable with
  // feature_hitl OFF); only the BADGE is gated — by the data, never the flag.
  { name: "Approvals", icon: CheckSquare },
  { name: "Settings", icon: Settings },
] as const;
type View = (typeof VIEWS)[number]["name"];

export default function App() {
  // Same-machine trust probe: when the serve is loopback-bound, the REST
  // surface answers without a key and the gate is skipped entirely - the
  // key ceremony belongs to AGENTS (/mcp), not to the local operator.
  const [mode, setMode] = useState<"checking" | "open" | "locked" | "unlocked">(
    "checking",
  );

  useEffect(() => {
    api
      .agents()
      .then(() => setMode(getApiKey() ? "unlocked" : "open"))
      .catch(() => setMode(getApiKey() ? "unlocked" : "locked"));
  }, []);

  if (mode === "checking") return null;
  if (mode === "locked") return <KeyGate onUnlock={() => setMode("unlocked")} />;
  return (
    <Dashboard
      localOpen={mode === "open"}
      onLock={() => {
        clearApiKey();
        setMode("locked");
      }}
    />
  );
}

// Pulse header pattern: both wordmark variants in the DOM, the theme picks
// one via dark:hidden / dark:block (no JS round-trip on toggle).
function BrandMark({ className = "h-7 w-auto" }: { className?: string }) {
  return (
    <span className="inline-flex items-center select-none">
      <img
        src="/logos/nexus-wordmark-light.svg"
        alt="Okto Nexus"
        className={`${className} dark:hidden`}
        draggable={false}
      />
      <img
        src="/logos/nexus-wordmark-dark.svg"
        alt="Okto Nexus"
        className={`${className} hidden dark:block`}
        draggable={false}
      />
    </span>
  );
}

function KeyGate({ onUnlock }: { onUnlock: () => void }) {
  const [key, setKey] = useState("");
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    setApiKey(key.trim());
    try {
      await api.agents();
      onUnlock();
    } catch (exc) {
      clearApiKey();
      setError("Key rejected: " + (exc as Error).message);
    }
  };

  return (
    <div className="h-screen grid place-items-center">
      <div className="panel p-6 w-[420px] space-y-4 animate-slide-up">
        <div>
          <BrandMark className="h-9 w-auto mb-2" />
          <p className="text-xs text-surface-500 dark:text-surface-400 mt-1">
            Enter an agent API key. It is kept in this tab only and never
            persisted on the server.
          </p>
        </div>
        <input
          autoFocus
          type="password"
          value={key}
          onChange={(e) => setKey(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submit()}
          placeholder="nxs_…"
          className="w-full rounded-lg border border-surface-200 dark:border-surface-700
            bg-white dark:bg-surface-800 px-3 py-2 text-sm font-mono
            focus:outline-none focus:ring-2 focus:ring-accent-500/40 focus:border-accent-500"
        />
        {error && <p className="text-xs text-red-500">{error}</p>}
        <button className="btn btn-primary w-full justify-center" onClick={submit}>
          Sign in
        </button>
      </div>
    </div>
  );
}

function Dashboard({
  onLock,
  localOpen,
}: {
  onLock: () => void;
  localOpen: boolean;
}) {
  const { theme, toggle } = useTheme();
  const [view, setView] = useState<View>("Graph");
  const [info, setInfo] = useState<NexusInfo | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(
    () => localStorage.getItem("okto-nexus-sidebar") !== "closed",
  );
  const [workspaces, setWorkspaces] = useState<WorkspaceListItem[]>([]);
  // The workspace SCOPE is the user's choice and survives reloads: the
  // serve's default only applies when nothing was ever picked (otherwise a
  // default pointing at an empty workspace silently hides the whole graph
  // right after the first render - the "edges vanish on refresh" effect).
  const [workspace, setWorkspace] = useState<string>(
    () => localStorage.getItem("okto-nexus-workspace") ?? "all",
  );
  const pickWorkspace = (id: string) => {
    localStorage.setItem("okto-nexus-workspace", id);
    setWorkspace(id);
  };
  const [graph, setGraph] = useState<GraphSnapshot | null>(null);
  const [eventLog, setEventLog] = useState<NexusEvent[]>([]);
  // Trajectory filter for the Events screen (R-I1). Lifted here so a
  // TraceChip click on ANY screen can switch views with the filter applied.
  const [eventTrace, setEventTrace] = useState("");
  const openTrace = useCallback((traceId: string) => {
    setEventTrace(traceId);
    setView("Events");
  }, []);
  const [refreshTick, setRefreshTick] = useState(0);
  // Monotonic counter bumped on every SSE event — drives the side panel's
  // live update while it is open (eventLog itself saturates at 500).
  const [liveTick, setLiveTick] = useState(0);
  // HITL (spec 2948b2a2): pending-approvals count behind the sidebar badge
  // (data-gated, never flag-gated — D7) + a tick bumped only on approval.*
  // SSE events so the Approvals screen refetches exactly when it matters.
  const [pendingApprovals, setPendingApprovals] = useState(0);
  const [approvalTick, setApprovalTick] = useState(0);
  const [showMenu, setShowMenu] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const [aboutOpen, setAboutOpen] = useState(false);
  const [onboardingOpen, setOnboardingOpen] = useState(false);
  const [metricsPanel, setMetricsPanel] = useState<"menu" | "prompt" | null>(
    null,
  );
  const menuRef = useRef<HTMLDivElement>(null);
  const memoryEnabled = Boolean(info?.features?.feature_memory);
  const visibleViews = useMemo(
    () => VIEWS.filter((v) => v.name !== "Memory" || memoryEnabled),
    [memoryEnabled],
  );

  const loadInfo = useCallback(async () => {
    const next = await api.info();
    setInfo(next);
    return next;
  }, []);

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setShowMenu(false);
      }
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  // First-run onboarding: shown once per browser (versioned localStorage),
  // never nags a returning operator. Re-openable from the header menu.
  useEffect(() => {
    if (!onboardingDone()) setOnboardingOpen(true);
  }, []);

  useEffect(() => {
    if (onboardingOpen || metricsPanel) return;
    if (isMetricsPromptDismissed()) return;
    let active = true;
    api
      .metricsSummary()
      .then((summary) => {
        if (!active) return;
        if (summary.mode === "disabled") {
          setMetricsPanel("prompt");
        } else {
          dismissMetricsPrompt();
        }
      })
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, [onboardingOpen, metricsPanel]);

  const closeMetricsPanel = () => {
    if (metricsPanel === "prompt") dismissMetricsPrompt();
    setMetricsPanel(null);
  };

  useEffect(() => {
    loadInfo().catch(() => undefined);
  }, [loadInfo, refreshTick]);

  useEffect(() => {
    if (!memoryEnabled && view === "Memory") setView("Graph");
  }, [memoryEnabled, view]);

  const toggleSidebar = () =>
    setSidebarOpen((open) => {
      localStorage.setItem("okto-nexus-sidebar", open ? "closed" : "open");
      return !open;
    });

  // Dedupe: a Live tick that fetches an UNCHANGED snapshot must not touch
  // state at all - otherwise every SSE event rebuilds the whole Sigma scene
  // (layout + camera) for nothing.
  const lastSnapshotRef = useRef<string>("");
  const loadGraph = useCallback(async () => {
    try {
      const snapshot = await api.graph(workspace);
      const fingerprint = JSON.stringify({
        n: snapshot.nodes,
        e: snapshot.edges,
        w: snapshot.workspace_id,
      });
      if (fingerprint === lastSnapshotRef.current) return;
      lastSnapshotRef.current = fingerprint;
      setGraph(snapshot);
    } catch {
      /* surfaced by the views */
    }
  }, [workspace]);

  // Incremental updates (FR6): an SSE event triggers a TARGETED refetch of
  // the graph snapshot and feeds the live tail - never a full page reload.
  // DEBOUNCED: connecting replays a backlog and busy swarms emit bursts;
  // one trailing fetch 400ms after the last event of a burst replaces the
  // fetch-per-event storm that froze the page on load.
  const refetchTimerRef = useRef<number | undefined>(undefined);
  const sseStatus = useSSE(
    useCallback(
      (event: NexusEvent) => {
        setEventLog((log) => [...log.slice(-499), event]);
        setLiveTick((t) => t + 1);
        // approval.requested/granted/denied move the pending queue — bump
        // the dedicated tick (badge + Approvals screen refetch on it).
        if (event.type.startsWith("approval.")) setApprovalTick((t) => t + 1);
        window.clearTimeout(refetchTimerRef.current);
        refetchTimerRef.current = window.setTimeout(loadGraph, 400);
      },
      [loadGraph],
    ),
  );

  useEffect(() => {
    loadGraph();
  }, [loadGraph, refreshTick]);

  // Badge count (initial fetch + every approval.* event + header refresh).
  // GET /approvals is workspace-scoped, so the "all" scope sums over every
  // known workspace. A locked gate / non-operator key just means no badge.
  const loadApprovalCount = useCallback(async () => {
    try {
      const ids =
        workspace === "all"
          ? (await api.workspaces()).workspaces.map((w) => w.workspace_id)
          : [workspace];
      const pages = await Promise.all(ids.map((id) => api.approvals(id)));
      setPendingApprovals(
        pages.reduce((total, page) => total + page.items.length, 0),
      );
    } catch {
      setPendingApprovals(0);
    }
  }, [workspace]);

  useEffect(() => {
    loadApprovalCount();
  }, [loadApprovalCount, approvalTick, refreshTick]);

  // The workspace scope picker is fed by the rich /api/v1/workspaces list (not
  // derived from /sessions): every KNOWN workspace shows up, including ones
  // with no live session yet (TR8).
  useEffect(() => {
    api
      .workspaces()
      .then(({ workspaces }) => setWorkspaces(workspaces))
      .catch(() => undefined);
  }, [refreshTick]);

  // Default scope = the serve's --project-root workspace (AC1) - applied
  // ONLY when the user never picked a scope on this browser AND the default
  // actually has activity (sessions). A serve started from an unrelated cwd
  // produces an EMPTY default workspace; auto-scoping to it blanks the graph
  // right after the first paint - the "edges vanish on refresh" effect.
  useEffect(() => {
    if (localStorage.getItem("okto-nexus-workspace")) return;
    Promise.all([loadInfo(), api.sessions()])
      .then(([info, sessions]) => {
        const def = (info as { default_workspace_id?: string | null })
          .default_workspace_id;
        if (def && sessions.items.some((s) => s.workspace_id === def)) {
          setWorkspace(def);
        }
      })
      .catch(() => undefined);
  }, [loadInfo]);

  return (
    <WorkspaceNamesProvider workspaces={workspaces}>
    <div className="h-screen flex flex-col bg-surface-50 dark:bg-surface-950">
      {/* Header FIRST, full-width above the sidebar (the Pulse App shell) */}
      <header
        className="flex items-center gap-3 px-4 py-2 shrink-0
          border-b border-surface-200/50 dark:border-gray-800/60
          bg-white/80 dark:bg-black/90 backdrop-blur-md relative z-20"
      >
        <button
          className="p-1.5 text-surface-400 hover:text-surface-600 dark:hover:text-surface-300
            hover:bg-surface-100 dark:hover:bg-white/10 rounded-lg transition-colors"
          onClick={toggleSidebar}
          title={sidebarOpen ? "Collapse menu" : "Expand menu"}
          data-testid="sidebar-toggle"
        >
          <PanelLeft size={18} />
        </button>
        <BrandMark />
        <span className="text-sm text-surface-500 dark:text-surface-400">
          / {view}
        </span>
        <div className="ml-auto flex items-center gap-2 text-xs">
          <select
            value={workspace}
            onChange={(e) => pickWorkspace(e.target.value)}
            className="rounded-lg border border-surface-200 dark:border-surface-700
              bg-white dark:bg-surface-800 px-2 py-1.5 max-w-[240px] text-xs
              focus:outline-none focus:ring-2 focus:ring-accent-500/40"
            title="Workspace scope"
          >
            <option value="all">All workspaces</option>
            {/* The CURRENT scope must always be a real option: a value
                missing from the list makes the browser DISPLAY the first
                option ("All") while the actual fetch scope is something
                else - a lying dropdown. */}
            {workspace !== "all" &&
              !workspaces.some((item) => item.workspace_id === workspace) && (
              <option value={workspace}>Unavailable workspace</option>
            )}
            {workspaces.map((item, index) => (
              <option key={item.workspace_id} value={item.workspace_id}>
                {workspaceDisplayName(item, index)}
              </option>
            ))}
          </select>
          <LiveChip status={sseStatus} />
          <button
            className="btn btn-secondary !px-2"
            onClick={() => setRefreshTick((t) => t + 1)}
            title="Refresh"
          >
            <RotateCw size={14} />
          </button>
          {!localOpen && (
            <button
              className="btn btn-secondary !px-2"
              onClick={onLock}
              title="Forget this tab's key"
            >
              <Lock size={14} />
            </button>
          )}
          {/* Menu dropdown (the Pulse header menu) */}
          <div className="relative" ref={menuRef}>
            <button
              onClick={() => setShowMenu((v) => !v)}
              className={`btn btn-secondary flex items-center gap-1 !px-2 ${
                showMenu ? "ring-2 ring-accent-300" : ""
              }`}
              data-testid="header-menu"
            >
              <Menu size={16} />
              <ChevronDown size={12} />
            </button>
            {showMenu && (
              <div className="absolute right-0 top-full mt-2 w-56 bg-white dark:bg-surface-800 border border-surface-200 dark:border-surface-700 rounded-lg shadow-xl z-50 py-1">
                <button
                  onClick={() => {
                    setShowMenu(false);
                    setView("Settings");
                  }}
                  className="w-full text-left px-4 py-2 text-sm text-surface-700 dark:text-surface-300 hover:bg-surface-50 dark:hover:bg-surface-700 flex items-center gap-2"
                >
                  <Settings size={14} />
                  Settings
                </button>
                <button
                  onClick={() => {
                    setShowMenu(false);
                    setMetricsPanel("menu");
                  }}
                  className="w-full text-left px-4 py-2 text-sm text-surface-700 dark:text-surface-300 hover:bg-surface-50 dark:hover:bg-surface-700 flex items-center gap-2"
                  data-testid="menu-metrics"
                >
                  <ChartColumn size={14} />
                  Metrics
                </button>
                <button
                  onClick={() => {
                    setShowMenu(false);
                    toggle();
                  }}
                  className="w-full text-left px-4 py-2 text-sm text-surface-700 dark:text-surface-300 hover:bg-surface-50 dark:hover:bg-surface-700 flex items-center gap-2"
                  data-testid="theme-toggle"
                >
                  {theme === "dark" ? <Sun size={14} /> : <Moon size={14} />}
                  {theme === "dark" ? "Light Mode" : "Dark Mode"}
                </button>
                <hr className="my-1 border-surface-200 dark:border-surface-700" />
                <button
                  onClick={() => {
                    setShowMenu(false);
                    resetOnboarding();
                    setOnboardingOpen(true);
                  }}
                  className="w-full text-left px-4 py-2 text-sm text-surface-700 dark:text-surface-300 hover:bg-surface-50 dark:hover:bg-surface-700 flex items-center gap-2"
                  data-testid="menu-getting-started"
                >
                  <Compass size={14} />
                  Getting started
                </button>
                <button
                  onClick={() => {
                    setShowMenu(false);
                    setHelpOpen(true);
                  }}
                  className="w-full text-left px-4 py-2 text-sm text-surface-700 dark:text-surface-300 hover:bg-surface-50 dark:hover:bg-surface-700 flex items-center gap-2"
                  data-testid="menu-help"
                >
                  <HelpCircle size={14} />
                  Help
                </button>
                <button
                  onClick={() => {
                    setShowMenu(false);
                    setAboutOpen(true);
                  }}
                  className="w-full text-left px-4 py-2 text-sm text-surface-700 dark:text-surface-300 hover:bg-surface-50 dark:hover:bg-surface-700 flex items-center gap-2"
                  data-testid="menu-about"
                >
                  <Info size={14} />
                  About
                </button>
              </div>
            )}
          </div>
        </div>
      </header>

      {helpOpen && <HelpModal onClose={() => setHelpOpen(false)} />}
      {aboutOpen && <AboutModal onClose={() => setAboutOpen(false)} />}
      {onboardingOpen && (
        <OnboardingModal onClose={() => setOnboardingOpen(false)} />
      )}
      {metricsPanel && !onboardingOpen && (
        <MetricsSettingsPanel
          initialPrompt={metricsPanel === "prompt"}
          onClose={closeMetricsPanel}
          onSaved={async () => {
            dismissMetricsPrompt();
            await loadInfo();
          }}
        />
      )}

      <div className="flex flex-1 overflow-hidden">
      {/* Navigation sidebar (the Pulse Sidebar grammar) */}
      <aside
        className={`backdrop-blur-md bg-surface-50/80 dark:bg-surface-900/80
          border-r border-surface-200/50 dark:border-surface-700/30
          flex flex-col overflow-hidden transition-all duration-300 ease-in-out
          ${sidebarOpen ? "w-56" : "w-0 border-r-0"}`}
        data-testid="nav-sidebar"
      >
        <div className="w-56 flex flex-col h-full">
          <nav className="flex-1 overflow-y-auto p-2 pt-3">
            <h3 className="px-3 py-1 text-xs font-medium uppercase tracking-wider text-surface-400 dark:text-surface-500">
              Observability
            </h3>
            <ul className="space-y-1 mb-4">
              {visibleViews.filter((v) => v.name !== "Settings").map(({ name, icon: Icon }) => (
                <li key={name}>
                  <button
                    data-view={name}
                    onClick={() => setView(name)}
                    className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-left text-sm transition-colors ${
                      view === name
                        ? "bg-accent-100 text-accent-700 dark:bg-accent-900/60 dark:text-accent-200"
                        : "text-surface-700 hover:bg-surface-100 dark:text-surface-300 dark:hover:bg-surface-800"
                    }`}
                  >
                    <Icon size={16} />
                    <span className="truncate">{name}</span>
                    {name === "Approvals" && pendingApprovals > 0 && (
                      <span
                        className="ml-auto min-w-[18px] px-1.5 py-0.5 rounded-full bg-red-500 text-white text-[10px] font-semibold text-center leading-none"
                        data-testid="approvals-badge"
                      >
                        {pendingApprovals}
                      </span>
                    )}
                  </button>
                </li>
              ))}
            </ul>
          </nav>
        </div>
      </aside>

      <main className="flex-1 min-w-0 overflow-hidden">
          {view === "Graph" && (
            <GraphView
              graph={graph}
              workspace={workspace}
              onChanged={loadGraph}
              theme={theme}
              liveTick={liveTick}
              sseStatus={sseStatus}
            />
          )}
          {view === "Messages" && (
            <MessagesView
              workspace={workspace}
              liveTick={liveTick}
              sseStatus={sseStatus}
              onOpenTrace={openTrace}
            />
          )}
          {view === "Handoffs" && (
            <HandoffsView workspace={workspace} onChanged={loadGraph} />
          )}
          {view === "Events" && (
            <EventsView
              workspace={workspace}
              log={eventLog}
              liveTick={liveTick}
              sseStatus={sseStatus}
              trace={eventTrace}
              onTraceChange={setEventTrace}
            />
          )}
          {view === "Memory" && memoryEnabled && (
            <MemoryView
              workspace={workspace}
              liveTick={liveTick}
              onOpenTrace={openTrace}
            />
          )}
          {view === "Workspaces" && (
            <WorkspacesView scope={workspace} refreshTick={refreshTick} />
          )}
          {view === "Agents" && (
            <AgentsView onChanged={loadGraph} workspace={workspace} />
          )}
          {view === "Registry" && <RegistryView />}
          {view === "Policies" && <PoliciesView workspace={workspace} />}
          {view === "Guardrails" && <GuardrailsView workspace={workspace} />}
          {view === "Communication" && <CommunicationView />}
          {view === "Approvals" && (
            <ApprovalsView
              workspace={workspace}
              refreshTick={approvalTick + refreshTick}
              onChanged={loadApprovalCount}
            />
          )}
          {view === "Settings" && <SettingsView onSettingsApplied={loadInfo} />}
      </main>
      </div>
    </div>
    </WorkspaceNamesProvider>
  );
}

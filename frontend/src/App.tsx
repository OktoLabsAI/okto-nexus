// Dashboard shell (spec S2 / FR1) - Pulse visual grammar:
// collapsible left navigation sidebar (the "menu"), slim header with
// workspace scope + live state + theme toggle, light/dark via the html
// class strategy. Every surface beyond the gate talks exclusively to
// /api/v1 (br_4eeb72b0).

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity,
  FolderOpen,
  KanbanSquare,
  Lock,
  MessagesSquare,
  Moon,
  PanelLeft,
  RotateCw,
  Settings,
  Sun,
  Users,
  Waypoints,
} from "lucide-react";
import {
  api,
  clearApiKey,
  getApiKey,
  setApiKey,
  type GraphSnapshot,
  type NexusEvent,
} from "./api";
import { useSSE } from "./useSSE";
import { useTheme } from "./hooks/useTheme";
import { GraphView } from "./views/GraphView";
import { AgentsView } from "./views/AgentsView";
import { MessagesView } from "./views/MessagesView";
import { HandoffsView } from "./views/HandoffsView";
import { EventsView } from "./views/EventsView";
import { WorkspacesView } from "./views/WorkspacesView";
import { SettingsView } from "./views/SettingsView";

const VIEWS = [
  { name: "Graph", icon: Waypoints },
  { name: "Messages", icon: MessagesSquare },
  { name: "Handoffs", icon: KanbanSquare },
  { name: "Events", icon: Activity },
  { name: "Workspaces", icon: FolderOpen },
  { name: "Agents", icon: Users },
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
      setError("Chave recusada: " + (exc as Error).message);
    }
  };

  return (
    <div className="h-screen grid place-items-center">
      <div className="panel p-6 w-[420px] space-y-4 animate-slide-up">
        <div>
          <BrandMark className="h-9 w-auto mb-2" />
          <p className="text-xs text-surface-500 dark:text-surface-400 mt-1">
            Informe uma API key de agente (ex.: a chave do <code>operator</code>{" "}
            impressa no primeiro <code>okto-nexus serve</code>). Ela fica apenas
            nesta aba e nunca é persistida no servidor.
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
          Entrar
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
  const [sidebarOpen, setSidebarOpen] = useState(
    () => localStorage.getItem("okto-nexus-sidebar") !== "closed",
  );
  const [workspaces, setWorkspaces] = useState<string[]>([]);
  const [workspace, setWorkspace] = useState<string>("all");
  const [graph, setGraph] = useState<GraphSnapshot | null>(null);
  const [eventLog, setEventLog] = useState<NexusEvent[]>([]);
  const [refreshTick, setRefreshTick] = useState(0);

  const toggleSidebar = () =>
    setSidebarOpen((open) => {
      localStorage.setItem("okto-nexus-sidebar", open ? "closed" : "open");
      return !open;
    });

  const loadGraph = useCallback(async () => {
    try {
      const snapshot = await api.graph(workspace);
      setGraph(snapshot);
    } catch {
      /* surfaced by the views */
    }
  }, [workspace]);

  // Incremental updates (FR6): an SSE event triggers a TARGETED refetch of
  // the graph snapshot and feeds the live tail - never a full page reload.
  const sseStatus = useSSE(
    useCallback(
      (event: NexusEvent) => {
        setEventLog((log) => [...log.slice(-499), event]);
        loadGraph();
      },
      [loadGraph],
    ),
  );

  useEffect(() => {
    loadGraph();
  }, [loadGraph, refreshTick]);

  useEffect(() => {
    api
      .sessions()
      .then(({ items }) => {
        const ids = [...new Set(items.map((s) => s.workspace_id))];
        setWorkspaces(ids);
      })
      .catch(() => undefined);
  }, [refreshTick]);

  // Default scope = the serve's --project-root workspace (AC1).
  useEffect(() => {
    api
      .info()
      .then((info) => {
        const def = (info as { default_workspace_id?: string | null })
          .default_workspace_id;
        if (def) setWorkspace(def);
      })
      .catch(() => undefined);
  }, []);

  const liveChip = useMemo(() => {
    const map = {
      live: [
        "● Live",
        "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300",
      ],
      connecting: [
        "● Connecting",
        "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
      ],
      reconnecting: [
        "● Reconnecting",
        "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
      ],
      off: [
        "● Off",
        "bg-surface-200 text-surface-600 dark:bg-surface-700 dark:text-surface-300",
      ],
    } as const;
    return map[sseStatus];
  }, [sseStatus]);

  return (
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
          title={sidebarOpen ? "Recolher menu" : "Expandir menu"}
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
            onChange={(e) => setWorkspace(e.target.value)}
            className="rounded-lg border border-surface-200 dark:border-surface-700
              bg-white dark:bg-surface-800 px-2 py-1.5 max-w-[240px] text-xs
              focus:outline-none focus:ring-2 focus:ring-accent-500/40"
            title="Workspace scope"
          >
            <option value="all">All workspaces</option>
            {workspaces.map((id) => (
              <option key={id} value={id}>
                {id.slice(0, 12)}…
              </option>
            ))}
          </select>
          <span className={`chip ${liveChip[1]}`}>{liveChip[0]}</span>
          <button
            className="btn btn-secondary !px-2"
            onClick={() => setRefreshTick((t) => t + 1)}
            title="Atualizar"
          >
            <RotateCw size={14} />
          </button>
          <button
            className="btn btn-secondary !px-2"
            onClick={toggle}
            title={theme === "dark" ? "Tema claro" : "Tema escuro"}
            data-testid="theme-toggle"
          >
            {theme === "dark" ? <Sun size={14} /> : <Moon size={14} />}
          </button>
          {!localOpen && (
            <button
              className="btn btn-secondary !px-2"
              onClick={onLock}
              title="Esquecer a chave desta aba"
            >
              <Lock size={14} />
            </button>
          )}
        </div>
      </header>

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
              {VIEWS.filter((v) => v.name !== "Settings").map(({ name, icon: Icon }) => (
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
                  </button>
                </li>
              ))}
            </ul>
            <h3 className="px-3 py-1 text-xs font-medium uppercase tracking-wider text-surface-400 dark:text-surface-500">
              System
            </h3>
            <ul className="space-y-1">
              <li>
                <button
                  data-view="Settings"
                  onClick={() => setView("Settings")}
                  className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-left text-sm transition-colors ${
                    view === "Settings"
                      ? "bg-accent-100 text-accent-700 dark:bg-accent-900/60 dark:text-accent-200"
                      : "text-surface-700 hover:bg-surface-100 dark:text-surface-300 dark:hover:bg-surface-800"
                  }`}
                >
                  <Settings size={16} />
                  <span>Settings</span>
                </button>
              </li>
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
            />
          )}
          {view === "Messages" && <MessagesView workspace={workspace} />}
          {view === "Handoffs" && (
            <HandoffsView workspace={workspace} onChanged={loadGraph} />
          )}
          {view === "Events" && <EventsView log={eventLog} />}
          {view === "Workspaces" && (
            <WorkspacesView workspaces={workspaces} graph={graph} />
          )}
          {view === "Agents" && <AgentsView onChanged={loadGraph} />}
          {view === "Settings" && <SettingsView />}
      </main>
      </div>
    </div>
  );
}

// Dashboard shell (spec S2 / FR1) - Pulse visual grammar:
// collapsible left navigation sidebar (the "menu"), slim header with
// workspace scope + live state + theme toggle, light/dark via the html
// class strategy. Every surface beyond the gate talks exclusively to
// /api/v1 (br_4eeb72b0).

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import {
  ChartColumn,
  ChevronDown,
  Compass,
  HelpCircle,
  Info,
  Lock,
  Menu,
  Moon,
  PanelLeft,
  RotateCw,
  Settings,
  Sun,
  X,
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
import {ProjectConnectFlow} from './components/onboarding/ProjectConnectFlow';
import {AgentActionModal} from './components/AgentActionModal';
import {HomeInspection} from './components/home/HomeInspection';
import {clearExactRuntimeRequests} from './components/home/exactRuntimeOperations';
import type {HomeTarget} from './homeTypes';
import { shouldOfferIntroduction } from './components/onboarding/onboardingStorage';
import {
  isCompleted as onboardingDone,
  reset as resetOnboarding,
} from "./components/onboarding/onboardingStorage";
import {
  api,
  type GraphSnapshot,
  type NexusInfo,
  type NexusEvent,
} from "./api";
import { useSSE } from "./useSSE";
import {
  newItems,
  notifyInBackground,
  OPERATOR_VIEWS,
  readSeenMarker,
  toastText,
  toastTitle,
  writeSeenMarker,
} from "./operatorUnread";
import { useTheme } from "./hooks/useTheme";
import { GraphView } from "./views/GraphView";
import { HomeView } from "./views/HomeView";
import {clearHomeContinuationRequests} from "./components/home/continuation";
import {OperationalHome} from "./components/home/OperationalHome";
import { AgentsView } from "./views/AgentsView";
import { MessagesView } from "./views/MessagesView";
import { HandoffsView } from "./views/HandoffsView";
import { MetaHarnessView } from "./views/MetaHarnessView";
import { EventsView } from "./views/EventsView";
import { MemoryView } from "./views/MemoryView";
import { ArtifactsView } from "./views/ArtifactsView";
import { WorkspacesView } from "./views/WorkspacesView";
import { RegistryView } from "./views/RegistryView";
import { PoliciesView } from "./views/PoliciesView";
import { GuardrailsView } from "./views/GuardrailsView";
import { CommunicationView } from "./views/CommunicationView";
import { ApprovalsView } from "./views/ApprovalsView";
import { RuntimesView } from "./views/RuntimesView";
import { ExecutionLogView } from "./views/ExecutionLogView";
import { SettingsView } from "./views/SettingsView";
import { AttentionView } from './views/AttentionView';
import { AttentionInspection } from './components/AttentionInspection';
import { useAttention } from './hooks/useAttention';
import type { AttentionAction, AttentionOccurrence } from './attentionTypes';
import {
  WorkspaceNamesProvider,
  workspaceDisplayName,
} from "./components/WorkspaceNames";
import type { WorkspaceListItem } from "./api";
import {getNavigationBreadcrumb, getNavigationEntry, type ViewId} from './navigationRegistry';
import {AdvancedView} from './views/AdvancedView';
import {useScopedAttentionSummary} from './hooks/useScopedAttentionSummary';
import {NavigationSidebar} from './components/NavigationSidebar';
import {GlobalAttentionButton} from './components/GlobalAttentionButton';

type View = ViewId;

export default function App() {
  const [status, setStatus] = useState<import("./api").OperatorStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const refreshAuth = useCallback(() => {
    return api.operatorStatus().then(value => { setStatus(value); setError(null); })
      .catch(exc => setError((exc as Error).message));
  }, []);
  useEffect(() => {
    sessionStorage.removeItem("okto_nexus_operator_key");
    void refreshAuth();
    const expired = () => {clearHomeContinuationRequests(sessionStorage);clearExactRuntimeRequests(sessionStorage);void refreshAuth();};
    window.addEventListener("nexus-auth-expired", expired);
    return () => window.removeEventListener("nexus-auth-expired", expired);
  }, [refreshAuth]);
  if (error) return <div role="alert" className="p-6">{error}<button className="btn btn-secondary ml-3" onClick={() => void refreshAuth()}>Retry</button></div>;
  if (!status) return <div className="p-6">Connecting…</div>;
  if (!status.authenticated) return <OperatorGate configured={status.configured} onUnlock={() => void refreshAuth()} />;
  return <Dashboard key={status.username || "local-operator"} identityKey={JSON.stringify([status.local, status.username])} localOpen={status.local} onLock={() => {
    clearHomeContinuationRequests(sessionStorage);
    clearExactRuntimeRequests(sessionStorage);
    window.dispatchEvent(new Event('nexus-operator-logout'));
    void api.operatorLogout().then(refreshAuth).catch(exc => setError((exc as Error).message));
  }} />;
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

function OperatorGate({configured, onUnlock}: {configured: boolean; onUnlock: () => void}) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  return <div className="h-screen grid place-items-center">
    <form className="panel p-6 w-full max-w-[420px] space-y-4" onSubmit={async event => {
      event.preventDefault(); setBusy(true); setError(null);
      try { await api.operatorLogin(username.trim(), password); setPassword(""); onUnlock(); }
      catch (exc) { setError((exc as Error).message); }
      finally { setBusy(false); }
    }}>
      <BrandMark className="h-9 w-auto mb-2" />
      <h1 className="font-semibold">Operator sign-in</h1>
      {configured ? <>
        <label className="block text-sm">Username<input autoFocus autoComplete="username" required value={username} onChange={e => setUsername(e.target.value)} className="w-full border rounded-lg p-2 mt-1 bg-transparent" /></label>
        <label className="block text-sm">Password<input type="password" autoComplete="current-password" required value={password} onChange={e => setPassword(e.target.value)} className="w-full border rounded-lg p-2 mt-1 bg-transparent" /></label>
        {error && <p role="alert" className="text-sm text-red-500">{error}</p>}
        <button className="btn btn-primary w-full justify-center" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
      </> : <p className="text-sm text-surface-500">Remote operator access is not configured. On the Nexus server, open the dashboard at localhost and go to Settings → Operator access.</p>}
    </form>
  </div>;
}

export function restoreClosedNavigationFocus(navigation:HTMLElement|null, trigger:HTMLButtonElement|null, active:Element|null):boolean {
  if(!navigation||!trigger||!active||!navigation.contains(active)||active.closest('dialog[open], [role="dialog"]'))return false;
  trigger.focus({preventScroll:true});
  return true;
}

function Dashboard({
  onLock,
  localOpen,
  identityKey,
}: {
  onLock: () => void;
  localOpen: boolean;
  identityKey: string;
}) {
  const { theme, toggle } = useTheme();
  const [view, setViewState] = useState<View>("Home");
  const [narrow, setNarrow] = useState(() => window.matchMedia('(max-width: 767px)').matches);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const navigationToggleRef=useRef<HTMLButtonElement>(null);
  const navigationPanelRef=useRef<HTMLElement>(null);
  useEffect(() => {
    const media = window.matchMedia('(max-width: 767px)');
    const resize = () => { setNarrow(media.matches); setMobileMenuOpen(false); };
    const escape = (event: KeyboardEvent) => { if (event.key === 'Escape') setMobileMenuOpen(false); };
    media.addEventListener('change', resize);
    window.addEventListener('keydown', escape);
    return () => { media.removeEventListener('change', resize); window.removeEventListener('keydown', escape); };
  }, []);
  const homeLeaveGuard = useRef<(() => boolean) | null>(null);
  const registerHomeLeaveGuard = useCallback((guard: (() => boolean) | null) => {homeLeaveGuard.current = guard;}, []);
  const mayLeavePanel = useCallback(() => {
    if (homeLeaveGuard.current && !homeLeaveGuard.current()) return false;
    const attentionDialog = document.querySelector<HTMLDialogElement>('[data-testid="attention-inspection"], [data-testid="project-connect-detail"], [data-testid="connection-context-detail"]');
    if (attentionDialog) {attentionDialog.dispatchEvent(new Event('cancel', {cancelable:true}));return false;}
    return true;
  }, []);
  const [homeOperational, setHomeOperational] = useState(() => localStorage.getItem('okto-nexus-home-operational') === 'enabled');
  const [latestHomeEvent, setLatestHomeEvent] = useState<NexusEvent | null>(null);
  const settingsPending = useRef(false);
  const onSettingsPending = useCallback((pending: boolean) => {settingsPending.current = pending;}, []);
  const mayLeaveSettings = () => mayLeavePanel() && (!settingsPending.current || window.confirm('Discard unsaved settings and leave this page?'));
  const viewRef = useRef<View>(view);
  viewRef.current = view;
  // Operator notifications (#78). visitBaseline is the "seen" marker from
  // before the operator opened Messages or Meta-harness. Meta-harness uses it
  // for the "new since your last visit" divider.
  const [visitBaseline, setVisitBaseline] = useState<string | null>(null);
  const setView = useCallback((next: View) => {
    if (!mayLeavePanel()) return;
    if (!settingsPending.current || window.confirm('Discard unsaved settings and leave this page?')) {
      settingsPending.current = false;
      if (OPERATOR_VIEWS.includes(next) && !OPERATOR_VIEWS.includes(viewRef.current)) {
        setVisitBaseline(readSeenMarker());
      }
      setViewState(next);
      setMobileMenuOpen(false);
    }
  }, []);
  const [info, setInfo] = useState<NexusInfo | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(
    () => localStorage.getItem("okto-nexus-sidebar") !== "closed",
  );
  const navigationOpen = narrow ? mobileMenuOpen : sidebarOpen;
  useLayoutEffect(()=>{
    if(!navigationOpen)restoreClosedNavigationFocus(navigationPanelRef.current,navigationToggleRef.current,document.activeElement);
  },[navigationOpen]);
  const [workspaces, setWorkspaces] = useState<WorkspaceListItem[]>([]);
  // True once GET /workspaces answered, so an empty list is not mistaken for
  // "not loaded yet" when the saved scope is checked.
  const [workspacesLoaded, setWorkspacesLoaded] = useState(false);
  const [workspaceNotice, setWorkspaceNotice] = useState<string | null>(null);
  // The workspace SCOPE is the user's choice and survives reloads: the
  // serve's default only applies when nothing was ever picked (otherwise a
  // default pointing at an empty workspace silently hides the whole graph
  // right after the first render - the "edges vanish on refresh" effect).
  const [workspace, setWorkspace] = useState<string>(
    () => localStorage.getItem("okto-nexus-workspace") ?? "all",
  );
  const attention = useAttention({workspace: view === 'Attention' ? 'all' : workspace, visible: view === 'Attention',
    enabled: info?.features?.feature_attention !== false});
  const globalAttention = useScopedAttentionSummary({workspace: 'all',
    enabled: info?.features?.feature_attention !== false});
  const [attentionInspection, setAttentionInspection] = useState<{
    item: AttentionOccurrence; action: AttentionAction;
  } | null>(null);
  const [attentionNavigationNotice, setAttentionNavigationNotice] = useState<string | null>(null);
  const attentionFocusReturn = useRef<HTMLElement | null>(null);
  const closeAttentionInspection = useCallback(() => {
    setAttentionInspection(null);
    window.requestAnimationFrame(() => {
      const previous = attentionFocusReturn.current;
      if (previous?.isConnected) previous.focus();
      else document.querySelector<HTMLElement>('[data-testid="attention-heading"]')?.focus();
    });
  }, []);
  const openAttention = useCallback((item: AttentionOccurrence, action: AttentionAction) => {
    if (!item.allowed_actions.includes(action)) return;
    attentionFocusReturn.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setAttentionNavigationNotice(null);
    setAttentionInspection({item, action});
  }, []);
  const currentAttentionItem = attentionInspection && attention.state.page?.items.find(
    item => item.attention_id === attentionInspection.item.attention_id);
  useEffect(() => {
    if (attention.state.status === 'forbidden' || attention.state.status === 'disabled') {
      setAttentionInspection(null);
      setAttentionNavigationNotice(null);
    } else if (attentionInspection && currentAttentionItem &&
        !currentAttentionItem.allowed_actions.includes(attentionInspection.action)) {
      closeAttentionInspection();
      setAttentionNavigationNotice('This action changed. Review the current record before continuing.');
    }
    // Absence from a limited page does not prove that the source was removed.
  }, [attention.state.status, attentionInspection, currentAttentionItem, closeAttentionInspection]);
  useEffect(() => {
    setAttentionInspection(null);
    setAttentionNavigationNotice(null);
  }, [workspace, view]);
  const pickWorkspace = (id: string) => {
    if (!mayLeavePanel()) return;
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
  useEffect(() => {
    if (refreshTick) attention.refresh();
  }, [refreshTick, attention.refresh]);
  useEffect(() => {if (refreshTick || attention.state.summary) globalAttention.refresh();},
    [refreshTick, attention.state.summary?.observed_at, globalAttention.refresh]);
  // Monotonic counter bumped on every SSE event — drives the side panel's
  // live update while it is open (eventLog itself saturates at 500).
  const [liveTick, setLiveTick] = useState(0);
  // HITL (spec 2948b2a2): pending-approvals count behind the sidebar badge
  // (data-gated, never flag-gated — D7) + a tick bumped only on approval.*
  // SSE events so the Approvals screen refetches exactly when it matters.
  const [approvalTick, setApprovalTick] = useState(0);
  // Unread operator messages: server count behind the sidebar badge, a tick
  // bumped on message.created events, and the toasts shown in every view.
  const [operatorUnread, setOperatorUnread] = useState(0);
  const [operatorTick, setOperatorTick] = useState(0);
  const [toasts, setToasts] = useState<
    { id: string; title: string; text: string }[]
  >([]);
  const reportedRef = useRef<Set<string> | null>(null);
  const [showMenu, setShowMenu] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const [aboutOpen, setAboutOpen] = useState(false);
  const [onboardingOpen, setOnboardingOpen] = useState(false);
  const [connectFlowOpen,setConnectFlowOpen]=useState(false);
  const [connectionTarget,setConnectionTarget]=useState<HomeTarget|null>(null);
  const openConnectFlow=()=>{if(mayLeavePanel()){setConnectionTarget(null);setConnectFlowOpen(true);}};
  useEffect(()=>{
    const clear=()=>{setConnectFlowOpen(false);setConnectionTarget(null);};
    window.addEventListener('nexus-auth-expired',clear);window.addEventListener('nexus-operator-logout',clear);
    return()=>{window.removeEventListener('nexus-auth-expired',clear);window.removeEventListener('nexus-operator-logout',clear);};
  },[]);
  const [introductionChecked, setIntroductionChecked] = useState(false);
  const [metricsPanel, setMetricsPanel] = useState<"menu" | "prompt" | null>(
    null,
  );
  const menuRef = useRef<HTMLDivElement>(null);
  const memoryEnabled = Boolean(info?.features?.feature_memory);

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

  // A browser-local flag alone cannot identify a new Nexus installation.
  useEffect(() => {
    let active = true;
    if (onboardingDone()) {setIntroductionChecked(true);return;}
    api.agents().then(result => {
      if (active && shouldOfferIntroduction(onboardingDone(), result.items)) setOnboardingOpen(true);
    }).catch(() => undefined).finally(() => {if (active) setIntroductionChecked(true);});
    return () => {active = false;};
  }, []);

  useEffect(() => {
    if (!introductionChecked || onboardingOpen || metricsPanel) return;
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
  }, [introductionChecked, onboardingOpen, metricsPanel]);

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

  const toggleSidebar = () => {
    if (narrow) { setMobileMenuOpen(open => !open); return; }
    setSidebarOpen((open) => {
      localStorage.setItem("okto-nexus-sidebar", open ? "closed" : "open");
      return !open;
    });
  };

  // Dedupe: a Live tick that fetches an UNCHANGED snapshot must not touch
  // state at all - otherwise every SSE event rebuilds the whole Sigma scene
  // (layout + camera) for nothing.
  const lastSnapshotRef = useRef<string>("");
  const workspaceRef = useRef(workspace);
  workspaceRef.current = workspace;
  const loadGraph = useCallback(async () => {
    try {
      const snapshot = await api.graph(workspace);
      // A late answer for a scope that is no longer selected must not
      // replace the graph of the new scope.
      if (workspaceRef.current !== workspace) return;
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
        setLatestHomeEvent(event);
        setLiveTick((t) => t + 1);
        // approval.requested/granted/denied move the pending queue — bump
        // the dedicated tick (badge + Approvals screen refetch on it).
        if (event.type.startsWith("approval.")) setApprovalTick((t) => t + 1);
        if (event.type === "message.created") setOperatorTick((t) => t + 1);
        window.clearTimeout(refetchTimerRef.current);
        refetchTimerRef.current = window.setTimeout(loadGraph, 400);
      },
      [loadGraph],
    ),
  );

  useEffect(() => {
    loadGraph();
  }, [loadGraph, refreshTick]);

  useEffect(() => {
    if (view !== "Graph") return;
    const timer = window.setInterval(loadGraph, 5000);
    return () => window.clearInterval(timer);
  }, [loadGraph, view]);

  const loadApprovalCount = useCallback(() => {attention.refresh();globalAttention.refresh();},
    [attention.refresh, globalAttention.refresh]);

  // Unread messages for the operator. The first answer only seeds the list of
  // reported messages, so opening the dashboard does not toast old messages.
  // While Messages or Meta-harness is open, the messages count as seen.
  const loadOperatorUnread = useCallback(async () => {
    try {
      const data = await api.operatorUnread(readSeenMarker());
      const watching = OPERATOR_VIEWS.includes(viewRef.current);
      if (watching && data.latest_created_at) writeSeenMarker(data.latest_created_at);
      setOperatorUnread(watching ? 0 : data.count);
      const reported = reportedRef.current;
      if (reported === null) {
        reportedRef.current = new Set(data.items.map((item) => item.message_id));
        return;
      }
      const fresh = newItems(data.items, reported).reverse();
      if (fresh.length === 0) return;
      fresh.forEach((item) => reported.add(item.message_id));
      const shown = fresh.slice(-3);
      shown.forEach((item) =>
        notifyInBackground(item, () => setView("Meta-harness")),
      );
      setToasts((current) =>
        [
          ...current,
          ...shown.map((item) => ({
            id: item.message_id,
            title: toastTitle(item),
            text: toastText(item),
          })),
        ].slice(-3),
      );
      shown.forEach((item) =>
        window.setTimeout(
          () => setToasts((current) => current.filter((t) => t.id !== item.message_id)),
          8000,
        ),
      );
    } catch {
      /* the badge is optional: a locked gate just shows none */
    }
  }, [setView]);

  useEffect(() => {
    const timer = window.setTimeout(loadOperatorUnread, 250);
    return () => window.clearTimeout(timer);
  }, [loadOperatorUnread, view, refreshTick, operatorTick]);

  useEffect(() => {
    const timer = window.setInterval(loadOperatorUnread, 10000);
    return () => window.clearInterval(timer);
  }, [loadOperatorUnread]);

  // The workspace scope picker is fed by the rich /api/v1/workspaces list (not
  // derived from /sessions): every KNOWN workspace shows up, including ones
  // with no live session yet (TR8).
  useEffect(() => {
    let active = true;
    let requestVersion = 0;
    const reload = () => {
      const version = ++requestVersion;
      api.workspaces().then(({workspaces}) => {
        if (active && version === requestVersion) {
          setWorkspaces(workspaces);
          setWorkspacesLoaded(true);
        }
      })
        .catch(() => undefined);
    };
    reload();
    window.addEventListener("nexus-workspaces-changed", reload);
    const timer = view === "Meta-harness" ? window.setInterval(reload, 10000) : undefined;
    return () => {
      active = false;
      window.removeEventListener("nexus-workspaces-changed", reload);
      if (timer !== undefined) window.clearInterval(timer);
    };
  }, [refreshTick, view]);

  // A saved scope can name a workspace that this hub does not have (for
  // example after the hub starts with a new data directory). Once the list is
  // known, replace such a scope with the serve default (or the first
  // workspace) and tell the operator. The check never runs before the list
  // arrives, and never when the list request failed.
  useEffect(() => {
    if (!workspacesLoaded || workspace === "all") return;
    if (workspaces.some((item) => item.workspace_id === workspace)) return;
    let active = true;
    const missing = workspace;
    const apply = (defaultId: string | null | undefined) => {
      if (!active) return;
      const fallback =
        workspaces.find((item) => item.workspace_id === defaultId) ??
        workspaces[0];
      if (fallback) {
        pickWorkspace(fallback.workspace_id);
      } else {
        localStorage.removeItem("okto-nexus-workspace");
        setWorkspace("all");
      }
      setWorkspaceNotice(
        `The saved project (${missing}) does not exist on this hub. ` +
          (fallback ? "A default project is selected." : "All projects are selected."),
      );
    };
    loadInfo()
      .then((next) =>
        apply((next as { default_workspace_id?: string | null }).default_workspace_id),
      )
      .catch(() => apply(null));
    return () => {
      active = false;
    };
  }, [workspacesLoaded, workspaces, workspace, loadInfo]);

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
    <div className="h-screen overflow-hidden flex flex-col bg-surface-50 dark:bg-surface-950">
      {/* Header FIRST, full-width above the sidebar (the Pulse App shell) */}
      <header
        className="flex flex-wrap items-center gap-2 sm:gap-3 px-4 py-2 shrink-0
          border-b border-surface-200/50 dark:border-gray-800/60
          bg-white/80 dark:bg-black/90 backdrop-blur-md relative z-20"
      >
        <button
          className="p-1.5 text-surface-400 hover:text-surface-600 dark:hover:text-surface-300
            hover:bg-surface-100 dark:hover:bg-white/10 rounded-lg transition-colors"
          onClick={toggleSidebar}
          title={navigationOpen ? "Collapse menu" : "Expand menu"}
          aria-label={navigationOpen ? "Collapse navigation" : "Expand navigation"}
          aria-expanded={navigationOpen}
          aria-controls="dashboard-navigation"
          data-testid="sidebar-toggle"
          ref={navigationToggleRef}
        >
          <PanelLeft size={18} />
        </button>
        <BrandMark />
        <nav aria-label="Breadcrumb" className="text-sm text-surface-500 dark:text-surface-400 flex flex-wrap items-center gap-1 min-w-0">
          {getNavigationBreadcrumb(view).map((crumb, index, crumbs) => <span key={`${crumb.id}-${index}`} className="min-w-0">
            <span aria-hidden="true"> / </span>
            {index === crumbs.length - 1 ? <span aria-current="page">{crumb.label}</span>
              : <button type="button" className="underline focus-visible:ring-2" onClick={() => setView(crumb.id)}>{crumb.label}</button>}
          </span>)}
        </nav>
        <div className="ml-auto w-full sm:w-auto min-w-0 flex items-center gap-2 text-xs">
          <label className="flex min-w-0 flex-1 sm:flex-none items-center gap-2">
          <span className="font-medium">Project</span>
          <select
            value={workspace}
            onChange={(e) => pickWorkspace(e.target.value)}
            className="rounded-lg border border-surface-200 dark:border-surface-700
              bg-white dark:bg-surface-800 px-2 py-1.5 min-w-0 flex-1 sm:flex-none max-w-[240px] text-xs
              focus:outline-none focus:ring-2 focus:ring-accent-500/40"
            aria-label="Project"
            title="Choose a project"
          >
            <option value="all">All projects</option>
            {/* The CURRENT scope must always be a real option: a value
                missing from the list makes the browser DISPLAY the first
                option ("All") while the actual fetch scope is something
                else - a lying dropdown. */}
            {workspace !== "all" &&
              !workspaces.some((item) => item.workspace_id === workspace) && (
              <option value={workspace}>Unavailable project</option>
            )}
            {workspaces.map((item, index) => (
              <option key={item.workspace_id} value={item.workspace_id}>
                {workspaceDisplayName(item, index)}
              </option>
            ))}
          </select>
          </label>
          <GlobalAttentionButton state={globalAttention.state} onOpen={() => {globalAttention.refresh();setView('Attention');}}/>
          <LiveChip status={sseStatus} />
          <button
            className="btn btn-secondary !px-2"
            onClick={() => setRefreshTick((t) => t + 1)}
            title={`Refresh ${getNavigationEntry(view).label}`}
            aria-label={`Refresh ${getNavigationEntry(view).label}`}
            data-testid="header-refresh"
          >
            <RotateCw size={14} />
          </button>
          {!localOpen && (
            <button
              className="btn btn-secondary !px-2"
              onClick={() => {
                if (mayLeaveSettings()) {
                  attention.clear();
                  setAttentionInspection(null);
                  onLock();
                }
              }}
              title="Sign out" aria-label="Sign out"
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
        <OnboardingModal onClose={() => setOnboardingOpen(false)} onOpenAgents={() => {setOnboardingOpen(false);openConnectFlow();}} />
      )}
      {connectFlowOpen&&<AgentActionModal title="Connect a project agent" presentation="drawer" wide testId="project-connect-detail" onClose={()=>setConnectFlowOpen(false)}>
        <ProjectConnectFlow identityKey={identityKey} workspace={workspaces.find(item=>item.workspace_id===workspace)??null} serverOrigin={window.location.origin}
          onClose={()=>setConnectFlowOpen(false)} onResume={item=>{setConnectFlowOpen(false);setConnectionTarget({kind:'connection',server_id:item.server_id,executor_id:item.executor_id,
            workspace_id:item.workspace_id,binding_id:item.binding_id,agent_id:item.agent_id});}}
          onComplete={result=>{setConnectFlowOpen(false);setRefreshTick(value=>value+1);attention.refresh();
            if(result.binding){const b=result.binding;if(b.server_id)setConnectionTarget({kind:'connection',server_id:b.server_id,executor_id:b.executor_id,workspace_id:b.workspace_id,binding_id:b.binding_id,agent_id:b.agent_id});}}}/>
      </AgentActionModal>}
      {connectionTarget&&<AgentActionModal title="Connection context" presentation="drawer" wide testId="connection-context-detail" onClose={()=>setConnectionTarget(null)}>
        <HomeInspection target={connectionTarget} serverId={connectionTarget.server_id} workspace={connectionTarget.workspace_id} onClose={()=>setConnectionTarget(null)}
          onChanged={()=>{setRefreshTick(value=>value+1);attention.refresh();}}/>
      </AgentActionModal>}
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

      {workspaceNotice && (
        <div
          role="status"
          data-testid="workspace-notice"
          className="shrink-0 flex items-center gap-3 px-4 py-2 text-xs
            bg-amber-50 text-amber-900 dark:bg-amber-900/30 dark:text-amber-100
            border-b border-amber-200 dark:border-amber-800"
        >
          <span className="flex-1">{workspaceNotice}</span>
          <button
            className="btn btn-secondary !px-2 !py-0.5"
            onClick={() => setWorkspaceNotice(null)}
            aria-label="Dismiss notice"
          >
            Dismiss
          </button>
        </div>
      )}

      <div className="flex flex-1 min-h-0 overflow-hidden relative">
      {narrow && mobileMenuOpen && <button className="absolute inset-0 z-20 bg-black/30"
        aria-label="Close navigation" onClick={() => setMobileMenuOpen(false)} />}
      {/* Navigation sidebar (the Pulse Sidebar grammar) */}
      <aside
        ref={navigationPanelRef}
        id="dashboard-navigation"
        aria-hidden={!navigationOpen}
        className={`absolute inset-y-0 left-0 z-30 md:static backdrop-blur-md bg-surface-50 dark:bg-surface-900
          border-r border-surface-200/50 dark:border-surface-700/30
          flex flex-col overflow-hidden transition-all duration-300 ease-in-out
          ${navigationOpen ? "w-56" : "w-0 border-r-0 invisible"}`}
        data-testid="nav-sidebar"
      >
        <div className="w-56 flex flex-col h-full">
          <NavigationSidebar view={view} onNavigate={setView} unread={operatorUnread}/>
        </div>
      </aside>

      <main className="flex-1 min-w-0 overflow-hidden">
          {view === 'Home' && <div className="h-full flex flex-col min-h-0">
            {(!homeOperational||info?.features?.feature_home===false)&&<div className="shrink-0 px-4 pt-2 flex justify-end">
              <button type="button" className="btn btn-secondary" onClick={openConnectFlow}>Connect or resume</button>
            </div>}
            <div className="min-h-0 flex-1">
              {homeOperational && info?.features?.feature_home !== false
                ? <OperationalHome key={workspace} workspace={workspace} workspaces={workspaces} identityKey={identityKey}
                    refreshTick={refreshTick} latestEvent={latestHomeEvent} streamStatus={sseStatus} onNavigate={setView}
                    onAttentionChanged={attention.refresh} onSetupAgent={openConnectFlow} registerLeaveGuard={registerHomeLeaveGuard}/>
                : <HomeView key={workspace} workspace={workspace} refreshTick={refreshTick} attention={attention.state}
                    onRefreshAttention={attention.refresh} onNavigate={setView}/>}
            </div>
          </div>}
          {view === 'Advanced' && <AdvancedView memoryEnabled={memoryEnabled} onNavigate={setView}/>}
          {view === 'Attention' && <div className="h-full flex flex-col min-h-0">
            <p className="px-4 pt-3 text-xs text-surface-500">All projects and Server incidents. The project selector does not filter this queue.</p>
            {attention.state.status === 'disabled' && <div className="px-4 pt-3 flex flex-wrap gap-2">
              <button className="btn btn-secondary" onClick={() => setView('Approvals')}>Review approvals</button>
              <button className="btn btn-secondary" onClick={() => setView('Meta-harness')}>Open Conversations</button>
            </div>}
            <div className="min-h-0 flex-1"><AttentionView
            state={{...attention.state, notice: attention.state.notice ?? attentionNavigationNotice}}
            filters={attention.filters} onFiltersChange={attention.setFilters}
            onRefresh={attention.refresh} onLoadMore={attention.loadMore}
            onSeen={attention.markSeen} onSnooze={attention.snooze} onOpen={openAttention}
          /></div></div>}
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
            <HandoffsView
              workspace={workspace}
              refreshTick={refreshTick}
              onChanged={loadGraph}
            />
          )}
          {view === "Meta-harness" && (
            <div className="h-full flex flex-col min-h-0"><div className="shrink-0 px-4 pt-3 flex justify-end"><button type="button" className="btn btn-secondary" onClick={openConnectFlow}>Connect or resume</button></div>
            <div className="min-h-0 flex-1"><MetaHarnessView
              workspace={workspace}
              workspaces={workspaces}
              liveTick={liveTick}
              newSince={visitBaseline}
            /></div></div>
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
          {view === "Artifacts" && (
            <ArtifactsView workspace={workspace} liveTick={liveTick} />
          )}
          {view === "Workspaces" && (
            <WorkspacesView scope={workspace} refreshTick={refreshTick} />
          )}
          {view === "Agents" && (
            <AgentsView onChanged={loadGraph} workspace={workspace} />
          )}
          {view === "Registry" && <RegistryView />}
          {view === "Runtimes" && <RuntimesView onApprovals={() => setView("Approvals")} />}
          {view === "Execution log" && <ExecutionLogView workspace={workspace} />}
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
          {view === "Settings" && <SettingsView onSettingsApplied={loadInfo} onPendingChange={onSettingsPending}
            homeOperational={homeOperational} onHomeOperationalChange={next=>{
              if (!mayLeavePanel()) return;
              localStorage.setItem('okto-nexus-home-operational', next ? 'enabled' : 'disabled');setHomeOperational(next);
            }}/>}
      </main>
      </div>
      {attentionInspection && attention.state.status !== 'forbidden' && attention.state.status !== 'disabled' &&
        <AttentionInspection item={currentAttentionItem || attentionInspection.item} action={attentionInspection.action}
          refreshKey={attention.state.page?.observed_at ?? attention.state.summary?.observed_at}
          onClose={closeAttentionInspection} onChanged={attention.refresh} />}
      {toasts.length > 0 && (
        <div
          className="fixed bottom-4 right-4 z-50 flex w-80 flex-col gap-2"
          role="status"
          aria-live="polite"
          data-testid="operator-toasts"
        >
          {toasts.map((toast) => (
            <div
              key={toast.id}
              className="flex items-start gap-2 rounded-lg border border-accent-300 bg-white p-3 text-xs shadow-xl dark:border-accent-700/60 dark:bg-surface-800"
              data-testid="operator-toast"
            >
              <button
                className="min-w-0 flex-1 text-left"
                onClick={() => {
                  setToasts((current) => current.filter((t) => t.id !== toast.id));
                  setView("Meta-harness");
                }}
                title="Open Conversations"
              >
                <div className="font-semibold text-surface-800 dark:text-surface-100">
                  {toast.title}
                </div>
                <div className="mt-0.5 truncate text-surface-600 dark:text-surface-300">
                  {toast.text}
                </div>
              </button>
              <button
                className="text-surface-400 hover:text-surface-600 dark:hover:text-surface-200"
                onClick={() =>
                  setToasts((current) => current.filter((t) => t.id !== toast.id))
                }
                aria-label="Dismiss message notice"
              >
                <X size={14} />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
    </WorkspaceNamesProvider>
  );
}

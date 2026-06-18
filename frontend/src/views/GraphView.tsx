// The agent-mesh graph (spec S2 / FR2-FR3): Sigma.js v3 over graphology
// with a deterministic layout (seeded initial positions per agent_id +
// fixed forceatlas2 iterations - stable across reloads, AC2).
//
// Visual grammar (owner-reviewed, 2026-06-10; central hub node tried and
// REJECTED by the owner - idle agents sit on a calm deterministic orbit
// around the mesh's centroid instead):
// * Agents are circles coloured by DERIVED presence; size tracks activity;
//   offline nodes and labels are deliberately muted.
// * Message edges are blue, thickness ~ volume; in-flight traffic turns
//   the edge cyan and adds a "N (mail)" edge label badge.
// * Handoffs are magenta SQUARES (work waiting for a claim, not agents).
// Theme-aware: label/muted colours flip with the Pulse light/dark theme.
// Everything rendered derives 1:1 from the API payload (br_10140930).

import { useEffect, useMemo, useRef, useState } from "react";
import Graph from "graphology";
import forceAtlas2 from "graphology-layout-forceatlas2";
import Sigma from "sigma";
import { NodeSquareProgram } from "@sigma/node-square";
import { DashedEdgeArrowProgram } from "../graph/DashedEdgeProgram";
import { Ban, RotateCw, Search, X } from "lucide-react";
import {
  api,
  type ConversationPeer,
  type GraphEdge,
  type GraphHandoff,
  type GraphNode,
  type GraphSnapshot,
  type MessageRow,
} from "../api";
import { useConfirm } from "../components/Confirm";
import { LiveChip } from "../components/LiveChip";
import { Markdown } from "../components/Markdown";
import { ResizablePanel } from "../components/ResizablePanel";
import type { SSEStatus } from "../useSSE";

type ThemeName = "light" | "dark";

function presenceColor(presence: GraphNode["presence"], theme: ThemeName): string {
  if (presence === "present") return "#0ea5e9";
  if (presence === "stale") return "#f59e0b";
  return theme === "dark" ? "#3f4a5c" : "#b2bdcc";
}

// Grey flow-decay for COMPLETED traffic (no pending deliveries in the
// pair), tuned to real swarm rhythms (exchanges minutes-to-hours apart):
// light grey < 15 min since the last completed hop, mid < 1 h, dark < 4 h,
// gone afterwards. "Visibility decays with age" flips with the theme
// (recent = brightest on dark, darkest on light).
const FLOW_LIGHT_MS = 15 * 60 * 1000;
const FLOW_MID_MS = 60 * 60 * 1000;
const FLOW_DARK_MS = 4 * 60 * 60 * 1000;

function flowDecayColor(
  lastDoneAt: string | null,
  nowMs: number,
  dark: boolean,
): string | null {
  if (!lastDoneAt) return null;
  const age = nowMs - Date.parse(lastDoneAt.endsWith("Z") ? lastDoneAt : lastDoneAt + "Z");
  if (!Number.isFinite(age) || age < 0) return dark ? "#d1d5db" : "#475569";
  if (age < FLOW_LIGHT_MS) return dark ? "#d1d5db" : "#475569";
  if (age < FLOW_MID_MS) return dark ? "#8b95a5" : "#94a3b8";
  if (age < FLOW_DARK_MS) return dark ? "#4b5563" : "#cbd5e1";
  return null; // older than 4 h: the flow edge disappears
}

// Deterministic angle from the agent id (stable layout seeds, TR2).
function hashOf(id: string): number {
  let hash = 2166136261;
  for (let i = 0; i < id.length; i++) {
    hash = Math.imul(hash ^ id.charCodeAt(i), 16777619);
  }
  return hash >>> 0;
}

function seedPosition(id: string): { x: number; y: number } {
  const hash = hashOf(id);
  const angle = ((hash % 3600) / 3600) * Math.PI * 2;
  const radius = 5 + (((hash >> 8) % 100) / 100) * 5;
  return { x: Math.cos(angle) * radius, y: Math.sin(angle) * radius };
}

type Selection =
  | { kind: "node"; node: GraphNode }
  | { kind: "edge"; edge: GraphEdge }
  | { kind: "handoff"; handoff: GraphHandoff }
  | null;

export function GraphView({
  graph,
  workspace,
  onChanged,
  theme,
  liveTick,
  sseStatus,
}: {
  graph: GraphSnapshot | null;
  workspace: string;
  onChanged: () => void;
  theme: ThemeName;
  liveTick?: number;
  sseStatus?: SSEStatus;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [selection, setSelection] = useState<Selection>(null);

  const model = useMemo(() => {
    if (!graph) return null;
    const dark = theme === "dark";
    const g = new Graph({ multi: true, type: "directed" });

    for (const node of graph.nodes) {
      const activity = node.sessions + node.inbox.unread + node.inbox.delivered;
      const offline = node.presence === "offline";
      const { x, y } = seedPosition(node.agent_id);
      g.addNode(node.agent_id, {
        label: node.agent_id,
        x,
        y,
        size: (offline ? 10 : 14) + Math.min(14, activity * 3),
        color: presenceColor(node.presence, theme),
        labelColor: offline
          ? dark
            ? "#64748b"
            : "#94a3b8"
          : dark
            ? "#e2e8f0"
            : "#1e293b",
        kind: "agent",
      });
    }

    for (const edge of graph.edges.messages) {
      if (!g.hasNode(edge.from) || !g.hasNode(edge.to)) continue;
      const { unread, delivered } = edge.in_flight;
      const baseSize = 1.5 + Math.min(6, Math.log2(edge.count + 1));
      // Layer 1 - IN-FLIGHT (solid cyan): the recipient PULLED the message
      // and is working on it (no ack yet).
      if (delivered > 0) {
        g.addEdgeWithKey(`m:${edge.from}->${edge.to}`, edge.from, edge.to, {
          size: baseSize,
          color: "#0ea5e9",
          label: `${delivered} ✉`,
          type: "arrow",
        });
      }
      // Layer 2 - INBOX (dashed): delivered to the recipient's inbox,
      // waiting to be pulled.
      if (unread > 0) {
        g.addEdgeWithKey(`i:${edge.from}->${edge.to}`, edge.from, edge.to, {
          size: Math.max(1.5, baseSize - 0.5),
          color: dark ? "#7dd3fc" : "#0284c7",
          label: `${unread} ⌛`,
          type: "dashed",
        });
      }
      // Layer 3 - COMPLETED FLOW (grey, decaying): nothing pending in the
      // pair; the edge fades light -> mid -> dark grey over 15 min since
      // the last completed hop, then disappears (a new exchange resets it).
      if (unread === 0 && delivered === 0) {
        const grey = flowDecayColor(edge.last_done_at, Date.now(), dark);
        if (grey) {
          g.addEdgeWithKey(`m:${edge.from}->${edge.to}`, edge.from, edge.to, {
            size: baseSize,
            color: grey,
            type: "arrow",
            flowDoneAt: edge.last_done_at,
          });
        }
      }
    }

    for (const handoff of graph.edges.handoffs) {
      const anchor = handoff.from_agent_id;
      if (!anchor || !g.hasNode(anchor)) continue;
      if (handoff.status === "CLAIMED" && handoff.claimed_by) {
        if (g.hasNode(handoff.claimed_by)) {
          g.addEdgeWithKey(
            `h:${handoff.handoff_id}`,
            anchor,
            handoff.claimed_by,
            { size: 2, color: "#ec4899", type: "arrow" },
          );
        }
        continue;
      }
      // OPEN handoff: a magenta SQUARE (work in the pool, not an agent).
      const poolId = `pool:${handoff.handoff_id}`;
      const base = g.getNodeAttributes(anchor);
      const target = handoff.target as { capability?: string; role?: string } | null;
      const targetLabel = target?.capability ?? target?.role ?? "pool";
      g.addNode(poolId, {
        label: `handoff · ${targetLabel}`,
        x: (base.x as number) + 1.5,
        y: (base.y as number) + 1.5,
        size: 11,
        color: "#ec4899",
        labelColor: dark ? "#f9a8d4" : "#be185d",
        type: "square",
        kind: "handoff",
      });
      g.addEdgeWithKey(`h:${handoff.handoff_id}`, anchor, poolId, {
        size: 2,
        color: "rgba(236,72,153,0.7)",
        type: "arrow",
      });
    }

    if (g.order > 1) {
      forceAtlas2.assign(g, {
        iterations: 200,
        settings: { ...forceAtlas2.inferSettings(g), slowDown: 5 },
      });
    }

    // Idle agents (no traffic at all) sit on a deterministic orbit around
    // the mesh's centroid: organised, with no extra nodes or tether edges.
    const agents = g.filterNodes((_, a) => a.kind === "agent");
    if (agents.length > 0) {
      let cx = 0;
      let cy = 0;
      for (const id of agents) {
        cx += g.getNodeAttribute(id, "x") as number;
        cy += g.getNodeAttribute(id, "y") as number;
      }
      cx /= agents.length;
      cy /= agents.length;

      let maxR = 1;
      for (const id of agents) {
        const dx = (g.getNodeAttribute(id, "x") as number) - cx;
        const dy = (g.getNodeAttribute(id, "y") as number) - cy;
        maxR = Math.max(maxR, Math.hypot(dx, dy));
      }
      const orbit = maxR * 1.25;
      for (const id of agents) {
        if (g.degree(id) > 0) continue;
        const angle = ((hashOf(id) % 3600) / 3600) * Math.PI * 2;
        g.setNodeAttribute(id, "x", cx + Math.cos(angle) * orbit);
        g.setNodeAttribute(id, "y", cy + Math.sin(angle) * orbit);
      }
    }
    return g;
  }, [graph, theme]);

  useEffect(() => {
    if (!containerRef.current || !model) return;
    const dark = theme === "dark";
    const renderer = new Sigma(model, containerRef.current, {
      enableEdgeEvents: true,
      labelColor: { attribute: "labelColor", color: dark ? "#e2e8f0" : "#1e293b" },
      labelSize: 15,
      labelWeight: "600",
      labelRenderedSizeThreshold: 0, // every node keeps its name visible
      renderEdgeLabels: true,
      edgeLabelSize: 13,
      edgeLabelColor: { color: "#0ea5e9" },
      edgeLabelWeight: "700",
      defaultEdgeType: "line",
      nodeProgramClasses: { square: NodeSquareProgram },
      edgeProgramClasses: { dashed: DashedEdgeArrowProgram },
      allowInvalidContainer: true,
    });
    renderer.on("clickNode", ({ node }) => {
      if (node.startsWith("pool:")) {
        const handoff = graph?.edges.handoffs.find(
          (h) => h.handoff_id === node.slice(5),
        );
        setSelection(handoff ? { kind: "handoff", handoff } : null);
        return;
      }
      const data = graph?.nodes.find((n) => n.agent_id === node);
      setSelection(data ? { kind: "node", node: data } : null);
    });
    renderer.on("clickEdge", ({ edge }) => {
      if (edge.startsWith("h:")) {
        const handoff = graph?.edges.handoffs.find(
          (h) => h.handoff_id === edge.slice(2),
        );
        setSelection(handoff ? { kind: "handoff", handoff } : null);
        return;
      }
      if (!edge.startsWith("m:") && !edge.startsWith("i:")) return;
      const [from, to] = edge.slice(2).split("->");
      const data = graph?.edges.messages.find(
        (e) => e.from === from && e.to === to,
      );
      setSelection(data ? { kind: "edge", edge: data } : null);
    });
    renderer.on("clickStage", () => setSelection(null));
    // Exposed for the e2e harness (clicking WebGL nodes needs their
    // viewport coordinates); harmless in production.
    (window as unknown as { __nexusSigma?: Sigma }).__nexusSigma = renderer;

    // Flow-decay ticker: every 30s, fade completed-flow edges IN PLACE
    // (attribute mutation re-renders; it never rebuilds layout or camera).
    const decayTimer = window.setInterval(() => {
      const now = Date.now();
      for (const edge of [...model.edges()]) {
        const doneAt = model.getEdgeAttribute(edge, "flowDoneAt") as
          | string
          | undefined;
        if (!doneAt) continue;
        const grey = flowDecayColor(doneAt, now, dark);
        if (grey) model.setEdgeAttribute(edge, "color", grey);
        else model.dropEdge(edge);
      }
    }, 30_000);
    return () => {
      window.clearInterval(decayTimer);
      renderer.kill();
    };
  }, [model, graph, theme]);

  return (
    <div className="h-full flex">
      <div
        className="flex-1 relative bg-surface-50 dark:bg-surface-950 transition-colors"
        data-testid="graph-canvas"
      >
        <div ref={containerRef} className="absolute inset-0" />
        <Legend />
        {graph && graph.nodes.length === 0 && (
          <div className="absolute inset-0 grid place-items-center text-sm text-surface-400 dark:text-surface-500">
            No agents registered yet — create one in the Agents tab.
          </div>
        )}
      </div>
      {selection && (
        <ResizablePanel testId="side-panel">
          <SidePanel
            selection={selection}
            workspace={workspace}
            theme={theme}
            onClose={() => setSelection(null)}
            onChanged={onChanged}
            liveTick={liveTick}
            sseStatus={sseStatus}
          />
        </ResizablePanel>
      )}
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Legend - collapsible "how to read this graph" card
// --------------------------------------------------------------------------- //
function Legend() {
  const [open, setOpen] = useState(true);
  if (!open) {
    return (
      <button
        className="absolute bottom-4 left-4 btn btn-secondary"
        onClick={() => setOpen(true)}
      >
        ? How to read
      </button>
    );
  }
  return (
    <div
      className="absolute bottom-4 left-4 panel !bg-white/85 dark:!bg-surface-900/85
        backdrop-blur p-3 text-xs leading-6 text-surface-600 dark:text-surface-300 max-w-xs"
      data-testid="graph-legend"
    >
      <div className="flex items-center justify-between mb-1">
        <span className="font-display font-semibold text-surface-800 dark:text-surface-200">
          How to read this graph
        </span>
        <button
          className="text-surface-400 hover:text-surface-700 dark:hover:text-surface-200 ml-3"
          onClick={() => setOpen(false)}
          title="Minimize"
        >
          ✕
        </button>
      </div>
      <div>
        <span className="text-accent-500 text-base align-middle">●</span>{" "}
        present <span className="text-surface-400">· heartbeat &lt; 1 min</span>
      </div>
      <div>
        <span className="text-amber-500 text-base align-middle">●</span> stale{" "}
        <span className="text-surface-400">· silent for 1–30 min</span>
      </div>
      <div>
        <span className="text-surface-400 text-base align-middle">●</span>{" "}
        offline <span className="text-surface-400">· no active session</span>
      </div>
      <div>
        <span className="text-accent-500 font-bold align-middle">→</span>{" "}
        in-flight <span className="text-accent-500">N ✉</span>{" "}
        <span className="text-surface-400">· pulled, processing (no ack yet)</span>
      </div>
      <div>
        <span className="text-sky-400 font-bold align-middle">⇢</span>{" "}
        inbox <span className="text-sky-400">N ⌛</span>{" "}
        <span className="text-surface-400">· dashed: delivered, awaiting pull</span>
      </div>
      <div>
        <span className="font-bold align-middle" style={{ color: "#9ca3af" }}>→</span>{" "}
        completed flow{" "}
        <span className="text-surface-400">
          · grey fades light→dark over 15 min / 1 h / 4 h, then disappears
        </span>
      </div>
      <div>
        <span className="text-pink-500 text-sm align-middle">■</span> handoff
        aberto <span className="text-surface-400">· aguarda claim</span>
      </div>
      <div className="text-surface-400 mt-1">
        Click any element to inspect it.
      </div>
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Chat timeline - inbox/outbox of an agent as a per-peer conversation
// --------------------------------------------------------------------------- //
const FAILED_TAB = "__failed__";
const PAGE_SIZE = 10;

function laneTick(status?: string): string {
  switch (status) {
    case "unread":
      return "\u2713";
    case "delivered":
      return "\u2713\u2713";
    case "read":
      return "\u2713\u2713";
    case "parked":
      return "\u23f8";
    default:
      return "";
  }
}

function Bubble({
  agentId,
  peer,
  message,
}: {
  agentId: string;
  peer: string;
  message: MessageRow;
}) {
  const out = message.from_agent_id === agentId;
  const failed = peer === FAILED_TAB;
  const status = failed
    ? "none"
    : out
      ? (message.deliveries.find((d) => d.recipient_agent_id === peer)?.status ??
        message.deliveries[0]?.status)
      : undefined;
  const text = message.body ?? message.preview ?? "";
  return (
    <div className={`flex ${out ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[85%] rounded-xl px-2.5 py-1.5 text-[11px] leading-relaxed ${
          failed
            ? "bg-red-50 border border-red-200 text-red-700 dark:bg-red-900/20 dark:border-red-400/30 dark:text-red-200"
            : out
              ? "bg-accent-50 border border-accent-200 text-surface-800 dark:bg-accent-900/30 dark:border-accent-700/40 dark:text-surface-200"
              : "bg-surface-100 border border-surface-200 text-surface-700 dark:bg-surface-800 dark:border-surface-700 dark:text-surface-300"
        }`}
      >
        {message.subject && (
          <div className="font-semibold mb-0.5">{message.subject}</div>
        )}
        {text ? <Markdown text={text} /> : <div>(no body)</div>}
        <div className="flex items-center gap-1.5 justify-end mt-0.5 text-[9px] text-surface-400 dark:text-surface-500">
          <span>{message.created_at.slice(5, 16).replace("T", " ")}</span>
          {out && !failed && status && (
            <span
              className={status === "read" ? "text-accent-500" : ""}
              title={status}
            >
              {laneTick(status)}
            </span>
          )}
          {failed && (
            <span className="text-red-400" title="no recipient">
              {"\u2717"}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

// Per-peer conversation, server-paginated: NEWEST first, "Load more" walks
// back into history 10 messages at a time (lazy - a long history is never
// materialised up front). Peer list is an O(peers) SQL aggregate with a
// client-side search filter, so it scales past the handful-of-tabs stage.
function ChatPanel({
  agentId,
  refreshKey,
}: {
  agentId: string;
  refreshKey: number;
}) {
  const [peers, setPeers] = useState<ConversationPeer[]>([]);
  const [failedCount, setFailedCount] = useState(0);
  const [filter, setFilter] = useState("");
  const [tab, setTab] = useState<string | null>(null);
  const [entries, setEntries] = useState<MessageRow[]>([]);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  // Latest open tab, read by the refresh path without re-subscribing to it.
  const tabRef = useRef<string | null>(null);
  useEffect(() => {
    tabRef.current = tab;
  }, [tab]);

  const fetchPage = (peer: string, pageNum: number, append: boolean) => {
    setLoading(true);
    const params: Record<string, string> = {
      agent: agentId,
      include_body: "true",
      page: String(pageNum),
      page_size: String(PAGE_SIZE),
    };
    if (peer === FAILED_TAB) params.undelivered = "true";
    else params.peer = peer;
    api
      .messages(params)
      .then(({ items, total: t }) => {
        setEntries((prev) => (append ? [...prev, ...items] : items));
        setPage(pageNum);
        setTotal(t);
      })
      .catch(() => undefined)
      .finally(() => setLoading(false));
  };

  // Reload the peer list. preserveTab=true (refresh / live) keeps the open
  // conversation and refetches its newest page; false (agent change) selects
  // the first peer.
  const loadPeers = (preserveTab: boolean) => {
    api
      .conversationPeers(agentId)
      .then(({ items, failed_count }) => {
        setPeers(items);
        setFailedCount(failed_count);
        const cur = tabRef.current;
        const keep =
          preserveTab &&
          cur != null &&
          (cur === FAILED_TAB
            ? failed_count > 0
            : items.some((p) => p.peer === cur));
        const next = keep
          ? cur
          : (items[0]?.peer ?? (failed_count > 0 ? FAILED_TAB : null));
        setTab(next);
        if (next) fetchPage(next, 1, false);
        else {
          setEntries([]);
          setTotal(0);
        }
      })
      .catch(() => undefined);
  };

  useEffect(() => {
    setFilter("");
    loadPeers(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agentId]);

  // Refresh button / live update: reload preserving the open tab. Skip mount.
  const firstRefresh = useRef(true);
  useEffect(() => {
    if (firstRefresh.current) {
      firstRefresh.current = false;
      return;
    }
    loadPeers(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshKey]);

  const openTab = (peer: string) => {
    setTab(peer);
    setEntries([]);
    fetchPage(peer, 1, false);
  };

  const visiblePeers = filter
    ? peers.filter((p) =>
        p.peer.toLowerCase().includes(filter.trim().toLowerCase()),
      )
    : peers;

  if (peers.length === 0 && failedCount === 0) {
    return (
      <div className="text-surface-400 dark:text-surface-500">
        no conversations yet
      </div>
    );
  }
  const remaining = Math.max(0, total - entries.length);

  return (
    <div className="flex flex-col gap-2 flex-1 min-h-0" data-testid="chat-panel">
      {peers.length > 6 && (
        <div className="relative shrink-0">
          <Search
            size={12}
            className="absolute left-2 top-1/2 -translate-y-1/2 text-surface-400"
          />
          <input
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder={`search ${peers.length} peers\u2026`}
            className="w-full pl-6 pr-2 py-1 rounded-lg text-[11px] border border-surface-200 dark:border-surface-700 bg-white dark:bg-surface-800 focus:outline-none focus:ring-2 focus:ring-accent-500/40"
            data-testid="peer-search"
          />
        </div>
      )}
      <div className="flex flex-wrap gap-1 max-h-20 overflow-y-auto pb-1 shrink-0">
        {visiblePeers.map(({ peer, count }) => (
          <button
            key={peer}
            onClick={() => openTab(peer)}
            className={`px-2 py-1 rounded-lg text-[11px] whitespace-nowrap border transition-colors ${
              peer === tab
                ? "bg-accent-100 text-accent-700 border-accent-300 dark:bg-accent-900/40 dark:text-accent-300 dark:border-accent-700"
                : "border-surface-200 text-surface-500 hover:text-surface-800 dark:border-surface-700 dark:text-surface-400 dark:hover:text-surface-200"
            }`}
          >
            {peer}
            <span className="ml-1 opacity-60">{count}</span>
          </button>
        ))}
        {filter && visiblePeers.length === 0 && (
          <span className="text-[11px] text-surface-400 px-1 py-1">
            no peer matches "{filter}"
          </span>
        )}
        {failedCount > 0 && (
          <button
            onClick={() => openTab(FAILED_TAB)}
            className={`px-2 py-1 rounded-lg text-[11px] whitespace-nowrap border transition-colors ${
              tab === FAILED_TAB
                ? "bg-red-50 text-red-600 border-red-300 dark:bg-red-900/30 dark:text-red-300 dark:border-red-400/40"
                : "border-surface-200 text-surface-500 hover:text-red-500 dark:border-surface-700 dark:text-surface-400"
            }`}
          >
            {"\u26a0"} no recipient
            <span className="ml-1 opacity-60">{failedCount}</span>
          </button>
        )}
      </div>

      {tab === FAILED_TAB && (
        <p className="text-[11px] text-red-500/80 dark:text-red-300/80 shrink-0">
          Persisted sends whose target resolved to no eligible recipient
          {" \u2014 "}delivered to nobody. Sends to a nonexistent agent_id are
          rejected with no trace (full rollback, by bus design).
        </p>
      )}

      {/* Newest first; "Load more" appends OLDER messages below. */}
      <div className="flex-1 min-h-0 overflow-y-auto space-y-1.5 pr-1">
        {tab &&
          entries.map((m) => (
            <Bubble key={m.message_id} agentId={agentId} peer={tab} message={m} />
          ))}
        {remaining > 0 && (
          <button
            onClick={() => tab && fetchPage(tab, page + 1, true)}
            disabled={loading}
            className="w-full py-1.5 rounded-lg text-[11px] border border-surface-200 dark:border-surface-700 text-surface-500 hover:text-surface-800 dark:text-surface-400 dark:hover:text-surface-200 hover:bg-surface-50 dark:hover:bg-surface-800 transition-colors disabled:opacity-50"
            data-testid="load-more"
          >
            {loading ? "loading\u2026" : `Load more (${remaining} older)`}
          </button>
        )}
      </div>
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Side panel content (rendered inside the ResizablePanel)
// --------------------------------------------------------------------------- //
function SidePanel({
  selection,
  workspace,
  theme,
  onClose,
  onChanged,
  liveTick,
  sseStatus,
}: {
  selection: NonNullable<Selection>;
  workspace: string;
  theme: ThemeName;
  onClose: () => void;
  onChanged: () => void;
  liveTick?: number;
  sseStatus?: SSEStatus;
}) {
  const { confirm, dialog } = useConfirm();
  const [sessions, setSessions] = useState<
    { session_id: string; status: string; last_heartbeat_at: string | null }[]
  >([]);
  // Bumping refreshKey re-runs every data fetch in this panel (sessions + the
  // chat/pair timeline). Driven by the manual Refresh button and, while the
  // panel is open, by live bus activity (liveTick).
  const [refreshKey, setRefreshKey] = useState(0);
  const refresh = () => {
    setRefreshKey((k) => k + 1);
    onChanged(); // also refresh the underlying graph (edge/node badges)
  };

  const agentId = selection.kind === "node" ? selection.node.agent_id : "";

  // Live update: a new bus event (liveTick changes) refreshes the panel,
  // debounced so a burst coalesces into one refetch. The initial mount is
  // skipped — the fetches below already run when the panel opens.
  const liveSeen = useRef(false);
  useEffect(() => {
    if (!liveSeen.current) {
      liveSeen.current = true;
      return;
    }
    const t = window.setTimeout(() => setRefreshKey((k) => k + 1), 700);
    return () => window.clearTimeout(t);
  }, [liveTick]);

  useEffect(() => {
    if (selection.kind === "node") {
      api
        .sessions(workspace === "all" ? undefined : workspace)
        .then(({ items }) =>
          setSessions(items.filter((s) => s.agent_id === agentId)),
        )
        .catch(() => undefined);
    }
  }, [selection, agentId, workspace, refreshKey]);

  return (
    <div className="text-xs flex flex-col gap-3 flex-1 min-h-0">
      {dialog}
      <div className="flex items-center justify-between shrink-0">
        <span className="font-display font-semibold text-sm text-surface-900 dark:text-surface-100">
          {selection.kind === "node"
            ? selection.node.agent_id
            : selection.kind === "edge"
              ? `${selection.edge.from} → ${selection.edge.to}`
              : `Handoff · ${selection.handoff.status}`}
        </span>
        <div className="flex items-center gap-1.5">
          {/* Live monitor indicator: this panel refetches on every bus event
              (liveTick) while open, so it carries the SAME ● Live chip as the
              header/canvas, reflecting the real SSE connection state. */}
          <LiveChip status={sseStatus ?? "off"} />
          <button
            className="btn btn-secondary !px-2"
            onClick={refresh}
            title="Refresh"
            data-testid="side-panel-refresh"
          >
            <RotateCw size={14} />
          </button>
          <button
            className="btn btn-secondary !px-2"
            onClick={onClose}
            title="Close"
          >
            <X size={14} />
          </button>
        </div>
      </div>

      {selection.kind === "handoff" && (
        <div className="space-y-2">
          <div className="text-surface-500 dark:text-surface-400">
            <span
              className={`chip mr-2 ${
                selection.handoff.status === "OPEN"
                  ? "bg-pink-100 text-pink-700 dark:bg-pink-900/40 dark:text-pink-300"
                  : "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300"
              }`}
            >
              {selection.handoff.status}
            </span>
            <span className="font-mono text-surface-400">
              {selection.handoff.handoff_id}
            </span>
          </div>
          <div className="text-surface-500 dark:text-surface-400">
            created by <b>{selection.handoff.from_agent_id ?? "—"}</b>
            {selection.handoff.claimed_by && (
              <>
                {" "}
                · claimed by <b>{selection.handoff.claimed_by}</b>
              </>
            )}
          </div>
          <div className="text-surface-400">{selection.handoff.created_at}</div>
          <div className="bg-surface-100 dark:bg-surface-900 border border-surface-200 dark:border-surface-700 rounded-lg p-2 font-mono text-[11px] text-surface-600 dark:text-surface-300 overflow-x-auto">
            target: {JSON.stringify(selection.handoff.target ?? null)}
          </div>
          <p className="text-[11px] text-surface-400">
            {selection.handoff.status === "OPEN"
              ? "Awaiting claim: any eligible agent can claim it via handoff_claim (first one wins)."
              : "Being executed by the claiming agent; if the lease expires it returns to the pool."}
          </p>
          {(selection.handoff.status === "OPEN" ||
            selection.handoff.status === "CLAIMED") && (
            <button
              className="btn btn-danger"
              data-testid="cancel-handoff"
              onClick={() =>
                confirm({
                  title: "Cancel handoff?",
                  body: (
                    <span>
                      O handoff <code>{selection.handoff.handoff_id}</code> will be
                      moved to CANCELLED and leaves the claim pool.
                    </span>
                  ),
                  onConfirm: async () => {
                    await api.cancelHandoff(
                      selection.handoff.handoff_id,
                      selection.handoff.workspace_id,
                    );
                    onChanged();
                    onClose();
                  },
                })
              }
            >
              <Ban size={14} /> Cancel handoff…
            </button>
          )}
        </div>
      )}

      {selection.kind === "node" && (
        <>
          <div className="text-surface-500 dark:text-surface-400 shrink-0">
            role: {selection.node.role ?? "—"} · presence:{" "}
            <b style={{ color: presenceColor(selection.node.presence, theme) }}>
              {selection.node.presence}
            </b>
          </div>
          <div className="text-surface-400 shrink-0">
            caps: {Object.keys(selection.node.capabilities).join(", ") || "—"}
          </div>
          <div className="border-t border-surface-200 dark:border-surface-700 pt-2 shrink-0">
            <div className="text-surface-600 dark:text-surface-300 font-medium mb-1">
              Inbox lanes
            </div>
            <div className="grid grid-cols-4 gap-1 text-center">
              {(["unread", "delivered", "read", "parked"] as const).map((lane) => (
                <div
                  key={lane}
                  className="bg-surface-100 dark:bg-surface-900 rounded-lg p-1 text-surface-500 dark:text-surface-400"
                >
                  {lane}
                  <br />
                  <b className="text-accent-600 dark:text-accent-400">
                    {selection.node.inbox[lane]}
                  </b>
                </div>
              ))}
            </div>
          </div>
          <div className="border-t border-surface-200 dark:border-surface-700 pt-2 space-y-1 shrink-0 max-h-32 overflow-y-auto">
            <div className="text-surface-600 dark:text-surface-300 font-medium">
              Sessions
            </div>
            {sessions.length === 0 && (
              <div className="text-surface-400">no sessions</div>
            )}
            {sessions.map((s) => (
              <div key={s.session_id} className="flex items-center gap-2">
                <span className="font-mono text-surface-600 dark:text-surface-300">
                  {s.session_id.slice(0, 10)}…
                </span>
                <span className="text-surface-400">{s.status}</span>
                {s.status === "active" && (
                  <button
                    className="btn btn-secondary !py-0.5 !text-xs text-red-500 ml-auto"
                    onClick={() =>
                      confirm({
                        title: "Close session?",
                        body: (
                          <span>
                            Session <code>{s.session_id}</code> of{" "}
                            <b>{agentId}</b> will be closed.
                          </span>
                        ),
                        onConfirm: async () => {
                          await api.closeSession(s.session_id);
                          onChanged();
                        },
                      })
                    }
                  >
                    Close…
                  </button>
                )}
              </div>
            ))}
          </div>
          <div className="border-t border-surface-200 dark:border-surface-700 pt-2 flex-1 min-h-0 flex flex-col gap-1">
            <div className="text-surface-600 dark:text-surface-300 font-medium shrink-0">
              Conversations{" "}
              <span className="text-surface-400">· per peer</span>
            </div>
            <ChatPanel agentId={agentId} refreshKey={refreshKey} />
          </div>
        </>
      )}

      {selection.kind === "edge" && (
        <>
          <div className="text-surface-500 dark:text-surface-400 shrink-0">
            {selection.edge.count} messages · in flight:{" "}
            {selection.edge.in_flight.unread + selection.edge.in_flight.delivered} ·
            last: {selection.edge.last_at}
          </div>
          <div className="border-t border-surface-200 dark:border-surface-700 pt-2 flex-1 min-h-0 flex flex-col gap-1">
            <div className="text-surface-600 dark:text-surface-300 font-medium shrink-0">
              Pair conversation{" "}
              <span className="text-surface-400">
                · from {selection.edge.from}'s perspective
              </span>
            </div>
            <PairChat
              from={selection.edge.from}
              to={selection.edge.to}
              refreshKey={refreshKey}
            />
          </div>
        </>
      )}
    </div>
  );
}

// Pair conversation (edge click) - same server-paginated, newest-first
// grammar as the per-peer chat panel.
function PairChat({
  from,
  to,
  refreshKey,
}: {
  from: string;
  to: string;
  refreshKey: number;
}) {
  const [entries, setEntries] = useState<MessageRow[]>([]);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);

  const fetchPage = (pageNum: number, append: boolean) => {
    setLoading(true);
    api
      .messages({
        agent: from,
        peer: to,
        include_body: "true",
        page: String(pageNum),
        page_size: String(PAGE_SIZE),
      })
      .then(({ items, total: t }) => {
        setEntries((prev) => (append ? [...prev, ...items] : items));
        setPage(pageNum);
        setTotal(t);
      })
      .catch(() => undefined)
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    setEntries([]);
    fetchPage(1, false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [from, to, refreshKey]);

  if (entries.length === 0 && !loading) {
    return (
      <div className="text-surface-400 dark:text-surface-500">
        no messages between the pair
      </div>
    );
  }
  const remaining = Math.max(0, total - entries.length);
  return (
    <div className="flex-1 min-h-0 overflow-y-auto space-y-1.5 pr-1">
      {entries.map((m) => (
        <Bubble key={m.message_id} agentId={from} peer={to} message={m} />
      ))}
      {remaining > 0 && (
        <button
          onClick={() => fetchPage(page + 1, true)}
          disabled={loading}
          className="w-full py-1.5 rounded-lg text-[11px] border border-surface-200 dark:border-surface-700 text-surface-500 hover:text-surface-800 dark:text-surface-400 dark:hover:text-surface-200 hover:bg-surface-50 dark:hover:bg-surface-800 transition-colors disabled:opacity-50"
        >
          {loading ? "loading..." : `Load more (${remaining} older)`}
        </button>
      )}
    </div>
  );
}

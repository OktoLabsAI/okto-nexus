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
import { Ban, X } from "lucide-react";
import {
  api,
  type GraphEdge,
  type GraphHandoff,
  type GraphNode,
  type GraphSnapshot,
  type MessageRow,
} from "../api";
import { useConfirm } from "../components/Confirm";
import { ResizablePanel } from "../components/ResizablePanel";

type ThemeName = "light" | "dark";

function presenceColor(presence: GraphNode["presence"], theme: ThemeName): string {
  if (presence === "present") return "#0ea5e9";
  if (presence === "stale") return "#f59e0b";
  return theme === "dark" ? "#3f4a5c" : "#b2bdcc";
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
}: {
  graph: GraphSnapshot | null;
  workspace: string;
  onChanged: () => void;
  theme: ThemeName;
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
      const inFlight = edge.in_flight.unread + edge.in_flight.delivered;
      g.addEdgeWithKey(`m:${edge.from}->${edge.to}`, edge.from, edge.to, {
        size: 1.5 + Math.min(6, Math.log2(edge.count + 1)),
        color: inFlight > 0 ? "#0ea5e9" : dark ? "rgba(59,130,246,0.55)" : "rgba(59,130,246,0.45)",
        label: inFlight > 0 ? `${inFlight} ✉` : undefined,
        type: "arrow",
      });
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
      if (!edge.startsWith("m:")) return;
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
    return () => renderer.kill();
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
        <span className="text-blue-500 font-bold align-middle">→</span>{" "}
        messages (thickness = 24h volume)
      </div>
      <div>
        <span className="text-accent-500 font-bold align-middle">→</span>{" "}
        in-flight traffic <span className="text-accent-500">N ✉</span>{" "}
        <span className="text-surface-400">· unread in the pair</span>
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
interface ChatEntry {
  key: string;
  dir: "in" | "out";
  at: string;
  text: string;
  status?: string; // delivery lane towards the peer (out only)
}

const FAILED_TAB = "⚠ no recipient";

function laneTick(status?: string): string {
  switch (status) {
    case "unread":
      return "✓";
    case "delivered":
      return "✓✓";
    case "read":
      return "✓✓";
    case "parked":
      return "⏸";
    default:
      return "";
  }
}

function buildConversations(
  agentId: string,
  messages: MessageRow[],
): Map<string, ChatEntry[]> {
  const convos = new Map<string, ChatEntry[]>();
  const push = (peer: string, entry: ChatEntry) => {
    if (!convos.has(peer)) convos.set(peer, []);
    convos.get(peer)!.push(entry);
  };
  for (const m of messages) {
    const text = m.preview || m.subject || "(no body)";
    if (m.from_agent_id === agentId) {
      if (m.deliveries.length === 0) {
        // Persisted but fanned out to NOBODY (target resolved to zero
        // eligible recipients) - the visible trace of a failed send.
        push(FAILED_TAB, {
          key: m.message_id,
          dir: "out",
          at: m.created_at,
          text,
          status: "none",
        });
        continue;
      }
      for (const d of m.deliveries) {
        push(d.recipient_agent_id, {
          key: `${m.message_id}:${d.delivery_id}`,
          dir: "out",
          at: m.created_at,
          text,
          status: d.status,
        });
      }
    } else if (m.deliveries.some((d) => d.recipient_agent_id === agentId)) {
      push(m.from_agent_id, {
        key: m.message_id,
        dir: "in",
        at: m.created_at,
        text,
      });
    }
  }
  for (const entries of convos.values()) {
    entries.sort((a, b) => a.at.localeCompare(b.at));
  }
  return convos;
}

function Bubble({ entry }: { entry: ChatEntry }) {
  return (
    <div className={`flex ${entry.dir === "out" ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[85%] rounded-xl px-2.5 py-1.5 text-[11px] leading-relaxed ${
          entry.status === "none"
            ? "bg-red-50 border border-red-200 text-red-700 dark:bg-red-900/20 dark:border-red-400/30 dark:text-red-200"
            : entry.dir === "out"
              ? "bg-accent-50 border border-accent-200 text-surface-800 dark:bg-accent-900/30 dark:border-accent-700/40 dark:text-surface-200"
              : "bg-surface-100 border border-surface-200 text-surface-700 dark:bg-surface-800 dark:border-surface-700 dark:text-surface-300"
        }`}
      >
        <div>{entry.text}</div>
        <div className="flex items-center gap-1.5 justify-end mt-0.5 text-[9px] text-surface-400 dark:text-surface-500">
          <span>{entry.at.slice(5, 16).replace("T", " ")}</span>
          {entry.dir === "out" && entry.status !== "none" && (
            <span
              className={entry.status === "read" ? "text-accent-500" : ""}
              title={entry.status}
            >
              {laneTick(entry.status)}
            </span>
          )}
          {entry.status === "none" && (
            <span className="text-red-400" title="no recipient">
              ✗
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

function ChatPanel({ agentId }: { agentId: string }) {
  const [convos, setConvos] = useState<Map<string, ChatEntry[]>>(new Map());
  const [tab, setTab] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api
      .messages({ agent: agentId, page_size: "200" })
      .then(({ items }) => {
        const built = buildConversations(agentId, items);
        setConvos(built);
        setTab((current) =>
          current && built.has(current)
            ? current
            : (built.keys().next().value ?? null),
        );
      })
      .catch(() => undefined);
  }, [agentId]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [tab, convos]);

  const peers = [...convos.keys()].sort((a, b) => {
    if (a === FAILED_TAB) return 1;
    if (b === FAILED_TAB) return -1;
    const lastA = convos.get(a)!.at(-1)?.at ?? "";
    const lastB = convos.get(b)!.at(-1)?.at ?? "";
    return lastB.localeCompare(lastA);
  });

  if (peers.length === 0) {
    return (
      <div className="text-surface-400 dark:text-surface-500">
        no messages in the last 200
      </div>
    );
  }
  const entries = tab ? (convos.get(tab) ?? []) : [];

  return (
    <div className="space-y-2" data-testid="chat-panel">
      <div className="flex gap-1 overflow-x-auto pb-1">
        {peers.map((peer) => (
          <button
            key={peer}
            onClick={() => setTab(peer)}
            className={`px-2 py-1 rounded-lg text-[11px] whitespace-nowrap border transition-colors ${
              peer === tab
                ? peer === FAILED_TAB
                  ? "bg-red-50 text-red-600 border-red-300 dark:bg-red-900/30 dark:text-red-300 dark:border-red-400/40"
                  : "bg-accent-100 text-accent-700 border-accent-300 dark:bg-accent-900/40 dark:text-accent-300 dark:border-accent-700"
                : "border-surface-200 text-surface-500 hover:text-surface-800 dark:border-surface-700 dark:text-surface-400 dark:hover:text-surface-200"
            }`}
          >
            {peer}
            <span className="ml-1 opacity-60">{convos.get(peer)!.length}</span>
          </button>
        ))}
      </div>

      {tab === FAILED_TAB && (
        <p className="text-[11px] text-red-500/80 dark:text-red-300/80">
          Persisted sends whose target resolved to no eligible recipient —
          delivered to nobody. Sends to a nonexistent agent_id are rejected
          with no trace (full rollback, by bus design).
        </p>
      )}

      <div className="max-h-72 overflow-y-auto space-y-1.5 pr-1">
        {entries.map((entry) => (
          <Bubble key={entry.key} entry={entry} />
        ))}
        <div ref={endRef} />
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
}: {
  selection: NonNullable<Selection>;
  workspace: string;
  theme: ThemeName;
  onClose: () => void;
  onChanged: () => void;
}) {
  const { confirm, dialog } = useConfirm();
  const [sessions, setSessions] = useState<
    { session_id: string; status: string; last_heartbeat_at: string | null }[]
  >([]);

  const agentId = selection.kind === "node" ? selection.node.agent_id : "";

  useEffect(() => {
    if (selection.kind === "node") {
      api
        .sessions(workspace === "all" ? undefined : workspace)
        .then(({ items }) =>
          setSessions(items.filter((s) => s.agent_id === agentId)),
        )
        .catch(() => undefined);
    }
  }, [selection, agentId, workspace]);

  return (
    <div className="text-xs space-y-3">
      {dialog}
      <div className="flex items-center justify-between">
        <span className="font-display font-semibold text-sm text-surface-900 dark:text-surface-100">
          {selection.kind === "node"
            ? selection.node.agent_id
            : selection.kind === "edge"
              ? `${selection.edge.from} → ${selection.edge.to}`
              : `Handoff · ${selection.handoff.status}`}
        </span>
        <button className="btn btn-secondary !px-2" onClick={onClose}>
          <X size={14} />
        </button>
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
          <div className="text-surface-500 dark:text-surface-400">
            role: {selection.node.role ?? "—"} · presence:{" "}
            <b style={{ color: presenceColor(selection.node.presence, theme) }}>
              {selection.node.presence}
            </b>
          </div>
          <div className="text-surface-400">
            caps: {Object.keys(selection.node.capabilities).join(", ") || "—"}
          </div>
          <div className="border-t border-surface-200 dark:border-surface-700 pt-2">
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
          <div className="border-t border-surface-200 dark:border-surface-700 pt-2 space-y-1">
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
          <div className="border-t border-surface-200 dark:border-surface-700 pt-2 space-y-1">
            <div className="text-surface-600 dark:text-surface-300 font-medium">
              Conversations{" "}
              <span className="text-surface-400">· per peer</span>
            </div>
            <ChatPanel agentId={agentId} />
          </div>
        </>
      )}

      {selection.kind === "edge" && (
        <>
          <div className="text-surface-500 dark:text-surface-400">
            {selection.edge.count} messages · in flight:{" "}
            {selection.edge.in_flight.unread + selection.edge.in_flight.delivered} ·
            last: {selection.edge.last_at}
          </div>
          <div className="border-t border-surface-200 dark:border-surface-700 pt-2 space-y-1">
            <div className="text-surface-600 dark:text-surface-300 font-medium">
              Pair conversation{" "}
              <span className="text-surface-400">
                · from {selection.edge.from}'s perspective
              </span>
            </div>
            <PairChat from={selection.edge.from} to={selection.edge.to} />
          </div>
        </>
      )}
    </div>
  );
}

function PairChat({ from, to }: { from: string; to: string }) {
  const [entries, setEntries] = useState<ChatEntry[]>([]);

  useEffect(() => {
    api
      .messages({ agent: from, page_size: "200" })
      .then(({ items }) => {
        const convos = buildConversations(from, items);
        setEntries(convos.get(to) ?? []);
      })
      .catch(() => undefined);
  }, [from, to]);

  if (entries.length === 0) {
    return (
      <div className="text-surface-400 dark:text-surface-500">
        no messages between the pair
      </div>
    );
  }
  return (
    <div className="max-h-80 overflow-y-auto space-y-1.5 pr-1">
      {entries.map((entry) => (
        <Bubble key={entry.key} entry={entry} />
      ))}
    </div>
  );
}

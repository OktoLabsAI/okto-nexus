import type { GraphNode } from "../api";

// The Graph API does not expose a canonical activity aggregate yet. Keep the
// simple graph's sizing tied to the proxy used by the original Nexus graph:
// active sessions plus inbox work that is waiting or already being processed.
// pending_inbox follows the Graph's current workspace scope. Presence is
// deliberately excluded because the corner badge owns that signal.
export function agentActivityScore(
  node: Pick<GraphNode, "sessions" | "pending_inbox">,
): number {
  return [node.sessions, node.pending_inbox].reduce(
    (total, value) =>
      total + (Number.isFinite(value) ? Math.max(0, Math.trunc(value)) : 0),
    0,
  );
}

export const SIMPLE_NODE_MIN_RADIUS = 12;
export const SIMPLE_NODE_MAX_RADIUS = 28;

// A bounded linear scale keeps idle agents selectable and prevents a busy
// inbox from overwhelming the rest of the mesh. Equal activity always means
// equal size, regardless of online/stale/offline state.
export function simpleAgentNodeRadius(
  node: Pick<GraphNode, "sessions" | "pending_inbox">,
): number {
  return (
    SIMPLE_NODE_MIN_RADIUS +
    Math.min(
      SIMPLE_NODE_MAX_RADIUS - SIMPLE_NODE_MIN_RADIUS,
      agentActivityScore(node) * 3,
    )
  );
}

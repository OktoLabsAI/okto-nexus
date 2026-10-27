// Meta-harness "session restarted" dividers (issue #84).
// A session that ended while the same agent has a later session means the
// agent restarted. The new session has no memory of the earlier turns.
// The divider goes right before the first operator message of the new
// session: that is the first operator message after the ended session's
// last interaction.

import type { MetaHarnessSession } from "./api";

export interface RestartMarker {
  id: string;
  agentId: string;
  // Time of the last operator message that the ended session handled.
  after: string;
  // Containment reason of the ended session, when the hub reports one.
  reason: string | null;
}

export interface MarkerEntry {
  timestamp: string;
  direction: string;
  recipients: string[];
}

export function restartMarkers(sessions: MetaHarnessSession[]): RestartMarker[] {
  const groups = new Map<string, MetaHarnessSession[]>();
  for (const session of sessions) {
    const key = `${session.scope.workspace_id}:${session.scope.agent_id}`;
    groups.set(key, [...(groups.get(key) ?? []), session]);
  }
  const markers: RestartMarker[] = [];
  for (const group of groups.values()) {
    for (const ended of group) {
      if (ended.is_open) continue;
      const hasLater = group.some(
        (other) =>
          other !== ended && other.last_interaction_at > ended.last_interaction_at,
      );
      if (!hasLater) continue;
      markers.push({
        id: ended.scope.session_id,
        agentId: ended.scope.agent_id,
        after: ended.last_interaction_at,
        reason: ended.containment_reason ?? null,
      });
    }
  }
  return markers;
}

// Maps an entry index to the markers that belong right above that entry.
// A marker with no matching entry in the list is dropped.
export function placeMarkers(
  entries: MarkerEntry[],
  markers: RestartMarker[],
): Map<number, RestartMarker[]> {
  const placed = new Map<number, RestartMarker[]>();
  for (const marker of markers) {
    const index = entries.findIndex(
      (entry) =>
        entry.direction === "outgoing" &&
        entry.recipients.includes(marker.agentId) &&
        entry.timestamp > marker.after,
    );
    if (index < 0) continue;
    placed.set(index, [...(placed.get(index) ?? []), marker]);
  }
  return placed;
}

// Workspace overview (FR4): which contexts exist and the per-graph counts.

import type { GraphSnapshot } from "../api";

export function WorkspacesView({
  workspaces,
  graph,
}: {
  workspaces: string[];
  graph: GraphSnapshot | null;
}) {
  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="max-w-3xl mx-auto space-y-3" data-testid="workspaces-view">
        <div className="panel divide-y divide-surface-100 dark:divide-surface-700/50 text-xs">
          {workspaces.map((id) => (
            <div key={id} className="px-3 py-2 flex items-center gap-3">
              <span className="font-mono text-surface-700 dark:text-surface-300">{id}</span>
            </div>
          ))}
          {workspaces.length === 0 && (
            <div className="px-3 py-6 text-surface-400 dark:text-surface-500">
              No workspaces with sessions yet — workspaces appear when an agent
              opens a session via session_open.
            </div>
          )}
        </div>
        {graph && (
          <div className="text-xs text-surface-500 dark:text-surface-400">
            current snapshot: {graph.nodes.length} agents ·{" "}
            {graph.edges.messages.length} pairs with traffic ·{" "}
            {graph.edges.handoffs.length} active handoffs · window{" "}
            {graph.window_hours}h
          </div>
        )}
      </div>
    </div>
  );
}

import { createContext, useContext, useMemo, type ReactNode } from "react";
import type { WorkspaceListItem } from "../api";

function pathName(path: string | null): string | null {
  if (!path) return null;
  const parts = path.replace(/\\/g, "/").split("/").filter(Boolean);
  return parts.at(-1) ?? null;
}

export function workspaceDisplayName(
  workspace: WorkspaceListItem,
  index?: number,
): string {
  return (
    workspace.display_name?.trim() ||
    pathName(workspace.root_realpath) ||
    (index === undefined ? "Unnamed workspace" : `Workspace ${index + 1}`)
  );
}

const WorkspaceNamesContext = createContext<Record<string, string>>({});

export function WorkspaceNamesProvider({
  workspaces,
  children,
}: {
  workspaces: WorkspaceListItem[];
  children: ReactNode;
}) {
  const names = useMemo(
    () =>
      Object.fromEntries(
        workspaces.map((workspace, index) => [
          workspace.workspace_id,
          workspaceDisplayName(workspace, index),
        ]),
      ),
    [workspaces],
  );
  return (
    <WorkspaceNamesContext.Provider value={names}>
      {children}
    </WorkspaceNamesContext.Provider>
  );
}

export function useWorkspaceName(workspaceId: string | null | undefined): string {
  const names = useContext(WorkspaceNamesContext);
  if (!workspaceId) return "—";
  if (workspaceId === "all") return "All workspaces";
  return names[workspaceId] ?? "Unavailable workspace";
}

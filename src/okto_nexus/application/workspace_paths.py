"""Private workspace folder suggestions for an operator's execution host."""

import json
import os

from ..bootstrap.execution_authority import build_execution_access
from ..errors import ErrorCode, OktoNexusError
from .connection_setup import require_operator


def list_workspace_paths(deps, context, *, workspace_id: str, executor_id: str) -> dict:
    """Aggregate previously approved, normalized roots on this executor.

    A workspace is a logical identity and can map to different folders on
    different machines. Local realization records contain the canonical path;
    remote Connector paths are private to their host and are never inferred
    from a Server path.
    """
    with deps.connection_factory.unit_of_work(write=False) as uow:
        require_operator(build_execution_access(deps), context, uow)
        conn = uow.connection
        if conn.execute(
            "SELECT 1 FROM workspaces WHERE workspace_id=?", (workspace_id,)
        ).fetchone() is None:
            raise OktoNexusError(ErrorCode.NOT_FOUND, "Workspace not found.", {})
        executor = conn.execute(
            "SELECT server_id,kind FROM execution_executors WHERE executor_id=?",
            (executor_id,),
        ).fetchone()
        if executor is None:
            raise OktoNexusError(ErrorCode.NOT_FOUND, "Execution host not found.", {})
        if executor["kind"] != "embedded":
            return {"workspace_id": workspace_id, "executor_id": executor_id, "items": []}
        rows = conn.execute(
            "SELECT l.local_record_json,l.created_at FROM execution_local_realizations l "
            "JOIN execution_realizations r ON r.server_id=l.server_id "
            "AND r.executor_id=l.executor_id AND r.realization_ref=l.realization_ref "
            "JOIN execution_workspace_bindings w ON w.server_id=r.server_id "
            "AND w.executor_id=r.executor_id AND w.workspace_binding_id=r.workspace_binding_id "
            "WHERE w.workspace_id=? AND l.server_id=? AND l.executor_id=? "
            "ORDER BY l.created_at DESC",
            (workspace_id, executor["server_id"], executor_id),
        ).fetchall()
        paths: dict[str, str] = {}
        for row in rows:
            try:
                path = json.loads(row["local_record_json"])["root"]["path"]
            except (TypeError, ValueError, KeyError):
                continue
            if isinstance(path, str) and path:
                paths.setdefault(os.path.normcase(os.path.normpath(path)), path)
        return {
            "workspace_id": workspace_id,
            "executor_id": executor_id,
            "items": [{"path": path} for path in paths.values()],
        }

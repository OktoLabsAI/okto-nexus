"""R4 logical workspace binding; remote root handles are never local paths."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import re

from nexus_connector_core.protocol import canonical_json

from ....errors import ErrorCode, OktoNexusError
from .connection import ConnectionFactory


_HANDLE = re.compile(r"^root_[A-Za-z0-9_-]{16,128}$")


@dataclass(frozen=True, slots=True)
class WorkspaceExecutorBinding:
    server_id: str
    executor_id: str
    workspace_id: str
    workspace_binding_id: str
    realization_handle: str
    revision: int
    status: str


def workspace_binding_diff_hash(*, server_id: str, executor_id: str,
                                workspace_id: str, subject_agent_id: str,
                                realization_handle: str) -> str:
    """Hash exactly the scope and opaque root handle approved in a proposal."""
    if not isinstance(realization_handle, str) or not _HANDLE.fullmatch(realization_handle):
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR,
                              "An opaque executor root handle is required.", {})
    fields = (server_id, executor_id, workspace_id, subject_agent_id)
    if any(not isinstance(value, str) or not 1 <= len(value) <= 160
           for value in fields):
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR,
                              "Invalid workspace binding scope.", {})
    semantic = {"server_id": server_id, "executor_id": executor_id,
                "workspace_id": workspace_id,
                "subject_agent_id": subject_agent_id,
                "realization_handle": realization_handle}
    return "sha256:" + hashlib.sha256(canonical_json(semantic)).hexdigest()


def bind_approved_workspace(factory: ConnectionFactory, *, proposal_id: str,
                            server_id: str, executor_id: str,
                            workspace_id: str, subject_agent_id: str,
                            realization_handle: str,
                            now: datetime | None = None) -> WorkspaceExecutorBinding:
    """Record an approved logical mapping awaiting executor root validation.

    The caller must have obtained the handle from the executor's realization
    result. This function only checks approval and persists the mapping; it
    never resolves, stats or compares remote filesystem paths.
    """
    if not isinstance(proposal_id, str) or not 1 <= len(proposal_id) <= 160:
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR,
                              "Invalid proposal ID.", {})
    digest = workspace_binding_diff_hash(
        server_id=server_id, executor_id=executor_id,
        workspace_id=workspace_id, subject_agent_id=subject_agent_id,
        realization_handle=realization_handle,
    )
    instant = now or datetime.now(timezone.utc)
    if instant.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    binding_id = "wxb_" + hashlib.sha256(
        canonical_json({"server_id": server_id, "proposal_id": proposal_id})
    ).hexdigest()[:32]
    with factory.unit_of_work() as uow:
        conn = uow.connection
        proposal = conn.execute(
            "SELECT executor_id,subject_agent_id,diff_hash,expires_at,status "
            "FROM execution_proposals WHERE proposal_id=? AND server_id=?",
            (proposal_id, server_id),
        ).fetchone()
        if (proposal is None or proposal["executor_id"] != executor_id or
                proposal["subject_agent_id"] != subject_agent_id or
                proposal["diff_hash"] != digest or proposal["status"] != "APPLIED"):
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED,
                                  "No applied proposal matches this workspace binding.", {})
        existing = conn.execute(
            "SELECT workspace_id,executor_id,realization_handle,revision,status "
            "FROM execution_workspace_bindings WHERE server_id=? AND workspace_binding_id=?",
            (server_id, binding_id),
        ).fetchone()
        if existing is not None:
            if (existing["workspace_id"] != workspace_id or
                    existing["executor_id"] != executor_id or
                    existing["realization_handle"] != realization_handle):
                raise OktoNexusError(ErrorCode.CONFLICT,
                                      "The proposal is bound to another realization.", {})
            return WorkspaceExecutorBinding(
                server_id, executor_id, workspace_id, binding_id,
                realization_handle, existing["revision"], existing["status"],
            )
        expires = datetime.fromisoformat(proposal["expires_at"].replace("Z", "+00:00"))
        if expires.tzinfo is None or expires <= instant:
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED,
                                  "The workspace binding proposal has expired.", {})
        conn.execute(
            "INSERT INTO execution_workspace_bindings(server_id,workspace_binding_id,"
            "executor_id,workspace_id,realization_handle,revision,status) "
            "VALUES (?,?,?,?,?,1,'PENDING_VALIDATION')",
            (server_id, binding_id, executor_id, workspace_id,
             realization_handle),
        )
        return WorkspaceExecutorBinding(server_id, executor_id, workspace_id,
                                        binding_id, realization_handle, 1,
                                        "PENDING_VALIDATION")

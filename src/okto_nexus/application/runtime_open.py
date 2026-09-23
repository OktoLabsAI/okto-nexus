"""Canonical authenticated open use case, including crash-safe idempotency."""
import hashlib
import json

from ..domain.base import check_inline_size
from ..errors import ErrorCode, OktoNexusError
from .runtime_authorization import require_runtime_agent


class RuntimeOpenService:
    def __init__(self, *, connection_factory, endpoints, agents, sessions, requests, supervisor, construct, clock, owner_guard):
        self.cf, self.endpoints, self.agents, self.sessions = connection_factory, endpoints, agents, sessions
        self.requests, self.supervisor, self.construct, self.clock = requests, supervisor, construct, clock
        self.owner_guard = owner_guard

    def open(self, context, *, agent_id, kind, project_root, substrate=None, endpoint_id=None,
             target_pid=None, backend=None, role=None, metadata=None, notify_target=None, idempotency_key=None):
        endpoint, profile = self.endpoints.resolve(context, endpoint_id=endpoint_id, agent_id=agent_id,
            kind=kind, substrate=substrate, project_root=project_root)
        require_runtime_agent(agents=self.agents, connection_factory=self.cf, agent_id=agent_id, role=role)
        if backend:
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Use an approved runtime profile, not per-call backend options.", {})
        if target_pid is not None and target_pid != endpoint["public_config"].get("target_pid"):
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "Attach target does not match the approved endpoint.", {})
        if idempotency_key is not None and (not isinstance(idempotency_key, str) or not 1 <= len(idempotency_key) <= 128):
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Idempotency key must contain 1..128 characters.", {})
        spec = dict(endpoint_id=endpoint["endpoint_id"], endpoint_revision=endpoint["revision"],
                    profile_revision=profile["revision"] if profile else None, role=role, metadata=metadata, notify_target=notify_target)
        check_inline_size("runtime open", spec, 65536)
        profile_view = {"profile_id": endpoint["profile_id"], "inherit_ambient": bool(profile and profile["inherit_ambient"]),
                        "revision": profile["revision"] if profile else None}
        request_id = None
        if idempotency_key is not None:
            digest = hashlib.sha256(json.dumps(spec, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            with self.cf.unit_of_work() as uow:
                request_id, existing = self.requests.reserve(uow, actor_id=context.actor_agent_id or "operator",
                    key=idempotency_key, request_hash=digest, now=self.clock.now_iso())
                if existing:
                    return self.sessions.get(uow, session_id=existing), profile_view, True, request_id
        starting = False
        try:
            if not self.owner_guard():
                raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "Runtime effects require the active serve owner.", {})
            connector, _, _ = self.construct(endpoint=endpoint, profile=profile, kind=kind,
                project_root=project_root, substrate=substrate, target_pid=target_pid)
            starting = True
            session = self.supervisor.open(kind=kind, connector=connector, owning_agent_id=agent_id,
                project_root=project_root, role=role, endpoint_id=endpoint["endpoint_id"], workspace_id=endpoint["workspace_id"],
                metadata=metadata, notify_target=notify_target, open_request_id=request_id,
                profile_revision=profile["revision"] if profile else None)
            if request_id:
                with self.cf.unit_of_work() as uow:
                    self.requests.finish(uow, request_id=request_id, status="COMPLETED")
            return session, profile_view, False, request_id
        except Exception as exc:
            if request_id:
                with self.cf.unit_of_work() as uow:
                    self.requests.finish(uow, request_id=request_id, status="OUTCOME_UNKNOWN" if starting else "FAILED_FINAL")
            if isinstance(exc, OktoNexusError):
                raise
            raise OktoNexusError(ErrorCode.INTERNAL_ERROR,
                "Runtime opening failed; inspect the durable request before retrying.",
                {"request_id": request_id, "exception_type": type(exc).__name__}) from exc

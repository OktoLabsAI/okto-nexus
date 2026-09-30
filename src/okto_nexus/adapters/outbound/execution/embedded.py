"""Nexus-owned adapter for the public Core runtime port.

Only the Server dispatcher should construct this adapter from a selected
local installation and an admitted session context. It never imports the
Connector application and never chooses a provider path from an HTTP body.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path

from nexus_connector_core import (
    CloseOperation, ControlOperation, CoreError, ExecutionContext,
    InstallationCandidate, LaunchIntent, OpenOperation, OperationReceipt,
    PreparedLaunch, R4LeaseApplication, ShutdownPolicy, TurnOperation, r4_lease_renew_frame,
)

from ....bootstrap.runtime_host import EmbeddedRuntimeHost


def core_error_projection(error: CoreError) -> dict[str, object]:
    """Carry the Core's classifications without inferring effect safety."""
    return {"code": error.code, "stage": error.stage,
            "possible_effect": error.possible_effect,
            "retry_safe": error.retry_safe,
            "operation_id": error.operation_id,
            "message": error.message}


class EmbeddedExecutor:
    """Use one approved local selection and exact Core context per session."""

    @classmethod
    async def authorize_r4(
        cls, host: EmbeddedRuntimeHost, *, scope: Mapping[str, object],
        grant_id: str, connection_id: str, connection_generation: int,
        candidate: InstallationCandidate, workspace_root: str,
        environment: Callable[[PreparedLaunch], Awaitable[Mapping[str, str]]],
        request_grant: Callable[[dict], Awaitable[Mapping[str, object]]],
        native_factory=None,
    ) -> tuple[EmbeddedExecutor, R4LeaseApplication]:
        """Install canonical Server authority before prepare or native open.

        The Server supplies an authenticated grant issuer after admission.
        This callback must persist its grant before returning it. Core owns
        the request nonce, monotonic t0, context and application ACK.
        """
        scope = dict(scope)
        runtime = await host.acquire(
            executor_id=scope["executor_id"], session_id=scope["session_id"],
            candidates={candidate.adapter_id: candidate},
            workspace_roots={scope["workspace_id"]: workspace_root},
            environment=environment, native_factory=native_factory)
        attempt = await runtime.begin_r4_lease_request(
            scope=scope, grant_id=grant_id, connection_id=connection_id,
            connection_generation=connection_generation, purpose="initial")
        grant = await request_grant(r4_lease_renew_frame(attempt))
        application = await runtime.install_r4_lease(attempt, grant)
        executor = cls(
            host, context=application.context, session_id=scope["session_id"],
            candidate=candidate, workspace_root=workspace_root,
            environment=environment, native_factory=native_factory)
        return executor, application

    async def renew_r4(
        self, *, scope: Mapping[str, object], connection_id: str,
        connection_generation: int,
        request_grant: Callable[[dict], Awaitable[Mapping[str, object]]],
        purpose: str = "renew",
    ) -> R4LeaseApplication:
        if self.context.r4_authority is None:
            raise CoreError("LEASE_REVALIDATION_REQUIRED", "embedded_renew")
        runtime = await self._runtime()
        attempt = await runtime.begin_r4_lease_request(
            scope=scope, grant_id=self.context.r4_authority.grant_id,
            connection_id=connection_id,
            connection_generation=connection_generation, purpose=purpose)
        grant = await request_grant(r4_lease_renew_frame(attempt))
        application = await runtime.install_r4_lease(attempt, grant)
        self.context = application.context
        return application

    async def revoke_r4(self, *, authorization_revision: int) -> R4LeaseApplication:
        runtime = await self._runtime()
        application = await runtime.revoke_r4_lease(
            self.context, authorization_revision=authorization_revision)
        # Retain the original context to correlate a retry of this revocation.
        # Core refuses subsequent effects even if the caller retains it.
        return application

    def __init__(
        self, host: EmbeddedRuntimeHost, *, context: ExecutionContext,
        session_id: str, candidate: InstallationCandidate,
        workspace_root: str,
        environment: Callable[[PreparedLaunch], Awaitable[Mapping[str, str]]],
        native_factory=None,
    ):
        if not isinstance(context, ExecutionContext):
            raise TypeError("An approved Core execution context is required.")
        if not isinstance(session_id, str) or not session_id:
            raise ValueError("A session ID is required.")
        if not isinstance(candidate, InstallationCandidate):
            raise TypeError("A selected Core installation is required.")
        if not Path(workspace_root).is_absolute():
            raise ValueError("A local absolute workspace root is required.")
        if not callable(environment):
            raise TypeError("A per-session environment callback is required.")
        self.host = host
        self.context = context
        self.session_id = session_id
        self.candidate = candidate
        self.workspace_root = workspace_root
        self.environment = environment
        self.native_factory = native_factory

    async def _runtime(self):
        return await self.host.acquire(
            executor_id=self.context.executor_id, session_id=self.session_id,
            candidates={self.candidate.adapter_id: self.candidate},
            workspace_roots={self.context.workspace_id: self.workspace_root},
            environment=self.environment, native_factory=self.native_factory,
        )

    async def open(self, *, operation_id: str, stream_epoch: str,
                   mode: str = "managed", model: str | None = None,
                   auth_refs: tuple[str, ...] = ()) -> OperationReceipt:
        runtime = await self._runtime()
        prepared = await runtime.prepare(
            LaunchIntent(agent_id=self.context.agent_id,
                         workspace_id=self.context.workspace_id,
                         adapter_id=self.candidate.adapter_id,
                         mode=mode, model=model, auth_refs=auth_refs),
            self.context,
        )
        return await runtime.open(
            OpenOperation(operation_id=operation_id,
                          session_id=self.session_id,
                          stream_epoch=stream_epoch, prepared=prepared),
            self.context,
        )

    async def submit(self, *, operation_id: str, text: str,
                     expected_turn_id: str | None = None) -> OperationReceipt:
        runtime = await self._runtime()
        return await runtime.submit(
            TurnOperation(operation_id=operation_id,
                          session_id=self.session_id, text=text,
                          expected_turn_id=expected_turn_id),
            self.context,
        )

    async def control(self, *, operation_id: str, verb: str,
                      text: str | None = None,
                      expected_turn_id: str | None = None,
                      reason: str | None = None) -> OperationReceipt:
        runtime = await self._runtime()
        return await runtime.control(
            ControlOperation(operation_id=operation_id,
                             session_id=self.session_id, verb=verb,
                             text=text, expected_turn_id=expected_turn_id,
                             reason=reason),
            self.context,
        )

    async def close(self, *, operation_id: str,
                    reason: str | None = None,
                    policy: ShutdownPolicy | None = None) -> OperationReceipt:
        runtime = await self._runtime()
        if self.context.r4_authority is not None and policy is None:
            policy = ShutdownPolicy()
        if self.context.r4_authority is not None and reason is None:
            reason = "Close requested by the authorized agent."
        return await runtime.close(
            CloseOperation(operation_id=operation_id,
                           session_id=self.session_id,
                           reason=reason, policy=policy), self.context)

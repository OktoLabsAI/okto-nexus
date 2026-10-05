"""Embedded Core native actions through the same canonical domain as HTTP."""

import anyio
from dataclasses import replace
from nexus_connector_core import CoreError
from nexus_connector_core.clock import RollbackFencedClock, SystemClock
from nexus_connector_core.native_action_bridge import (
    ScopedNativeActionBridge, native_action_scope, native_action_request_body,
)
from nexus_connector_core.protocol import canonical_json

from ....bootstrap.execution_authority import build_native_action_service
from ....errors import OktoNexusError


class EmbeddedNativeActions:
    def __init__(self, deps, grant, capability):
        self._service = build_native_action_service(deps)
        self._scope = native_action_scope(grant.r4_scope)
        self._reference = grant.capability_ref
        self._capability = capability

    async def _invoke(self, request):
        body = native_action_request_body(request, self._scope)
        if request.capability_ref != self._reference:
            raise CoreError('BINDING_NOT_AUTHORIZED', 'native_action')
        def invoke():
            principal = self._service.capabilities.authenticate_transport(
                token=self._capability, audience='nexus-native-session')
            if ('native-cap:' + principal.capability_id != self._reference
                    or canonical_json(dict(principal.scope)) != canonical_json(self._scope)):
                raise CoreError('BINDING_NOT_AUTHORIZED', 'native_action')
            return self._service.invoke(principal=principal, body=body)['result']
        try:
            return await anyio.to_thread.run_sync(invoke)
        except OktoNexusError as error:
            raise CoreError(error.code, 'native_action', operation_id=request.operation_id,
                            message=error.message) from None

    async def get_context(self, request, context):
        return await self._invoke(request)

    async def create_message(self, request, context):
        return await self._invoke(request)

    async def list_runtime_inputs(self, request, context):
        return await self._invoke(request)

    async def respond_runtime_input(self, request, context):
        return await self._invoke(request)

    async def claim_handoff(self, request, context):
        return await self._invoke(request)

    async def complete_handoff(self, request, context):
        return await self._invoke(request)


def embedded_native_action_bridge(deps, grant, capability, runtime, *, clock=None):
    return ScopedNativeActionBridge(EmbeddedNativeActions(deps, grant, capability),
                                    grant, clock=clock, r4_runtime=runtime)


class RefreshingEmbeddedNativeActionBridge:
    """Renew only the deadline proven by matching applied Server/Core leases."""

    def __init__(self, deps, grant, capability, runtime, metadata_provider, *, clock=None):
        self.deps, self.grant, self.capability = deps, grant, capability
        self.runtime, self.metadata_provider = runtime, metadata_provider
        self.clock = RollbackFencedClock(clock or SystemClock())

    async def invoke(self, request, context):
        grant = self.grant
        def current():
            value = self.runtime.r4_native_action_context(grant.r4_scope,
                connection_id=grant.r4_connection_id, connection_generation=grant.connection_generation)
            if value != context:
                raise CoreError('STALE_GENERATION', 'native_action')
            return value
        current()
        try:
            metadata, deadline = await self.metadata_provider()
        except OktoNexusError as error:
            raise CoreError(error.code, 'native_action', operation_id=request.operation_id,
                            message=error.message) from None
        authority = current().r4_authority
        if (metadata['capability_ref'] != grant.capability_ref
                or canonical_json(metadata['scope']) != canonical_json(dict(grant.r4_scope))
                or metadata['audience'] != 'nexus-native-session'
                or set(metadata['actions']) != grant.allowed_actions or metadata['mcp_url'] is not None
                or authority is None or (metadata['lease_id'], metadata['lease_serial']) !=
                    (authority.lease_id, authority.lease_serial)):
            raise CoreError('STALE_GENERATION', 'native_action')
        renewed = replace(grant, expires_monotonic=min(deadline, context.lease_deadline_monotonic))
        bridge = embedded_native_action_bridge(self.deps, renewed, self.capability, self.runtime,
                                                clock=self.clock)
        return await bridge.invoke(request, context)


def embedded_native_action_owner_factory(deps, grant, capability, *, clock=None, metadata_provider=None):
    """Bind a protected native capability to one embedded Pi launch."""
    from dataclasses import replace
    from types import MappingProxyType
    from nexus_connector_core.native_action_socket import PiNativeActionOwner
    grant = replace(grant, r4_scope=MappingProxyType(native_action_scope(grant.r4_scope)),
                    allowed_actions=frozenset(grant.allowed_actions))
    def build(runtime):
        bridge = (embedded_native_action_bridge(deps, grant, capability, runtime, clock=clock)
                  if metadata_provider is None else RefreshingEmbeddedNativeActionBridge(
                      deps, grant, capability, runtime, metadata_provider, clock=clock))
        def context():
            return runtime.r4_native_action_context(grant.r4_scope,
                connection_id=grant.r4_connection_id, connection_generation=grant.connection_generation)
        return PiNativeActionOwner(bridge, context, capability_ref=grant.capability_ref,
                                   session_id=grant.session_id)
    return build

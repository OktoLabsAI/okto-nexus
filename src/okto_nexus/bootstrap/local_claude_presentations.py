"""Publish a read-only local attachment for the exact managed Claude terminal."""

from dataclasses import asdict

from nexus_connector_core import CoreError

from ..adapters.inbound.http.dashboard_session_presentations import LocalClaudePresentations
from ..application.session_attachment_broker import SessionAttachmentBroker
from ..domain.attention import digest
from ..domain.presentation_protocol import LOCAL_CLAUDE_AUDIENCE
from ..errors import OktoNexusError


def publish_local_claude_presentations(app, dispatch):
    state = app.state
    if dispatch is None or not state.deps.config.runtime_session_interaction_enabled:
        state.local_claude_presentations = None
        return

    def available(mapping, scope):
        session = scope.session
        return mapping.adapter_id == 'claude_stream' and dispatch.host.has_owned_claude_terminal(
            session.server_id, session.executor_id, session.session_id)

    def revision(uow, scope, author, access, audience):
        if author.surface != 'native_terminal' or access != 'read' or audience != LOCAL_CLAUDE_AUDIENCE:
            return None
        try:
            mapping = dispatch.read_native_presentation_mapping(uow, scope)
        except (CoreError, OktoNexusError):
            return None
        if not available(mapping, scope):
            return None
        return 'sha256:' + digest({'mapping': asdict(mapping), 'audience': audience})

    async def prove(scope):
        mapping, proof = await dispatch.prove_native_presentation_owner(scope)
        if not available(mapping, scope):
            raise CoreError('CAPABILITY_UNSUPPORTED', 'claude_terminal_read')
        return mapping, proof

    state.local_claude_presentations = LocalClaudePresentations(
        SessionAttachmentBroker(state.deps.connection_factory, authority_fence=state.operator_auth.authority_fence,
                                current_capability=revision),
        prove, dispatch.open_native_claude_terminal)

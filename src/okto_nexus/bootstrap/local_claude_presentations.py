"""Publish the exact managed Claude terminal and its canonical input capability."""

from dataclasses import asdict

from nexus_connector_core import CoreError

from ..adapters.inbound.http.dashboard_session_presentations import LocalClaudePresentations
from ..application.execution_native_session_mapping import reviewed_claude_terminal_context
from ..application.session_attachment_broker import SessionAttachmentBroker
from ..domain.attention import digest
from ..domain.presentation_protocol import LOCAL_CLAUDE_AUDIENCE
from ..errors import OktoNexusError
from .execution_authority import build_execution_access


def publish_local_claude_presentations(app, dispatch):
    state = app.state
    if dispatch is None or not state.deps.config.runtime_session_interaction_enabled:
        state.local_claude_presentations = None
        return
    next_turn_revision = getattr(state, 'session_input_dispatch_options', {}).get('session_input_capability_revision')

    def available(mapping, scope):
        session = scope.session
        return mapping.adapter_id == 'claude_stream' and dispatch.host.has_owned_claude_terminal(
            session.server_id, session.executor_id, session.session_id)

    def revision(uow, scope, author, access, audience):
        if author.surface != 'native_terminal' or audience != LOCAL_CLAUDE_AUDIENCE:
            return None
        try:
            mapping = dispatch.read_native_presentation_mapping(uow, scope)
        except (CoreError, OktoNexusError):
            return None
        if not available(mapping, scope):
            return None
        context = {'mapping': asdict(mapping), 'audience': audience}
        if access == 'write':
            if not reviewed_claude_terminal_context(mapping) or next_turn_revision is None:
                return None
            if (input_revision := next_turn_revision(uow, scope)) is None:
                return None
            context.update(access=access, next_turn_revision=input_revision)
        return 'sha256:' + digest(context)

    async def prove(scope):
        mapping, proof = await dispatch.prove_native_presentation_owner(scope)
        if not available(mapping, scope):
            raise CoreError('CAPABILITY_UNSUPPORTED', 'claude_terminal_read')
        return mapping, proof

    state.local_claude_presentations = LocalClaudePresentations(
        SessionAttachmentBroker(state.deps.connection_factory, authority_fence=state.operator_auth.authority_fence,
                                current_capability=revision),
        prove, dispatch.open_native_claude_terminal,
        build_execution_access(state.deps) if next_turn_revision is not None else None, next_turn_revision)

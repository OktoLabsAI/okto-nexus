"""Publish the local operator presentation for reviewed hosted Pi sessions."""

from dataclasses import asdict

from nexus_connector_core import CoreError

from ..adapters.inbound.http.dashboard_session_presentations import LocalPiPresentations
from ..application.execution_native_session_mapping import reviewed_pi_presentation_context
from ..application.session_attachment_broker import SessionAttachmentBroker
from ..domain.attention import digest
from ..domain.presentation_protocol import LOCAL_PI_AUDIENCE
from ..errors import OktoNexusError
from .execution_authority import build_execution_access


def publish_local_pi_presentations(app, dispatch):
    state = app.state
    if dispatch is None or not dispatch.host.pi_presentation_enabled:
        state.local_pi_presentations = None
        return
    next_turn_revision = getattr(state, 'session_input_dispatch_options', {}).get('session_input_capability_revision')

    def available(mapping, scope):
        session = scope.session
        return reviewed_pi_presentation_context(mapping) and dispatch.host.has_hosted_pi_renderer(
            session.server_id, session.executor_id, session.session_id)

    def revision(uow, scope, author, access, audience):
        if author.surface != 'native_terminal' or audience != LOCAL_PI_AUDIENCE:
            return None
        try:
            mapping = dispatch.read_native_presentation_mapping(uow, scope)
        except (CoreError, OktoNexusError):
            return None
        if not available(mapping, scope):
            return None
        context = {'mapping': asdict(mapping), 'audience': audience, 'access': access}
        if access == 'write':
            if next_turn_revision is None or (input_revision := next_turn_revision(uow, scope)) is None:
                return None
            context['next_turn_revision'] = input_revision
        return 'sha256:' + digest(context)

    async def prove(scope):
        mapping, proof = await dispatch.prove_native_presentation_owner(scope)
        if not available(mapping, scope):
            raise CoreError('CAPABILITY_UNSUPPORTED', 'pi_renderer')
        return mapping, proof

    state.local_pi_presentations = LocalPiPresentations(
        SessionAttachmentBroker(state.deps.connection_factory, authority_fence=state.operator_auth.authority_fence,
                                current_capability=revision),
        prove, dispatch.open_native_pi_renderer,
        build_execution_access(state.deps) if next_turn_revision is not None else None, next_turn_revision,
        open_editor=getattr(dispatch, 'open_native_pi_editor', None))

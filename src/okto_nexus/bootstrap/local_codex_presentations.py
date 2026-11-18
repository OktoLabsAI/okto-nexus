"""Expose the qualified local reader through the current embedded owner."""

from dataclasses import asdict

from nexus_connector_core import CoreError

from ..adapters.inbound.http.dashboard_session_presentations import (
    LocalCodexPresentations,
)
from ..application.session_attachment_broker import SessionAttachmentBroker
from ..domain.attention import digest
from ..domain.presentation_protocol import (
    CODEX_VIEWER_WINDOWS_SHA256,
    LOCAL_CODEX_AUDIENCE,
)
from ..errors import OktoNexusError
from .execution_authority import build_execution_access

# Read-only pair exercised without inference on Windows. Core's conversation
# and control qualifications stay independent.
_ENGINE = ('0.157.0', 'win32', 'x86_64',
           'sha256:ed1c7b36e44536809c868864c833af8a857f56599a7a7fe23b908a1ba1093b1f')


def _reviewed_mapping(mapping):
    build = mapping.launch_build
    return (mapping.adapter_id == 'codex_app_server' and mapping.codex_thread_id is not None
            and build is not None and build.qualification == 'qualified'
            and (build.version, build.platform, build.architecture, build.content_fingerprint) == _ENGINE)


def publish_local_codex_presentations(app, dispatch):
    state = app.state
    deps = state.deps
    if dispatch is None or not deps.config.runtime_session_interaction_enabled:
        state.local_codex_presentations = None
        return

    def revision(uow, scope, author, access, audience):
        if access != 'read' or author.surface != 'native_terminal' or audience != LOCAL_CODEX_AUDIENCE:
            return None
        try:
            mapping = dispatch.read_native_presentation_mapping(uow, scope)
        except (CoreError, OktoNexusError):
            return None
        if not _reviewed_mapping(mapping):
            return None
        return 'sha256:' + digest({'mapping': asdict(mapping), 'viewer': CODEX_VIEWER_WINDOWS_SHA256,
                                   'audience': audience, 'access': access})

    async def prove(scope):
        mapping, proof = await dispatch.prove_native_presentation_owner(scope)
        if not _reviewed_mapping(mapping):
            raise CoreError('CAPABILITY_UNSUPPORTED', 'native_presentation')
        return mapping, proof

    async def read(scope):
        context = await dispatch.read_native_presentation_context(scope)
        return context if context is not None and context.status == 'idle' else None

    broker = SessionAttachmentBroker(deps.connection_factory,
        authority_fence=state.operator_auth.authority_fence, current_capability=revision)
    state.local_codex_presentations = LocalCodexPresentations(
        broker, prove, build_execution_access(deps), read_context=read)

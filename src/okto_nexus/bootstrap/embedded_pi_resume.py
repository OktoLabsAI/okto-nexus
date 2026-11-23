"""Carry one exact retired Pi branch into its admitted local successor."""

import asyncio
from functools import partial
from pathlib import Path

from nexus_connector_core import CoreError
from nexus_connector_core.native.pi_saved_history import PiSavedResumeGrant, pi_saved_history_current

from ..application.execution_saved_resume import pi_history_evidence, saved_opening_profile
from .embedded_codex_resume import read_retired_source


class SavedPiOpening:
    callback_key = 'pi_saved_resume'
    target_key = 'resume_pi_session_id'

    def __init__(self, owner, frame, lineage):
        self.owner, self.frame, self.lineage = owner, dict(frame), lineage
        self.witness = read_retired_source(owner, self.frame, lineage)
        self.history = pi_history_evidence(self.witness['history'])
        self.target = self.history.session_id
        self.local_launch = None

    def _require_current(self, prepared):
        if self.local_launch is None:
            raise CoreError('BINDING_NOT_AUTHORIZED', 'saved_pi_resume', retry_safe=True)
        self.local_launch.check()
        expected = self.witness['opening_profile']
        present = saved_opening_profile(prepared)
        if (read_retired_source(self.owner, self.frame, self.lineage) != self.witness
                or Path(prepared.cwd) != Path(self.history.workspace)
                or any(present.get(key) != expected.get(key) for key in (
                    'root_fingerprint', 'resume_configuration_sha256'))):
            raise CoreError('PROFILE_DRIFT', 'saved_pi_resume', retry_safe=True)

    async def grant(self, prepared, session_id, context, environment):
        fields = ('server_id', 'executor_id', 'binding_id', 'agent_id', 'workspace_id',
                  'session_owner_generation', 'authorization_revision', 'configuration_revision')
        if session_id != self.frame['session_id'] or any(
                getattr(context, field) != self.frame[field] for field in fields):
            raise CoreError('STALE_GENERATION', 'saved_pi_resume', retry_safe=True)
        home = environment.get('PI_CODING_AGENT_DIR')
        if (not home or Path(home) != Path(self.history.agent_dir)
                or not await asyncio.to_thread(pi_saved_history_current, self.history)):
            raise CoreError('PROFILE_DRIFT', 'saved_pi_resume', retry_safe=True)
        await asyncio.to_thread(self._require_current, prepared)
        return PiSavedResumeGrant(self.history, session_id, *(getattr(context, field) for field in fields),
            prepared.profile_fingerprint, prepared.root_fingerprint, partial(self._require_current, prepared))

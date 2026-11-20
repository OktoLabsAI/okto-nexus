"""Bind a retired Claude source to the approved local successor."""

import asyncio
from functools import partial
from pathlib import Path

from nexus_connector_core import ClaudeTerminalResumeGrant, CoreError
from nexus_connector_core.native.claude_saved_history import ClaudeSavedHistory, observe_claude_saved_history

from nexus_connector_core.native.claude_terminal_profile import observe_claude_resume_profile
from ..application.execution_saved_resume import saved_opening_profile
from .embedded_codex_resume import read_retired_source


def _refuse(code='PROFILE_DRIFT'):
    return CoreError(code, 'saved_claude_resume', retry_safe=True)


class SavedClaudeOpening:
    callback_key = 'claude_resume'
    target_key = 'resume_claude_session_id'

    def __init__(self, owner, frame, lineage):
        self.owner, self.frame, self.lineage = owner, dict(frame), lineage
        self.witness = read_retired_source(owner, self.frame, lineage)
        data = self.witness['history']
        self.history = ClaudeSavedHistory(**(data | {
            key: tuple(data[key]) for key in ('home_identity', 'workspace_identity', 'file_identity')
        }))
        self.target = self.history.session_uuid
        self.profile = self.witness['opening_profile']['claude_resume_profile']
        self.local_launch = None

    def _require_current(self, prepared):
        if self.local_launch is None:
            raise _refuse('BINDING_NOT_AUTHORIZED')
        self.local_launch.check()
        if read_retired_source(self.owner, self.frame, self.lineage, ready=True) != self.witness:
            raise _refuse()
        expected = self.witness['opening_profile']
        present = saved_opening_profile(prepared)
        if (Path(prepared.cwd) != Path(self.history.workspace)
                or self.profile['state_home'] != self.history.state_home
                or any(present.get(key) != expected.get(key) for key in (
                    'root_fingerprint', 'resume_configuration_sha256'))
                or observe_claude_resume_profile(self.history.state_home, self.history.workspace) != self.profile):
            raise _refuse()

    async def grant(self, prepared, session_id, context):
        expected = self.frame
        fields = ('server_id', 'executor_id', 'binding_id', 'agent_id', 'workspace_id', 'session_owner_generation',
                  'authorization_revision', 'configuration_revision')
        if session_id != expected['session_id'] or any(getattr(context, key) != expected[key] for key in fields):
            raise _refuse('STALE_GENERATION')
        await asyncio.to_thread(self._require_current, prepared)
        current = await asyncio.to_thread(observe_claude_saved_history, self.history.state_home,
                                          self.target, self.history.workspace)
        if current != self.history:
            raise _refuse()
        return ClaudeTerminalResumeGrant(self.history, session_id, *(getattr(context, key) for key in fields),
            prepared.profile_fingerprint, prepared.root_fingerprint, partial(self._require_current, prepared),
            question_only=self.profile.get('question_only') is True,
            read_approval=self.profile.get('read_approval') is True)

    async def environment(self, resolve, local_launch, prepared):
        value = await resolve(prepared)
        if local_launch is None or local_launch.claude_resume_profile != self.profile:
            raise _refuse()
        await asyncio.to_thread(self._require_current, prepared)
        return value

import json
from dataclasses import asdict
from types import SimpleNamespace
from uuid import uuid4

import pytest

from nexus_connector_core import CoreError, ExecutionContext, LaunchIntent
from nexus_connector_core.harness_configuration import validate_harness_settings
from nexus_connector_core.native.claude_saved_history import (
    claude_history_path,
    observe_claude_saved_history,
)
from okto_nexus.application import execution_claude_resume_profile as config
from okto_nexus.application.execution_saved_resume import saved_opening_profile
from okto_nexus.bootstrap import embedded_claude_resume


@pytest.fixture
def saved(tmp_path, monkeypatch):
    monkeypatch.setattr(config, '_has_external_policy', lambda: False)
    monkeypatch.setattr(config, '_has_parent_instructions', lambda _workspace: False)
    home, workspace = tmp_path / 'profile', tmp_path / 'workspace'
    home.mkdir()
    workspace.mkdir()
    settings = home / 'settings.json'
    settings.write_text('{"permissions":{"deny":["*"]}}', encoding='utf-8')
    intent = LaunchIntent('agent', 'workspace', 'claude_stream',
        harness_settings=validate_harness_settings('claude_stream', {'permission_mode': 'plan'}))
    prepared = SimpleNamespace(intent=intent, argv=('claude.exe',), cwd=str(workspace), secret_refs=(),
                              profile_fingerprint='profile', root_fingerprint='root')
    environment = {'CLAUDE_CONFIG_DIR': str(home), 'ANTHROPIC_AUTH_TOKEN': 'fixture'}
    profile = config.capture_claude_resume_profile(prepared, environment)
    assert profile is not None
    transcript = claude_history_path(str(home), str(uuid4()), str(workspace))
    transcript.parent.mkdir(parents=True)
    transcript.write_text(''.join(json.dumps({'type': kind, 'isSidechain': False,
        'sessionId': transcript.stem, 'cwd': str(workspace)}) + '\n' for kind in ('user', 'assistant')),
        encoding='utf-8')
    history = observe_claude_saved_history(str(home), transcript.stem, str(workspace))
    return SimpleNamespace(prepared=prepared, home=home, transcript=transcript, settings=settings,
                           history=history, profile=profile, environment=environment)


def test_saved_profile_rejects_drift_and_unreviewed_sources(saved):
    assert config.capture_claude_resume_profile(saved.prepared, saved.environment) == saved.profile
    saved.settings.write_text('{"permissions":{"deny":["*"]},"model":"different"}', encoding='utf-8')
    assert config.capture_claude_resume_profile(saved.prepared, saved.environment) != saved.profile
    saved.settings.write_text('{"permissions":{"deny":["*"]},"disableAllHooks":true}', encoding='utf-8')
    assert config.capture_claude_resume_profile(saved.prepared, saved.environment) is None


@pytest.mark.asyncio
async def test_saved_grant_revalidates_exact_retired_history_and_current_profile(saved, monkeypatch):
    witness = {'history': asdict(saved.history), 'opening_profile': {
        **saved_opening_profile(saved.prepared), 'claude_resume_profile': saved.profile,
    }}
    states = []

    def read_source(_owner, _frame, _lineage, *, ready=False):
        states.append(ready)
        return witness

    monkeypatch.setattr(embedded_claude_resume, 'read_retired_source', read_source)
    context = ExecutionContext('server', 'executor', 'binding', 'agent', 'workspace', 1, 1, 1, 100,
                               frozenset({'runtime.open'}))
    frame = {'session_id': 'successor', **{name: getattr(context, name) for name in (
        'server_id', 'executor_id', 'binding_id', 'agent_id', 'workspace_id', 'session_owner_generation',
        'authorization_revision', 'configuration_revision')}}
    opening = embedded_claude_resume.SavedClaudeOpening(object(), frame, {'source': 'retired'})
    opening.local_launch = SimpleNamespace(check=lambda: None, claude_resume_profile=saved.profile)
    with pytest.raises(CoreError, match='STALE_GENERATION'):
        await opening.grant(saved.prepared, 'wrong-successor', context)
    grant = await opening.grant(saved.prepared, 'successor', context)
    assert grant.history == saved.history and grant.session_id == 'successor'
    grant.require_current()
    assert states == [False, True, True]
    saved.settings.write_text('{"permissions":{"deny":["*"]},"model":"different"}', encoding='utf-8')
    with pytest.raises(CoreError, match='PROFILE_DRIFT'):
        grant.require_current()
    saved.settings.write_text('{"permissions":{"deny":["*"]}}', encoding='utf-8')
    saved.transcript.write_bytes(b'changed')
    with pytest.raises(CoreError, match='PROFILE_DRIFT'):
        await opening.grant(saved.prepared, 'successor', context)

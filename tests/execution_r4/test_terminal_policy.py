"""Reviewed default policy activation shares canonical Finish and its receipt."""
from copy import deepcopy
import json
import time

import pytest
from nexus_connector_core import RuntimeEvent

from okto_nexus.application.settings import SettingsService
from okto_nexus.application.terminal_connection import ConnectionError, document_revision
from okto_nexus.application.terminal_work import TerminalWork
from test_connection_setup_recovery import snapshot
import test_terminal_connect as terminal_fixtures
from test_vertical_inventory import _NativeFactory

terminal = terminal_fixtures.terminal
checking = terminal_fixtures.checking
local_setup = terminal_fixtures.local_setup

def stored(t):
    with t.deps.connection_factory.unit_of_work(write=False) as uow:
        row = uow.connection.execute("SELECT * FROM settings WHERE key='feature_hitl'").fetchone()
        return dict(row) if row is not None else None


def test_reviewed_default_activation_allows_native_decision_without_manual_setting(terminal, local_setup):
    t = terminal
    assert t.deps.config.feature_hitl is False and stored(t) is None
    document = t.flow.review(t.selection)
    assert document['request']['native_decision_policy']['initialize'] is True
    assert any('Server-wide' in effect for effect in document['effects'])
    assert t.deps.config.feature_hitl is False and stored(t) is None
    original_run = t.app.state.connection_tests.run
    async def inspect_draft(*args):
        assert t.deps.config.feature_hitl is False and stored(t) is None
        await original_run(*args)
    t.app.state.connection_tests.run = inspect_draft
    t.flow.apply(document, approval=document['review_revision'])
    assert t.deps.config.feature_hitl is True and json.loads(stored(t)['value']) is True
    assert document['result']['native_decision_policy'] == {'enabled_at_commit': True, 'initialized': True}

    native = _NativeFactory()
    t.app.state.embedded_dispatch_owner.native_factory = native
    replies = []
    async def reply(request, decision, response):
        replies.append((decision, response))
    native.native.reply_native_approval = reply
    work = TerminalWork(t.call, lambda value: None, document)
    operation = work.submit('Request explicit permission before proceeding')
    deadline = time.monotonic() + 30
    while not native.native.sent:
        assert time.monotonic() < deadline, work.observe()
        time.sleep(.03)
    with t.deps.connection_factory.unit_of_work(write=False) as uow:
        stream = dict(uow.connection.execute('SELECT * FROM execution_local_streams').fetchone())
    request = dict(schema_version=1, request_id=9, request_hash='b' * 64,
        method='item/commandExecution/requestApproval',
        params={'threadId': 'native-thread', 'turnId': 'turn-from-native', 'itemId': 'item'})
    # The real Server/Core event path receives a synthetic native permission.
    # The TestClient portal used by the fixture owns this asynchronous queue.
    client = local_setup[2]
    client.portal.call(native.native.queue.put, RuntimeEvent(stream['server_id'], stream['executor_id'],
        stream['session_id'], stream['stream_epoch'], 0, 'approval_request', request['method'],
        {'native_approval': request, 'native_approval_display': dict(request)}, operation['submission_turn_operation_id']))
    while not (pending := work.observe()['requests']['items']):
        assert time.monotonic() < deadline
        time.sleep(.03)
    proposal = pending[0]['request_payload']['kwargs']
    work.decide(pending[0]['approval_id'], 'approve', reviewed_revision=document_revision(proposal))
    while not replies:
        assert time.monotonic() < deadline, work.observe()
        time.sleep(.03)
    assert replies == [('accept', None)]


@pytest.mark.parametrize('source', ['stored', 'cli/env', 'legacy-context'])
def test_explicit_disabled_policy_is_preserved_before_probes(terminal, source):
    t = terminal
    if source == 'stored':
        t.call('PATCH', '/api/v1/settings', {'feature_hitl': False})
    elif source == 'cli/env':
        t.app.state.settings_service = SettingsService(t.deps.config, t.deps.clock, frozenset({'feature_hitl'}))
    else:
        t.deps.config._legacy_settings_provenance = True
    before = stored(t), snapshot(t.deps)
    with pytest.raises(ConnectionError) as refused:
        t.flow.review(t.selection)
    assert refused.value.code == 'NATIVE_DECISIONS_DISABLED'
    assert (stored(t), snapshot(t.deps)) == before
    assert t.probes == t.turns == [] and t.deps.config.feature_hitl is False


@pytest.mark.parametrize('stage', ['setup:test', 'setup:finish'])
def test_concurrent_explicit_policy_prevents_stale_setup(terminal, stage):
    t = terminal
    document = t.flow.review(t.selection)
    original_call = t.flow.call
    def change_before_request(method, path, body=None):
        if method == 'POST' and path.endswith(stage):
            t.call('PATCH', '/api/v1/settings', {'feature_hitl': False})
        return original_call(method, path, body)
    t.flow.call = change_before_request
    with pytest.raises(ConnectionError, match='decision policy changed'):
        t.flow.apply(document, approval=document['review_revision'])
    assert json.loads(stored(t)['value']) is False and t.deps.config.feature_hitl is False
    assert not snapshot(t.deps)['execution_bindings']
    assert t.turns == [] if stage == 'setup:test' else len(t.turns) == 1


def test_policy_and_config_rollback_with_late_finish_failure(terminal):
    t = terminal
    document = t.flow.review(t.selection)
    before = snapshot(t.deps)
    with t.deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("CREATE TRIGGER fail_policy_receipt BEFORE INSERT ON connection_setup_commits "
                               "BEGIN SELECT RAISE(ABORT,'injected receipt failure'); END")
    with pytest.raises(Exception, match='injected receipt failure'):
        t.flow.apply(document, approval=document['review_revision'])
    assert stored(t) is None and t.deps.config.feature_hitl is False
    assert snapshot(t.deps) == before
    with t.deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute('DROP TRIGGER fail_policy_receipt')
    assert t.flow.apply(document)['state'] == 'configured'
    assert t.deps.config.feature_hitl is True and len(t.turns) == 1


def test_lost_finish_and_later_disable_never_reinitialize_policy(terminal):
    t = terminal
    document = t.flow.review(t.selection)
    t.fault.after = 'setup:finish'
    with pytest.raises(ConnectionError, match='Injected'):
        t.flow.apply(document, approval=document['review_revision'])
    first = stored(t)
    assert t.deps.config.feature_hitl is True
    resumed = t.flow.apply(deepcopy(t.saved[-1]))
    assert resumed['state'] == 'configured' and stored(t) == first
    t.call('PATCH', '/api/v1/settings', {'feature_hitl': False})
    disabled = stored(t)
    receipt = t.flow.api('POST', '/connections/setup:finish', document['request'])
    assert receipt['native_decision_policy']['initialized'] is True  # Historical receipt only.
    assert stored(t) == disabled and t.deps.config.feature_hitl is False
    current = t.flow.observe(t.saved[-1])['configuration']['native_decision_policy']
    assert current['value'] is False and current['can_initialize'] is False
    assert len(t.turns) == 1 and len(snapshot(t.deps)['runtime_execution_grants']) == 1


def test_existing_enabled_policy_is_reused_without_rewriting_it(terminal):
    t = terminal
    t.call('PATCH', '/api/v1/settings', {'feature_hitl': True})
    original = stored(t)
    document = t.flow.review(t.selection)
    assert document['request']['native_decision_policy']['initialize'] is False
    assert not any('Enable Server-wide' in effect for effect in document['effects'])
    t.flow.apply(document, approval=document['review_revision'])
    assert stored(t) == original and t.deps.config.feature_hitl is True
    assert document['result']['native_decision_policy']['initialized'] is False


@pytest.mark.parametrize('later_disable', [False, True])
def test_recovery_refreshes_committed_current_policy_after_cache_failure(terminal, monkeypatch, later_disable):
    from okto_nexus.errors import ErrorCode, OktoNexusError
    t = terminal
    document = t.flow.review(t.selection)
    service = t.app.state.settings_service
    original = service.refresh_native_decisions
    def unavailable(factory):
        raise OktoNexusError(ErrorCode.DB_ERROR, 'Injected cache refresh failure', {})
    monkeypatch.setattr(service, 'refresh_native_decisions', unavailable)
    with pytest.raises(ConnectionError, match='Setup is committed') as pending:
        t.flow.apply(document, approval=document['review_revision'])
    assert pending.value.possible_effect
    assert t.deps.config.feature_hitl is False and json.loads(stored(t)['value']) is True
    before = snapshot(t.deps)
    monkeypatch.setattr(service, 'refresh_native_decisions', original)
    if later_disable:
        t.call('PATCH', '/api/v1/settings', {'feature_hitl': False})
    recorded = stored(t)
    assert t.flow.apply(deepcopy(t.saved[-1]))['state'] == 'configured'
    assert t.deps.config.feature_hitl is (not later_disable)
    assert stored(t) == recorded and snapshot(t.deps) == before
    assert len(t.turns) == 1 and len(before['runtime_execution_grants']) == 1


@pytest.mark.parametrize('action', ['test', 'finish'])
def test_participant_cannot_initialize_server_policy(terminal, local_setup, action):
    t = terminal
    document = t.flow.review(t.selection)
    before = stored(t), snapshot(t.deps)
    response = local_setup[2].post('/v1/connections/setup:' + action,
        headers=local_setup[3]['subject'], json=document['request'])
    assert response.status_code == 403, response.text
    assert (stored(t), snapshot(t.deps)) == before and t.deps.config.feature_hitl is False
    assert t.turns == []

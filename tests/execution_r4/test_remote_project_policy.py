"""Remote preset authorization, atomic Finish and current-policy recovery."""
import json

import pytest

from okto_nexus.application.project_preset import ORIGIN
import test_binding_operator as fixtures
from test_binding_operator import prepare_delegated, decide_binding, connection_preferences, assert_no_binding
from test_remote_machine_policy import second_machine

onboarding = fixtures.onboarding


def stored(deps):
    with deps.connection_factory.unit_of_work(write=False) as uow:
        row = uow.connection.execute("SELECT * FROM settings WHERE key='feature_hitl'").fetchone()
        return dict(row) if row else None


def pending(onboarding):
    deps, client, headers, prepare = onboarding
    prepare.update(connection_configuration=connection_preferences(prepare), project_preset=dict(ORIGIN))
    return prepare_delegated(client, headers, prepare)


def apply(client, headers, request):
    return client.post('/v1/connections/bindings:apply', headers=headers['subject'], json=request)


def patch_policy(client, headers, value):
    response = client.patch('/api/v1/settings', headers=headers['operator'], json={'feature_hitl': value})
    assert response.status_code == 200, response.text


def test_operator_review_precedes_atomic_preset_activation(onboarding, monkeypatch):
    deps, client, headers, _ = onboarding
    proposal, request, approval = pending(onboarding)
    assert 'Enable Server-wide human review' in proposal['diff']['summary']
    assert 'native_decision_policy' in proposal['diff']['fields_changed']
    assert stored(deps) is None and deps.config.feature_hitl is False
    assert apply(client, headers, request).status_code == 403
    assert decide_binding(client, headers, approval).status_code == 200
    assert stored(deps) is None and deps.config.feature_hitl is False
    assert_no_binding(deps)
    service = client.app.state.settings_service
    refresh = service.refresh_native_decisions
    def after_commit(factory):
        # A separate connection must see the real outer binding transaction.
        with factory.unit_of_work(write=False) as uow:
            assert uow.connection.execute('SELECT status FROM execution_proposals').fetchone()[0] == 'APPLIED'
            receipt = json.loads(uow.connection.execute('SELECT result_json FROM connection_setup_commits').fetchone()[0])
            assert receipt['project_preset'] == ORIGIN
            assert receipt['native_decision_policy']['initialized'] is True
        assert json.loads(stored(deps)['value']) is True and deps.config.feature_hitl is False
        refresh(factory)
    monkeypatch.setattr(service, 'refresh_native_decisions', after_commit)
    result = apply(client, headers, request)
    assert result.status_code == 200, result.text
    assert deps.config.feature_hitl is True
    current = client.get('/v1/connections/setup/subject', params={'binding_id': proposal['binding_id']}, headers=headers['operator'])
    assert current.status_code == 200, current.text
    assert current.json()['project_preset'] == ORIGIN


@pytest.mark.parametrize('source', ['stored', 'pinned', 'legacy'])
def test_explicit_false_cannot_be_replaced_by_participant_preset(onboarding, source):
    deps, client, headers, prepare = onboarding
    if source == 'stored':
        patch_policy(client, headers, False)
    elif source == 'pinned':
        client.app.state.settings_service._pinned = frozenset({'feature_hitl'})
    else:
        deps.config._legacy_settings_provenance = True
    before = stored(deps)
    prepare.update(connection_configuration=connection_preferences(prepare), project_preset=dict(ORIGIN))
    refused = client.post('/v1/connections/bindings:prepare', headers=headers['subject'], json=prepare)
    assert refused.status_code == 403, refused.text
    assert stored(deps) == before and deps.config.feature_hitl is False
    assert_no_binding(deps)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM approvals').fetchone()[0] == 0


@pytest.mark.parametrize('stage', ['decision', 'apply'])
def test_policy_drift_requires_new_review(onboarding, stage):
    deps, client, headers, _ = onboarding
    _, request, approval = pending(onboarding)
    if stage == 'apply':
        assert decide_binding(client, headers, approval).status_code == 200
    patch_policy(client, headers, False)
    refused = decide_binding(client, headers, approval) if stage == 'decision' else apply(client, headers, request)
    assert refused.status_code == 409, refused.text
    assert 'policy changed' in refused.text
    assert_no_binding(deps)
    assert deps.config.feature_hitl is False


def test_late_binding_failure_rolls_back_policy_and_receipt(onboarding):
    deps, client, headers, _ = onboarding
    _, request, approval = pending(onboarding)
    assert decide_binding(client, headers, approval).status_code == 200
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("CREATE TRIGGER fail_apply BEFORE UPDATE OF applied_json ON execution_proposals "
                               "BEGIN SELECT RAISE(ABORT,'injected late apply failure'); END")
    assert apply(client, headers, request).status_code == 500
    assert stored(deps) is None and deps.config.feature_hitl is False
    assert_no_binding(deps)
    with deps.connection_factory.unit_of_work() as uow:
        for table in ('connection_setup_commits', 'runtime_execution_grants'):
            assert uow.connection.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0] == 0
        uow.connection.execute('DROP TRIGGER fail_apply')
    assert apply(client, headers, request).status_code == 200


@pytest.mark.parametrize('later_disable', [False, True])
def test_committed_cache_failure_recovers_same_intent_without_regrant(onboarding, monkeypatch, later_disable):
    deps, client, headers, _ = onboarding
    _, request, approval = pending(onboarding)
    assert decide_binding(client, headers, approval).status_code == 200
    service = client.app.state.settings_service
    refresh = service.refresh_native_decisions
    def unavailable(factory):
        raise OSError('injected cache failure')
    monkeypatch.setattr(service, 'refresh_native_decisions', unavailable)
    uncertain = apply(client, headers, request)
    assert uncertain.status_code == 409, uncertain.text
    assert uncertain.json()['error']['code'] == 'OUTCOME_UNKNOWN'
    assert uncertain.json()['error']['possible_effect'] and uncertain.json()['error']['retry_safe']
    assert json.loads(stored(deps)['value']) is True and deps.config.feature_hitl is False
    monkeypatch.setattr(service, 'refresh_native_decisions', refresh)
    if later_disable:
        patch_policy(client, headers, False)
    before = stored(deps)
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE runtime_execution_grants SET revoked_at='2026-11-05T00:00:00Z'")
        grant = dict(uow.connection.execute('SELECT * FROM runtime_execution_grants').fetchone())
    replay = apply(client, headers, request)
    assert replay.status_code == 200, replay.text
    assert stored(deps) == before and deps.config.feature_hitl is (not later_disable)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert dict(uow.connection.execute('SELECT * FROM runtime_execution_grants').fetchone()) == grant
        for table in ('execution_bindings', 'runtime_execution_grants', 'connection_setup_commits'):
            assert uow.connection.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0] == 1


def test_enabled_policy_is_preserved(onboarding):
    deps, client, headers, _ = onboarding
    patch_policy(client, headers, True)
    before = stored(deps)
    proposal, request, approval = pending(onboarding)
    assert 'Preserve the enabled' in proposal['diff']['summary']
    assert decide_binding(client, headers, approval).status_code == 200
    assert apply(client, headers, request).status_code == 200
    assert stored(deps) == before


@pytest.mark.parametrize('preset', [{'id': 'project-generalist', 'revision': 2},
                                 {'id': 'project-generalist', 'revision': True},
                                 {'id': 'unknown', 'revision': 1}])
def test_unknown_preset_never_creates_approval(onboarding, preset):
    deps, client, headers, prepare = onboarding
    prepare.update(connection_configuration=connection_preferences(prepare), project_preset=preset)
    response = client.post('/v1/connections/bindings:prepare', headers=headers['subject'], json=prepare)
    assert response.status_code == 422, response.text
    assert stored(deps) is None
    assert_no_binding(deps)


def test_project_effect_requires_operator_even_under_automatic_machine_replacement(onboarding, tmp_path):
    deps, client, headers, prepare = onboarding
    prepare['connection_configuration'] = connection_preferences(prepare)
    _, request, approval = prepare_delegated(client, headers, prepare)
    assert decide_binding(client, headers, approval).status_code == 200
    assert apply(client, headers, request).status_code == 200
    assert stored(deps) is None and deps.config.feature_hitl is False  # Old client contract.
    other = second_machine(deps, client, headers, prepare, tmp_path)
    other['project_preset'] = dict(ORIGIN)
    deps.config.remote_machine_policy = 'auto_replace'
    proposal, request, approval = prepare_delegated(client, headers, other)
    request['client_intent_id'] = 'second-apply'
    assert 'Enable Server-wide human review' in proposal['diff']['summary']
    assert apply(client, headers, request).status_code == 403
    assert decide_binding(client, headers, approval).status_code == 200
    result = apply(client, headers, request)
    assert result.status_code == 200, result.text
    assert deps.config.feature_hitl is True

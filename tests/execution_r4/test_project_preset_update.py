"""Preset evolution uses canonical setup CAS, authority and durable receipts."""
from copy import deepcopy
import json
import sqlite3

import pytest

import test_connection_setup
from test_connection_setup_recovery import snapshot
from okto_nexus.application import project_preset
from okto_nexus.application.execution_local_realizations import directory_identity
from okto_nexus.application.project_preset_update import prepare_preset_update
from okto_nexus.errors import OktoNexusError

local_setup = test_connection_setup.local_setup


def existing(setup):
    context, request = test_connection_setup.request_for(setup)
    request['project_preset'] = deepcopy(project_preset.ORIGIN)
    verified = dict(root=directory_identity(request['configuration']['workspace_root']), home=None)
    result = test_connection_setup.finish(setup, context, request, verified=verified)
    return context, request, result, verified


def revision_two(monkeypatch):
    defaults = project_preset.configuration_defaults()
    defaults['session_policy'] = 'per_sender_session'
    defaults['authorization']['actions'] = 30
    monkeypatch.setattr(project_preset, 'ORIGIN', dict(id='project-generalist', revision=2))
    monkeypatch.setattr(project_preset, 'configuration_defaults', lambda: deepcopy(defaults))


def test_current_revision_is_read_only_on_both_http_adapters_and_refuses_participant(local_setup):
    t = local_setup
    _, _, result, _ = existing(t)
    before = snapshot(t[0])
    suffix = '/connections/setup/subject/preset-update?binding_id=' + result['binding']['binding_id']
    for prefix in ('/v1', '/api/v1/runtime-management'):
        response = t[2].get(prefix + suffix, headers=t[3]['operator'])
        assert response.status_code == 200, response.text
        assert response.json()['state'] == 'up_to_date'
        assert response.json()['changes'] == []
        assert t[2].get(prefix + suffix, headers=t[3]['subject']).status_code == 403
    assert snapshot(t[0]) == before


def test_review_advances_only_unchanged_defaults_and_finish_recovers_once(local_setup, monkeypatch):
    t = local_setup
    context, original, result, verified = existing(t)
    with t[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agents SET role='Personalized reviewer' WHERE agent_id='subject'")
    revision_two(monkeypatch)
    before = snapshot(t[0])
    review = prepare_preset_update(t[0], context, 'subject', result['binding']['binding_id'])
    assert snapshot(t[0]) == before
    assert {item['field'] for item in review['changes']} == {'session_policy', 'authorization.actions'}
    assert review['preserved'] == [dict(field='tool_access', current='always_allow', recommendation='ask')]
    request = review['request'] | {'client_intent_id': 'preset-update-one'}
    updated = test_connection_setup.finish(t, context, request, verified=verified)
    assert updated['binding']['binding_id'] == result['binding']['binding_id']
    assert updated['project_preset']['revision'] == 2
    assert test_connection_setup.count(t, 'runtime_execution_grants') == 2
    with t[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT role FROM agents WHERE agent_id='subject'").fetchone()[0] == 'Personalized reviewer'
    after = snapshot(t[0])
    assert test_connection_setup.finish(t, context, request, verified=None) == updated
    assert snapshot(t[0]) == after
    # Upgrade does not prevent recovery of an older committed request.
    recovered = t[2].post('/api/v1/runtime-management/connections/setup:recover',
        headers=t[3]['operator'], json=original)
    assert recovered.status_code == 200, recovered.text
    assert recovered.json()['result']['project_preset']['revision'] == 1
    repeated_finish = t[2].post('/api/v1/runtime-management/connections/setup:finish',
        headers=t[3]['operator'], json=original)
    assert repeated_finish.status_code == 200, repeated_finish.text
    assert repeated_finish.json()['project_preset']['revision'] == 1
    assert snapshot(t[0]) == after


@pytest.mark.parametrize('change', ['identity', 'grant', 'configuration', 'preset'])
def test_concurrent_change_refuses_finish_without_repair_or_authority(local_setup, monkeypatch, change):
    t = local_setup
    context, _, result, verified = existing(t)
    revision_two(monkeypatch)
    review = prepare_preset_update(t[0], context, 'subject', result['binding']['binding_id'])
    request = review['request'] | {'client_intent_id': 'stale-preset-update'}
    if change == 'preset':
        monkeypatch.setattr(project_preset, 'ORIGIN', dict(id='project-generalist', revision=3))
    else:
        with t[0].connection_factory.unit_of_work() as uow:
            if change == 'identity':
                uow.connection.execute("UPDATE agents SET role='Concurrent choice' WHERE agent_id='subject'")
            elif change == 'grant':
                uow.connection.execute('UPDATE runtime_execution_grants SET revoked_at=?', (t[0].clock.now_iso(),))
            else:
                uow.connection.execute("UPDATE agent_endpoints SET revision=revision+1 WHERE agent_id='subject'")
    before = snapshot(t[0])
    with pytest.raises(OktoNexusError) as refused:
        test_connection_setup.finish(t, context, request, verified=verified)
    assert refused.value.code == 'CONFLICT'
    assert snapshot(t[0]) == before
    assert test_connection_setup.count(t, 'connection_setup_commits') == 1


def test_disabled_runtime_stays_disabled_without_test_or_grant(local_setup, monkeypatch):
    from okto_nexus.application import runtime_policy
    t = local_setup
    context, _, result, _ = existing(t)
    policy = runtime_policy.read_policy(t[0], context, 'subject')
    runtime_policy.save_policy(t[0], context, agent_id='subject', changes=dict(
        expected_revision=policy['revision'], runtime_enabled=False, session_policy='per_sender'))
    revision_two(monkeypatch)
    review = prepare_preset_update(t[0], context, 'subject', result['binding']['binding_id'])
    assert review['request']['configuration']['runtime_enabled'] is False
    assert review['local_test_required'] is False
    response = t[2].post('/api/v1/runtime-management/connections/setup:finish',
        headers=t[3]['operator'], json=review['request'] | {'client_intent_id': 'disabled-preset-update'})
    assert response.status_code == 200, response.text
    assert response.json()['binding']['binding_id'] == result['binding']['binding_id']
    assert runtime_policy.read_policy(t[0], context, 'subject')['runtime_enabled'] is False
    assert test_connection_setup.count(t, 'runtime_execution_grants') == 1
    assert t[1].state.connection_tests.tests == {}


def test_legacy_origin_uses_immutable_base_and_late_failure_rolls_back_update(local_setup, monkeypatch):
    t = local_setup
    context, _, result, verified = existing(t)
    with t[0].connection_factory.unit_of_work() as uow:
        old_result = deepcopy(result)
        old_result.pop('project_preset_defaults')
        uow.connection.execute('UPDATE connection_setup_commits SET result_json=?', (json.dumps(old_result),))
    revision_two(monkeypatch)
    review = prepare_preset_update(t[0], context, 'subject', result['binding']['binding_id'])
    assert {row['field'] for row in review['changes']} == {'session_policy', 'authorization.actions'}
    request = review['request'] | {'client_intent_id': 'rollback-preset-update'}
    with t[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute("CREATE TRIGGER reject_preset_receipt BEFORE INSERT ON connection_setup_commits "
                               "BEGIN SELECT RAISE(ABORT,'injected late receipt failure'); END")
    before = snapshot(t[0])
    with pytest.raises(sqlite3.IntegrityError):
        test_connection_setup.finish(t, context, request, verified=verified)
    assert snapshot(t[0]) == before
    with t[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute('DROP TRIGGER reject_preset_receipt')
    updated = test_connection_setup.finish(t, context, request, verified=verified)
    assert updated['project_preset_defaults']['authorization']['actions'] == 30


@pytest.mark.parametrize('tamper', ['path', 'claim_policy', 'mcp'])
def test_server_rejects_unreviewed_effects_before_starting_test(local_setup, monkeypatch, tamper):
    t = local_setup
    context, _, result, _ = existing(t)
    revision_two(monkeypatch)
    review = prepare_preset_update(t[0], context, 'subject', result['binding']['binding_id'])
    request = review['request'] | {'client_intent_id': 'tampered-preset-update'}
    if tamper == 'path':
        request['configuration']['workspace_root'] += '/different-project'
    elif tamper == 'claim_policy':
        request['broadcast_handoff_auto_claim'] = True
    else:
        request['mcp_preset'] = dict(expected_revision=0, servers=[])
    before = snapshot(t[0])
    response = t[2].post('/api/v1/runtime-management/connections/setup:test',
        headers=t[3]['operator'], json=request)
    assert response.status_code == 409, response.text
    assert t[1].state.connection_tests.tests == {} and snapshot(t[0]) == before


def test_review_lists_all_canonical_revocations_and_guards_other_connection_authority(local_setup, monkeypatch):
    from okto_nexus.application.connection_setup import load_setup
    t = local_setup
    context, first, result, verified = existing(t)
    another_root = t[6].parent / 'second-project'
    another_root.mkdir()
    second = deepcopy(first)
    second.update(client_intent_id='second-project', baseline=load_setup(t[0], context, 'subject')['baseline'])
    second['configuration'].update(workspace_root=str(another_root), workspace_label='Second project', alias='second')
    other = test_connection_setup.finish(t, context, second,
        verified=dict(root=directory_identity(str(another_root)), home=None))
    with t[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute('INSERT INTO runtime_boot_bindings '
            '(endpoint_id,enabled,endpoint_revision,profile_revision,issuer_agent_id,revision,updated_at) '
            "SELECT endpoint_id,1,revision,NULL,'operator',1,? FROM agent_endpoints WHERE agent_id='subject'",
            (t[0].clock.now_iso(),))
        identity = tuple(uow.connection.execute("SELECT agent_id,role,metadata,permissions,api_key_hash FROM agents WHERE agent_id='subject'").fetchone())
    revision_two(monkeypatch)
    review = prepare_preset_update(t[0], context, 'subject', result['binding']['binding_id'])
    effects = review['authority_changes']
    assert {row['binding_id'] for row in effects['connections']} == {result['binding']['binding_id'], other['binding']['binding_id']}
    assert len(effects['revoked_grant_ids']) == len(effects['disabled_boot_endpoint_ids']) == 2
    with t[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute('UPDATE runtime_execution_grants SET revision=revision+1 WHERE endpoint_id=?',
            (other['binding']['endpoint_id'],))
    before = snapshot(t[0])
    with pytest.raises(OktoNexusError) as stale:
        test_connection_setup.finish(t, context, review['request'] | {'client_intent_id': 'stale-other-grant'}, verified=verified)
    assert stale.value.code == 'CONFLICT' and snapshot(t[0]) == before
    fresh = prepare_preset_update(t[0], context, 'subject', result['binding']['binding_id'])
    updated = test_connection_setup.finish(t, context, fresh['request'] | {'client_intent_id': 'reviewed-all-effects'}, verified=verified)
    assert updated['binding']['binding_id'] == result['binding']['binding_id']
    with t[0].connection_factory.unit_of_work(write=False) as uow:
        grants = [dict(row) for row in uow.connection.execute('SELECT * FROM runtime_execution_grants')]
        assert {row['grant_id'] for row in grants if row['revoked_at']} == set(fresh['authority_changes']['revoked_grant_ids'])
        active = [row for row in grants if row['revoked_at'] is None]
        assert len(active) == 1 and active[0]['endpoint_id'] == result['binding']['endpoint_id']
        assert not uow.connection.execute('SELECT 1 FROM runtime_boot_bindings WHERE enabled=1').fetchone()
        assert tuple(uow.connection.execute("SELECT agent_id,role,metadata,permissions,api_key_hash FROM agents WHERE agent_id='subject'").fetchone()) == identity

"""Approved runtime configuration remains isolated and operator controlled."""
import json
from pathlib import Path

import pytest
from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, connected_local, connect_local, qualified_contract, admit, wait_receipt
from test_embedded_tools import enable_tools
from test_runtime_contract_migration import mcp


@pytest.mark.parametrize('local_setup', ['codex_app_server', 'pi_rpc', 'claude_stream'], indirect=True)
@pytest.mark.parametrize('transport', ['rest', 'mcp'])
def test_public_open_uses_isolated_approved_profile(local_setup, monkeypatch, transport):
    home = local_setup[0].config.home_dir / 'approved-provider'
    home.mkdir()
    local_setup[4]['provider_home'] = str(home)
    setup, binding, native, vault, environments = enable_tools(connect_local(local_setup))
    deps, _, client, headers, *_, root = setup
    monkeypatch.setenv('UNAPPROVED_AMBIENT_TOKEN', 'ambient-fixture-secret')
    kind = {'codex_app_server': 'codex', 'pi_rpc': 'pi', 'claude_stream': 'claude_code'}[setup[5].adapter_id]
    body = dict(agent_id='subject', kind=kind, endpoint_id=binding['endpoint_id'],
                project_root=str(root), idempotency_key='isolated-profile-open')
    if transport == 'rest':
        response = client.post('/api/v1/harness/sessions', headers=headers['subject'], json=body)
        assert response.status_code == 200, response.text
        opened = response.json()
    else:
        opened = mcp(setup, monkeypatch, headers['subject']['Authorization'].removeprefix('Bearer '), 'harness_open', body)
    assert opened['ok'], opened
    wait_receipt(setup, opened['data'])
    assert native.opens == 1 and len(environments) == 1
    environment = environments[0]
    home = Path(environment['HOME']).resolve()
    assert home.is_relative_to(deps.config.home_dir.resolve())
    if kind in ('pi', 'codex'):
        state = Path(environment['CODEX_HOME' if kind == 'codex' else 'PI_CODING_AGENT_DIR']).resolve()
        assert state.is_relative_to(home)
    assert 'UNAPPROVED_AMBIENT_TOKEN' not in environment
    for role in ('operator', 'subject'):
        assert headers[role]['Authorization'].removeprefix('Bearer ') not in json.dumps(dict(environment))
    with deps.connection_factory.unit_of_work(write=False) as uow:
        profile = uow.connection.execute('SELECT p.* FROM runtime_profiles p JOIN agent_endpoints e '
            'ON e.profile_id=p.profile_id WHERE e.endpoint_id=?', (binding['endpoint_id'],)).fetchone()
        assert profile['inherit_ambient'] == 0
        assert opened['data']['scope']['configuration_revision'] >= 1
    wait_receipt(setup, admit(setup, binding, 'isolated-profile-close', 'runtime.close',
        session_id=opened['data']['scope']['session_id']), stages=('SUCCEEDED',))


def test_notification_configuration_requires_operator_and_rejects_open_overrides(connected_local, monkeypatch):
    setup, binding, native = connected_local
    _, _, client, headers, *_, root = setup
    path = '/api/v1/harness/endpoints/' + binding['endpoint_id']
    response = client.patch(path, headers=headers['subject'], json=dict(expected_revision=1,
        public_config=dict(notify_target=dict(strategy='broadcast'))))
    assert response.status_code == 403, response.text
    body = dict(agent_id='subject', kind='codex', project_root=str(root), endpoint_id=binding['endpoint_id'],
        idempotency_key='unauthorized-audience', notify_target=dict(strategy='broadcast'))
    denied = mcp(setup, monkeypatch, headers['subject']['Authorization'].removeprefix('Bearer '), 'harness_open', body)
    assert not denied['ok'] and denied['error']['code'] == 'VALIDATION_ERROR', denied
    assert native.opens == 0


@pytest.mark.parametrize('local_setup', ['codex_app_server', 'pi_rpc', 'claude_stream'], indirect=True)
def test_stale_endpoint_update_preserves_approved_notification_audience(connected_local):
    setup, binding, native = connected_local
    deps, _, client, headers, *_ = setup
    path = '/api/v1/harness/endpoints/' + binding['endpoint_id']
    with deps.connection_factory.unit_of_work(write=False) as uow:
        initial_revision = uow.connection.execute('SELECT revision FROM agent_endpoints WHERE endpoint_id=?',
            (binding['endpoint_id'],)).fetchone()[0]
    settings = client.put(path + '/harness-settings', headers=headers['operator'],
        json=dict(expected_revision=initial_revision, settings=dict(model='fixture-model')))
    assert settings.status_code == 200, settings.text
    with deps.connection_factory.unit_of_work(write=False) as uow:
        before = dict(uow.connection.execute('SELECT revision,public_config FROM agent_endpoints WHERE endpoint_id=?',
            (binding['endpoint_id'],)).fetchone())
        revision = before['revision']
    target = dict(strategy='direct', agent_id='operator')
    changed = client.patch(path, headers=headers['operator'], json=dict(expected_revision=revision,
        public_config=dict(notify_target=target)))
    assert changed.status_code == 200, changed.text
    stale = client.patch(path, headers=headers['operator'], json=dict(expected_revision=revision,
        public_config=dict(notify_target=dict(strategy='broadcast'))))
    assert stale.status_code == 409, stale.text
    with deps.connection_factory.unit_of_work(write=False) as uow:
        row = uow.connection.execute('SELECT revision,public_config FROM agent_endpoints WHERE endpoint_id=?',
            (binding['endpoint_id'],)).fetchone()
        assert row['revision'] == revision + 1 and json.loads(row['public_config'])['notify_target'] == target
        assert json.loads(row['public_config'])['alias'] == json.loads(before['public_config'])['alias']
        assert json.loads(row['public_config'])['harness_settings'] == json.loads(before['public_config'])['harness_settings']
    assert native.opens == 0


def test_endpoint_patch_cannot_replace_binding_identity(connected_local):
    setup, binding, native = connected_local
    deps, _, client, headers, *_ = setup
    with deps.connection_factory.unit_of_work(write=False) as uow:
        before = dict(uow.connection.execute('SELECT * FROM agent_endpoints WHERE endpoint_id=?',
            (binding['endpoint_id'],)).fetchone())
    changed = client.patch('/api/v1/harness/endpoints/' + binding['endpoint_id'], headers=headers['operator'],
        json=dict(expected_revision=before['revision'], public_config=dict(alias='unapproved-name')))
    assert changed.status_code == 422, changed.text
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert dict(uow.connection.execute('SELECT * FROM agent_endpoints WHERE endpoint_id=?',
            (binding['endpoint_id'],)).fetchone()) == before
    assert native.opens == 0


@pytest.mark.parametrize('local_setup', ['codex_app_server', 'pi_rpc', 'claude_stream'], indirect=True)
def test_profile_disable_retains_history_blocks_send_and_contains_native(connected_local, monkeypatch):
    setup, binding, native = connected_local
    deps, _, client, headers, *_ = setup
    # Exercise the existing renewal/containment deadline with a short real
    # lease; do not force renewal or invoke the recovery owner from the test.
    setup[1].state.embedded_dispatch_owner.leases.max_duration_ms = 3000
    opened = admit(setup, binding, 'profile-disable-open', 'runtime.start', new_session=True)
    wait_receipt(setup, opened)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        profile = dict(uow.connection.execute('SELECT p.* FROM runtime_profiles p JOIN agent_endpoints e '
            'ON e.profile_id=p.profile_id WHERE e.endpoint_id=?', (binding['endpoint_id'],)).fetchone())
    path = '/api/v1/harness/profiles/' + profile['profile_id']
    changed = client.patch(path, headers=headers['operator'], json=dict(expected_revision=profile['revision'], enabled=False))
    assert changed.status_code == 200, changed.text
    stale = client.patch(path, headers=headers['operator'], json=dict(expected_revision=profile['revision'], enabled=True))
    assert stale.status_code == 409, stale.text
    body = dict(session_id=opened['session_id'], idempotency_key='disabled-profile-send', payload=dict(text='must not execute'))
    denied = mcp(setup, monkeypatch, headers['subject']['Authorization'].removeprefix('Bearer '), 'harness_send', body)
    assert not denied['ok'] and denied['error']['code'] in ('PERMISSION_DENIED', 'CONFLICT'), denied
    assert native.native.sent == []
    from test_agent_recovery_isolation import eventually
    eventually(lambda: native.native.stopped)
    def closed():
        with deps.connection_factory.unit_of_work(write=False) as uow:
            return uow.connection.execute("SELECT 1 FROM execution_sessions WHERE session_id=? AND lifecycle_state='CLOSED'",
                                          (opened['session_id'],)).fetchone()
    eventually(closed)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT 1 FROM execution_sessions WHERE session_id=?', (opened['session_id'],)).fetchone()
        assert not uow.connection.execute('SELECT 1 FROM runtime_execution_grants WHERE endpoint_id=? AND revoked_at IS NULL',
                                         (binding['endpoint_id'],)).fetchone()


@pytest.mark.parametrize('surface', ['rest', 'mcp'])
@pytest.mark.parametrize('disable_profile', [False, True])
def test_operator_close_preserves_subject_identity_and_rejects_foreign_actor(connected_local, monkeypatch, surface, disable_profile):
    from test_agent_recovery_isolation import create_agent
    setup, binding, native = connected_local
    opened = admit(setup, binding, 'operator-compat-open', 'runtime.start', new_session=True)
    wait_receipt(setup, opened)
    foreign = create_agent(setup, 'foreign')[3]['subject']
    body = dict(idempotency_key='operator-compat-close')
    client = setup[2]
    if disable_profile:
        with setup[0].connection_factory.unit_of_work(write=False) as uow:
            profile = dict(uow.connection.execute('SELECT p.* FROM runtime_profiles p JOIN agent_endpoints e '
                'ON e.profile_id=p.profile_id WHERE e.endpoint_id=?', (binding['endpoint_id'],)).fetchone())
        disabled = client.patch('/api/v1/harness/profiles/' + profile['profile_id'],
            headers=setup[3]['operator'], json=dict(expected_revision=profile['revision'], enabled=False))
        assert disabled.status_code == 200, disabled.text
        for role in ('operator', 'subject'):
            denied_send = client.post('/api/v1/harness/sessions/' + opened['session_id'] + '/send',
                headers=setup[3][role], json=dict(idempotency_key='disabled-send-' + role, payload=dict(text='No write')))
            assert denied_send.status_code == 403, denied_send.text
        assert native.native.sent == []
        denied_close = client.post('/api/v1/harness/sessions/' + opened['session_id'] + '/close',
            headers=setup[3]['subject'], json=dict(idempotency_key='disabled-subject-close'))
        assert denied_close.status_code == 403, denied_close.text
    path = '/api/v1/harness/sessions/' + opened['session_id'] + '/close'
    denied = client.post(path, headers=foreign, json=body)
    assert denied.status_code == 403, denied.text
    assert not native.native.stopped
    if surface == 'rest':
        response = client.post(path, headers=setup[3]['operator'], json=body)
        with setup[0].connection_factory.unit_of_work(write=False) as uow:
            resolutions = [json.loads(r[0]) for r in uow.connection.execute('SELECT resolved_json FROM execution_client_intents')]
        assert response.status_code == 200, (response.text, [(r['semantic_intent']['action'], r['blockers']) for r in resolutions])
        closed = response.json()
    else:
        closed = mcp(setup, monkeypatch, setup[3]['operator']['Authorization'].removeprefix('Bearer '),
                     'harness_close', dict(session_id=opened['session_id'], **body))
    assert closed['ok'], closed
    wait_receipt(setup, closed['data'], stages=('SUCCEEDED',))
    assert native.native.stopped
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        row = uow.connection.execute('SELECT actor_agent_id,subject_agent_id FROM execution_operations WHERE operation_id=?',
                                     (closed['data']['operation_id'],)).fetchone()
        assert tuple(row) == ('operator', 'subject')
        if disable_profile:
            assert not uow.connection.execute("SELECT 1 FROM execution_leases WHERE status IN ('ISSUED','ACTIVE')").fetchone()
            assert not uow.connection.execute('SELECT 1 FROM runtime_execution_grants WHERE revoked_at IS NULL').fetchone()


def test_endpoint_reenable_requires_current_revision_and_new_grant(connected_local):
    from test_unbounded_local_grants import issue
    setup, binding, native = connected_local
    deps, _, client, headers, *_ = setup
    path = '/api/v1/harness/endpoints/' + binding['endpoint_id']
    with deps.connection_factory.unit_of_work(write=False) as uow:
        revision = uow.connection.execute('SELECT revision FROM agent_endpoints WHERE endpoint_id=?',
                                         (binding['endpoint_id'],)).fetchone()[0]
        old_grants = [r[0] for r in uow.connection.execute('SELECT grant_id FROM runtime_execution_grants')]
    for offset, enabled in enumerate((False, True)):
        response = client.patch(path, headers=headers['operator'], json=dict(expected_revision=revision + offset, enabled=enabled))
        assert response.status_code == 200, response.text
    stale = client.patch(path, headers=headers['operator'], json=dict(expected_revision=revision, enabled=False))
    assert stale.status_code == 409, stale.text
    from test_operator_runtime import resolve
    denied = resolve(setup, binding, identity='subject', intent_id='old-grant-open', new_session=True)
    if denied.status_code == 200:
        resolution = denied.json()
        rejected = client.post('/v1/runtime/operations', headers=headers['subject'], json={k: resolution[k] for k in
            ('client_intent_id', 'operation_id', 'resolution_revision', 'intent_hash')})
        assert rejected.status_code == 202, rejected.text
        from test_agent_recovery_isolation import eventually
        def refused():
            response = client.get('/v1/runtime/operations/' + resolution['operation_id'], headers=headers['subject'])
            assert response.status_code == 200, response.text
            return response.json() if response.json()['admission_state'] == 'RESOLVED_TERMINAL' else None
        eventually(refused)
        assert refused()['possible_effect'] is False and refused()['result'] is None
    else:
        assert denied.status_code == 403, denied.text
    assert native.opens == 0
    grant = issue(setup, binding)
    assert grant.status_code == 200, grant.text
    opened = admit(setup, binding, 'new-grant-open', 'runtime.start', new_session=True)
    wait_receipt(setup, opened)
    assert native.opens == 1
    with deps.connection_factory.unit_of_work(write=False) as uow:
        for grant_id in old_grants:
            assert uow.connection.execute('SELECT revoked_at FROM runtime_execution_grants WHERE grant_id=?', (grant_id,)).fetchone()[0]
        audit = uow.connection.execute("SELECT old_revision,new_revision FROM runtime_access_audit "
            "WHERE action='config.endpoint.update' AND resource_id=? ORDER BY rowid", (binding['endpoint_id'],)).fetchall()
        assert [tuple(r) for r in audit] == [(revision, revision + 1), (revision + 1, revision + 2)]


def test_operator_containment_rechecks_initiating_authority_before_effect(connected_local):
    from test_agent_recovery_isolation import eventually
    setup, binding, native = connected_local
    deps, app, client, headers, *_ = setup
    opened = admit(setup, binding, 'containment-authority-open', 'runtime.start', new_session=True)
    wait_receipt(setup, opened)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        profile = dict(uow.connection.execute('SELECT p.* FROM runtime_profiles p JOIN agent_endpoints e '
            'ON e.profile_id=p.profile_id WHERE e.endpoint_id=?', (binding['endpoint_id'],)).fetchone())
    disabled = client.patch('/api/v1/harness/profiles/' + profile['profile_id'], headers=headers['operator'],
        json=dict(expected_revision=profile['revision'], enabled=False))
    assert disabled.status_code == 200, disabled.text
    lock = app.state.embedded_dispatch_owner.pump.send_lock
    client.portal.call(lock.acquire)
    try:
        response = client.post('/api/v1/harness/sessions/' + opened['session_id'] + '/close',
            headers=headers['operator'], json=dict(idempotency_key='revoked-operator-close'))
        assert response.status_code == 200, response.text
        operation = response.json()['data']['operation_id']
        with deps.connection_factory.unit_of_work() as uow:
            uow.connection.execute("UPDATE agents SET api_key_hash='revoked-operator-key' WHERE agent_id='operator'")
    finally:
        client.portal.call(lock.release)
    def rejected():
        with deps.connection_factory.unit_of_work(write=False) as uow:
            row = uow.connection.execute('SELECT dispatch_state,last_error FROM execution_dispatch_outbox WHERE operation_id=?', (operation,)).fetchone()
            return dict(row) if row['dispatch_state'] == 'RESOLVED_TERMINAL' else None
    eventually(rejected)
    assert 'authority' in rejected()['last_error'].lower(), rejected()
    assert not native.native.stopped and native.native.sent == []
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert not uow.connection.execute('SELECT 1 FROM execution_receipts WHERE operation_id=?', (operation,)).fetchone()


def test_profile_disable_after_admission_prevents_native_write(connected_local):
    from test_agent_recovery_isolation import eventually
    setup, binding, native = connected_local
    deps, app, client, headers, *_ = setup
    owner = app.state.embedded_dispatch_owner
    owner.leases.max_duration_ms = 3000
    opened = admit(setup, binding, 'disable-after-open', 'runtime.start', new_session=True)
    wait_receipt(setup, opened)
    client.portal.call(owner.pump.send_lock.acquire)
    try:
        turn = admit(setup, binding, 'disable-after-admission', 'turn.submit', session_id=opened['session_id'], text='Do not write')
        with deps.connection_factory.unit_of_work(write=False) as uow:
            profile = dict(uow.connection.execute('SELECT p.* FROM runtime_profiles p JOIN agent_endpoints e '
                'ON e.profile_id=p.profile_id WHERE e.endpoint_id=?', (binding['endpoint_id'],)).fetchone())
        response = client.patch('/api/v1/harness/profiles/' + profile['profile_id'], headers=headers['operator'],
            json=dict(expected_revision=profile['revision'], enabled=False))
        assert response.status_code == 200, response.text
    finally:
        client.portal.call(owner.pump.send_lock.release)
    def rejected():
        response = client.get('/v1/runtime/operations/' + turn['operation_id'], headers=headers['subject'])
        assert response.status_code == 200, response.text
        return response.json() if response.json()['admission_state'] == 'RESOLVED_TERMINAL' else None
    eventually(rejected)
    assert rejected()['possible_effect'] is False
    assert rejected()['result'] is None and native.native.sent == []
    eventually(lambda: native.native.stopped)

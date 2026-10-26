import pytest
from test_embedded_dispatch import local_setup, connected_local, qualified_contract


def test_settings_validate_scope_cas_and_revoke_old_execution_authority(connected_local):
    setup, binding, _ = connected_local
    deps, _, client, headers, *_ = setup
    path = f"/api/v1/harness/endpoints/{binding['endpoint_id']}/harness-settings"
    current = client.get(path, headers=headers['operator']).json()['data']
    assert current['settings'] == {}
    body = dict(expected_revision=current['revision'], settings={'model':'test-model','effort':'high','approval_policy':'never','sandbox':'workspace-write'})
    assert client.put(path, headers=headers['subject'], json=body).status_code == 403
    invalid = {**body, 'settings':{'permission_mode':'auto'}}
    assert client.put(path, headers=headers['operator'], json=invalid).status_code == 422
    saved = client.put(path, headers=headers['operator'], json=body)
    assert saved.status_code == 200, saved.text
    assert saved.json()['data']['settings'] == body['settings']
    assert client.put(path, headers=headers['operator'], json=body).status_code == 409
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT revoked_at FROM runtime_execution_grants').fetchone()[0]


@pytest.mark.parametrize('local_setup', ['claude_stream'], indirect=True)
def test_permission_mode_change_reports_revocation_and_model_change_can_reissue(connected_local):
    """#94: a harness edit revokes grants and says so; reissue_grants re-arms in the same call."""
    setup, binding, _ = connected_local
    deps, _, client, headers, *_ = setup
    path = f"/api/v1/harness/endpoints/{binding['endpoint_id']}/harness-settings"
    def active():
        with deps.connection_factory.unit_of_work(write=False) as uow:
            return uow.connection.execute('SELECT count(*) FROM runtime_execution_grants '
                'WHERE endpoint_id=? AND revoked_at IS NULL', (binding['endpoint_id'],)).fetchone()[0]
    granted = active()
    assert granted >= 1
    current = client.get(path, headers=headers['operator']).json()['data']
    assert 'grants_revoked' not in current
    bad = client.put(path, headers=headers['operator'], json=dict(expected_revision=current['revision'],
        settings={'model': 'sonnet'}, reissue_grants='yes'))
    assert bad.status_code == 422, bad.text
    model = client.put(path, headers=headers['operator'], json=dict(expected_revision=current['revision'],
        settings={'model': 'sonnet', 'effort': 'high'}, reissue_grants=True))
    assert model.status_code == 200, model.text
    assert model.json()['data']['grants_revoked'] == model.json()['data']['grants_reissued'] == granted
    assert active() == granted
    mode = client.put(path, headers=headers['operator'], json=dict(expected_revision=model.json()['data']['revision'],
        settings={'model': 'sonnet', 'effort': 'high', 'permission_mode': 'plan'}))
    assert mode.status_code == 200, mode.text
    assert mode.json()['data']['grants_revoked'] == granted and mode.json()['data']['grants_reissued'] == 0
    assert active() == 0


def test_native_catalogue_reaches_ui_and_expires_with_account_revision(connected_local):
    import time
    from nexus_connector_core import discover_harness_configuration, RuntimeEvent
    from test_embedded_dispatch import admit, wait_receipt
    from okto_nexus.application.execution_harness_configuration import read_harness_configuration
    setup, binding, native = connected_local
    deps, app, client, headers, *_ = setup
    opened = admit(setup, binding, 'catalogue-open', 'runtime.start', new_session=True)
    wait_receipt(setup, opened)
    scope = opened['scope']
    with deps.connection_factory.unit_of_work(write=False) as uow:
        epoch = uow.connection.execute('SELECT stream_epoch FROM execution_local_streams WHERE session_id=?',
                                       (scope['session_id'],)).fetchone()[0]
    schema = discover_harness_configuration('codex_app_server', candidate_ref=binding['candidate_ref'],
        native_models={'data':[{'model':'observed-model','supportedReasoningEfforts':[{'reasoningEffort':'low'}]}]})
    event = RuntimeEvent(scope['server_id'],scope['executor_id'],scope['session_id'],epoch,0,
        'lifecycle','core/harness_configuration',{'harness_configuration':schema})
    client.portal.call(native.native.queue.put,event)
    deadline = time.monotonic()+8
    while True:
        with deps.connection_factory.unit_of_work(write=False) as uow:
            view = read_harness_configuration(uow.connection, endpoint_id=binding['endpoint_id'],adapter_id='codex_app_server')
        if view['models']:
            break
        assert time.monotonic() < deadline
        time.sleep(.05)
    assert view['models'][0]['id'] == 'observed-model'
    path = f"/api/v1/harness/endpoints/{binding['endpoint_id']}/harness-settings"
    current = client.get(path,headers=headers['operator']).json()['data']
    result = client.put(path,headers=headers['operator'],json=dict(expected_revision=current['revision'],
        settings={'model':'observed-model','effort':'high'}))
    assert result.status_code == 422
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute('SAVEPOINT catalogue_revision')
        uow.connection.execute('UPDATE execution_agent_revisions SET credential_epoch=credential_epoch+1')
        expired = read_harness_configuration(uow.connection, endpoint_id=binding['endpoint_id'],adapter_id='codex_app_server')
        assert expired['models'] == []
        uow.connection.execute('ROLLBACK TO catalogue_revision')
        uow.connection.execute('RELEASE catalogue_revision')

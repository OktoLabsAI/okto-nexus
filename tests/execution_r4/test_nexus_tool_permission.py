from test_embedded_dispatch import local_setup, connected_local, qualified_contract, admit, wait_receipt


def test_tool_permission_defaults_cas_and_revokes_grant(connected_local):
    setup, binding, _ = connected_local
    deps, _, client, headers, *_ = setup
    path = f"/api/v1/harness/endpoints/{binding['endpoint_id']}/tool-permission"
    current = client.get(path, headers=headers['operator']).json()['data']
    assert current['mode'] == 'ask'
    assert client.put(path, headers=headers['subject'], json=dict(expected_revision=current['revision'], mode='always_allow')).status_code == 403
    saved = client.put(path, headers=headers['operator'], json=dict(expected_revision=current['revision'], mode='always_allow'))
    assert saved.status_code == 200, saved.text
    assert saved.json()['data']['mode'] == 'always_allow'
    assert client.put(path, headers=headers['operator'], json=dict(expected_revision=current['revision'], mode='ask')).status_code == 409
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT revoked_at FROM runtime_execution_grants').fetchone()[0]


def test_tool_permission_requires_closed_session(connected_local):
    setup, binding, _ = connected_local
    op = admit(setup, binding, 'permission-open', 'runtime.start', new_session=True)
    wait_receipt(setup, op)
    path = f"/api/v1/harness/endpoints/{binding['endpoint_id']}/tool-permission"
    client, headers = setup[2:4]
    current = client.get(path, headers=headers['operator']).json()['data']
    response = client.put(path, headers=headers['operator'], json=dict(expected_revision=current['revision'], mode='always_allow'))
    assert response.status_code == 409, response.text
    assert client.get(path, headers=headers['operator']).json()['data']['mode'] == 'ask'
    wait_receipt(setup, admit(setup, binding, 'permission-close', 'runtime.close', session_id=op['session_id']), stages=('SUCCEEDED',))

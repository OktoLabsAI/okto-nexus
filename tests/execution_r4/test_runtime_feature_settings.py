"""Exercise operator boundaries and revisioned settings over the real HTTP API."""
from test_embedded_dispatch import local_setup, connected_local, qualified_contract
from test_embedded_dispatch import admit, wait_receipt


def test_one_shot_api_inherits_and_checks_revision(connected_local):
    setup = connected_local[0]
    client, headers = setup[2], setup[3]['operator']
    global_path = '/api/v1/one-shot-policy'
    agent_path = '/api/v1/agents/subject/one-shot-policy'
    response = client.get(global_path, headers=headers)
    assert response.status_code == 200, response.text
    global_policy = response.json()['data']
    settings = global_policy['settings'] | {'max_parallel': 10, 'warm_instances': 5}
    result = client.put(global_path, headers=headers, json=dict(expected_revision=global_policy['revision'], settings=settings))
    assert result.status_code == 200, result.text
    response = client.get(agent_path, headers=headers)
    assert response.status_code == 200, response.text
    agent = response.json()['data']
    assert agent['effective']['max_parallel'] == 10
    result = client.put(agent_path, headers=headers, json=dict(expected_revision=agent['revision'], settings={'warm_instances': 2}))
    assert result.status_code == 200, result.text
    assert result.json()['data']['effective']['warm_instances'] == 2
    stale = client.put(agent_path, headers=headers, json=dict(expected_revision=agent['revision'], settings={}))
    assert stale.status_code == 409
    denied = client.put(global_path, headers=setup[3]['subject'], json=dict(expected_revision=1, settings=settings))
    assert denied.status_code == 403, denied.text
    state_path = '/api/v1/agents/subject/one-shot-state'
    state = client.get(state_path, headers=headers).json()['data']
    assert (state['available'], state['max_pool_instances'], state['max_parallel'], state['warm_target']) == (0, 10, 10, 2)
    assert client.get(state_path, headers=setup[3]['subject']).status_code == 403
    current = client.get(agent_path, headers=headers).json()['data']
    assert client.put(agent_path, headers=headers, json=dict(expected_revision=current['revision'],
        settings={'max_parallel': 0, 'warm_instances': 2})).status_code == 200
    state = client.get(state_path, headers=headers).json()['data']
    assert state['max_pool_instances'] == state['max_parallel'] == 0
    from okto_nexus.application import one_shot_capacity as capacity
    with setup[0].connection_factory.unit_of_work() as uow:
        slot = capacity.reserve_warm(uow.connection, agent_id='subject', executor_id='test-host',
            configuration_digest='test-config', host_limit=5, now=0)
    state = client.get(state_path, headers=headers).json()['data']
    assert state['available'] == 0 and state['slots']['STARTING'] == 1
    with setup[0].connection_factory.unit_of_work() as uow:
        capacity.ready(uow.connection, slot_id=slot, session_id='ready-test-session')
    state = client.get(state_path, headers=headers).json()['data']
    assert state['available'] == 1 and state['occupied'] == 1


def test_mcp_preset_api_is_operator_only_and_revisioned(connected_local):
    setup, binding, _ = connected_local
    client, headers = setup[2], setup[3]['operator']
    path = '/api/v1/harness/endpoints/' + binding['endpoint_id'] + '/mcp-preset'
    initial = client.get(path, headers=headers)
    assert initial.status_code == 200, initial.text
    servers = [dict(name='docs', transport='http', url='https://example.test/mcp')]
    updated = client.put(path, headers=headers, json=dict(expected_revision=0, servers=servers))
    assert updated.status_code == 200, updated.text
    assert updated.json()['data']['servers'][0] == servers[0] | {'enabled': True, 'header_refs': {}}
    assert client.put(path, headers=headers, json=dict(expected_revision=0, servers=[])).status_code == 409
    assert client.get(path, headers=setup[3]['subject']).status_code == 403
    assert client.put(path, headers=setup[3]['subject'], json=dict(expected_revision=1, servers=[])).status_code == 403


def test_preset_snapshot_reaches_local_launch_and_keeps_previous_session(connected_local):
    setup, binding, native = connected_local
    seen = []
    original = native.open
    async def capture(prepared, *args, **kwargs):
        seen.append(prepared)
        return await original(prepared, *args, **kwargs)
    native.open = capture
    client, headers = setup[2], setup[3]['operator']
    path = '/api/v1/harness/endpoints/' + binding['endpoint_id'] + '/mcp-preset'
    first = [dict(name='docs', transport='http', url='https://first.test/mcp')]
    saved = client.put(path, headers=headers, json=dict(expected_revision=0, servers=first))
    assert saved.status_code == 200, saved.text
    opened = admit(setup, binding, 'preset-first', 'runtime.start', new_session=True)
    wait_receipt(setup, opened)
    assert seen[0].intent.mcp_preset[0]['url'] == 'https://first.test/mcp'
    second = [dict(name='docs', transport='http', url='https://second.test/mcp')]
    saved = client.put(path, headers=headers, json=dict(expected_revision=1, servers=second))
    assert saved.status_code == 200, saved.text
    assert seen[0].intent.mcp_preset[0]['url'] == 'https://first.test/mcp'
    opened = admit(setup, binding, 'preset-second', 'runtime.start', new_session=True)
    wait_receipt(setup, opened)
    assert seen[1].intent.mcp_preset[0]['url'] == 'https://second.test/mcp'

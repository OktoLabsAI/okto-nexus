import pytest
from test_embedded_dispatch import local_setup, connected_local, qualified_contract, admit, wait_receipt


def test_login_directory_suggestions_are_visible_only_to_local_operator(connected_local, monkeypatch):
    import nexus_connector_core
    setup, binding, _ = connected_local
    calls = []
    def discover(adapter):
        calls.append(adapter)
        return 'C:/approved/config'
    monkeypatch.setattr(nexus_connector_core, 'discover_provider_home', discover)
    params = dict(executor_id=binding['executor_id'], workspace_id=binding['workspace_id'])
    response = setup[2].get('/v1/agents/subject/runtime-options', params=params, headers=setup[3]['operator'])
    assert response.status_code == 200, response.text
    selected = next(item for item in response.json()['options'] if item['candidate_ref'])
    assert selected['provider_home_suggestion'] == 'C:/approved/config' and calls
    calls.clear()
    response = setup[2].get('/v1/agents/subject/runtime-options', params=params, headers=setup[3]['subject'])
    assert response.status_code == 200, response.text
    assert not calls
    assert all('provider_home_suggestion' not in item for item in response.json()['options'])


@pytest.mark.parametrize('local_setup', [('pi_rpc', 'untrusted')], indirect=True)
def test_approved_discovered_installation_reaches_core_without_trusting_inventory(connected_local):
    setup, binding, native = connected_local
    owner = setup[1].state.embedded_inventory_owner
    assert owner.candidates[0].trust == 'untrusted'
    opened = admit(setup, binding, 'discovered-open', 'runtime.start', new_session=True)
    wait_receipt(setup, opened)
    assert native.opens == 1
    assert owner.candidates[0].trust == 'untrusted'
    wait_receipt(setup, admit(setup, binding, 'discovered-close', 'runtime.close',
                             session_id=opened['session_id']), stages=('SUCCEEDED',))

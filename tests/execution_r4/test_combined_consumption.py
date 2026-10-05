"""Two live canonical executors compete for the same logical message claim."""
import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest
from nexus_connector_core import InstallationCandidate
from nexus_connector_core.discovery import fingerprint

from test_binding_operator import onboarding as remote_onboarding


@pytest.fixture
def combined_onboarding(tmp_path, monkeypatch):
    from okto_nexus.bootstrap import embedded_inventory, embedded_dispatch
    info = embedded_dispatch.protocol_info()
    monkeypatch.setattr(embedded_dispatch, 'protocol_info', lambda: {**info, 'remote_execution_ready': True})
    binary = tmp_path / 'local-codex.exe'
    binary.write_bytes(b'Combined local native fixture')
    candidate = InstallationCandidate('codex_app_server', str(binary), fingerprint(binary), 'explicit', 'selected')
    monkeypatch.setattr(embedded_inventory, 'discover_local_candidates',
                        lambda **_: SimpleNamespace(candidates=(candidate,)))
    yield from remote_onboarding.__wrapped__(tmp_path, SimpleNamespace(param='connector-configured'))


def prepare_embedded(onboarding, remote_binding, tmp_path, monkeypatch, qualified):
    from okto_nexus.bootstrap import embedded_dispatch
    from test_embedded_dispatch import connect_local
    monkeypatch.setattr(embedded_dispatch, 'protocol_info', lambda: qualified)
    deps, client, headers, _ = onboarding
    app = client.app
    owner = app.state.embedded_inventory_owner
    snapshot = client.get(f'/v1/runtime/executors/{owner.key.executor_id}/inventory',
                          headers=headers['operator']).json()['snapshot']
    root = tmp_path / 'combined-local-workspace'
    root.mkdir()
    body = dict(client_intent_id='combined-local', agent_id='subject', workspace_root=str(root),
        workspace_id=remote_binding['workspace_id'], workspace_label='Shared logical project',
        adapter_id='codex_app_server', candidate_ref=snapshot['evidence'][0]['candidate_ref'],
        inventory_revision=snapshot['inventory_revision'], local_consent_id='combined-consent',
        approved=True, provider_home=None, secret_bindings={})
    setup = (deps, app, client, headers, body, owner.candidates[0], root)
    result = connect_local(setup)
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agent_endpoints SET consumption='exclusive',response_policy='conversation' WHERE endpoint_id=?",
                               (result[1]['endpoint_id'],))
    return result


async def verify_competition(onboarding, remote_binding, embedded, remote_native, execution,
                             remote_session, winner, monkeypatch, remote_admit):
    from test_embedded_dispatch import admit, wait_receipt
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1]))
    from test_pr34_remediation import tool
    deps, client, headers, _ = onboarding
    setup, local_binding, local_native = embedded
    local_open = admit(setup, local_binding, 'combined-open', 'runtime.start', new_session=True)
    wait_receipt(setup, local_open)
    client.headers['host'] = '127.0.0.1:8000'
    created = tool(client, headers['operator']['Authorization'].removeprefix('Bearer '),
        'message_create', dict(workspace_id=remote_binding['workspace_id'], from_agent_id='operator',
            subject='One logical consumer', body='Review once.', target=dict(strategy='direct', agent_id='subject')))
    assert created['ok'], created
    with deps.connection_factory.unit_of_work(write=False) as uow:
        turns = list(uow.connection.execute("SELECT * FROM execution_operations WHERE action='turn.submit'"))
        assert len(turns) == 1
        turn = dict(turns[0])
        chosen = remote_binding if winner == 'remote' else local_binding
        assert turn['executor_id'] == chosen['executor_id']
        assert turn['session_id'] == (remote_session if winner == 'remote' else local_open['scope']['session_id'])
        delivery = uow.connection.execute('SELECT endpoint_id,operation_id FROM delivery_outbox').fetchone()
        assert delivery[0] == chosen['endpoint_id']
        assert uow.connection.execute('SELECT consumer_kind,consumer_operation_id FROM message_deliveries').fetchone()[:] == ('push', delivery[1])
        assert uow.connection.execute('SELECT COUNT(*) FROM delivery_outbox').fetchone()[0] == 1
    pulled = tool(client, headers['subject']['Authorization'].removeprefix('Bearer '), 'inbox_pull', dict(agent_id='subject'))
    assert pulled['ok'] and pulled['data']['messages'] == [], pulled
    async with asyncio.timeout(10):
        while True:
            result = client.get('/v1/runtime/operations/' + turn['operation_id'], headers=headers['subject'])
            assert result.status_code == 200, result.text
            assert result.json()['error'] is None, result.text
            if result.json()['executor_stage'] in ('SUBMITTED', 'SUCCEEDED'):
                break
            assert execution.failure is None, repr(execution.failure)
            await asyncio.sleep(.01)
    assert len(local_native.native.sent) == (winner == 'local')
    assert len(remote_native.native.sent) == (winner == 'remote')
    local_close = admit(setup, local_binding, 'combined-close', 'runtime.close', session_id=local_open['scope']['session_id'])
    wait_receipt(setup, local_close, stages=('SUCCEEDED',))
    await remote_admit('runtime.close', session_id=remote_session)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_sessions WHERE lifecycle_state='CLOSED'").fetchone()[0] == 2
        assert uow.connection.execute('SELECT COUNT(*) FROM harness_sessions').fetchone()[0] == 0


@pytest.mark.parametrize('winner', ['local', 'remote'])
def test_combined_executors_and_mcp_share_one_claim(combined_onboarding, tmp_path, monkeypatch, winner):
    from test_remote_connection import test_owned_connector_reader_dispatches_five_actions_over_real_websocket
    test_owned_connector_reader_dispatches_five_actions_over_real_websocket(
        combined_onboarding, tmp_path, monkeypatch, True, None, False, 0, None,
        domain_delivery=True, combined_winner=winner)

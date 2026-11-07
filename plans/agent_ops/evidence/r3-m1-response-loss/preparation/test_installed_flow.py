"""Real installed ASGI/SQLite/Core, synthetic native peer, no process/network."""
from copy import deepcopy
import json
import time

import pytest
from nexus_connector_core import RuntimeEvent
from okto_nexus.application.terminal_connection import ConnectionError, document_revision
from okto_nexus.application.terminal_work import TerminalWork
from response_loss import CampaignState, FiniteResponseLoss

from test_embedded_dispatch import local_setup, connected_local, qualified_contract, wait_receipt


@pytest.fixture(autouse=True)
def no_subprocess_or_vault(monkeypatch):
    import subprocess
    def deny(*args, **kwargs):
        raise AssertionError('Subprocess/vault forbidden in synthetic preparation')
    class NoProcess(subprocess.Popen):
        def __init__(self, *args, **kwargs):
            deny()
    monkeypatch.setattr(subprocess, 'Popen', NoProcess)
    import win32cred
    for name in ('CredRead', 'CredWrite', 'CredDelete', 'CredEnumerate'):
        monkeypatch.setattr(win32cred, name, deny)


def test_installed_admission_and_decision_response_loss_recover_without_replay(connected_local, tmp_path):
    setup, binding, native = connected_local
    deps, app, client, *_ = setup
    deps.config.feature_hitl = True
    checkpoint = tmp_path / 'work.json'
    def save(doc):
        checkpoint.write_text(json.dumps(doc), encoding='utf-8')
    def load():
        return json.loads(checkpoint.read_text())
    calls = []
    def http(method, path, body=None):
        calls.append((method, path))
        response = client.request(method, path, json=body, headers={'X-Nexus-UI': '1'})
        value = response.json()
        if response.status_code >= 400:
            error = value.get('error', {})
            raise ConnectionError(error.get('code', 'REQUEST_REFUSED'), 'Synthetic HTTP request refused',
                                  stage=error.get('stage', 'http'), possible_effect=error.get('possible_effect', False))
        return value
    connection = dict(state='done', server_id=binding['server_id'],
        selection=dict(agent='subject', client='codex', project=str(setup[6].resolve()), workspace_id=None,
                       candidate_ref=None, provider_home=None), result={'binding': binding})
    state = CampaignState(tmp_path / 'faults.json', campaign_id='installed-synthetic')
    state.arm('admission', 'connector', 'm1-synthetic-work')
    call = FiniteResponseLoss(http, load, state, 'connector')
    flow = TerminalWork(call, save, connection)
    with pytest.raises(ConnectionError) as error:
        flow.submit('PRIVATE_PROMPT_CANARY', client_intent_id='m1-synthetic-work')
    assert error.value.stage == 'm1_response_loss'
    before = deepcopy(load())
    state = CampaignState(state.path)
    call = FiniteResponseLoss(http, load, state, 'connector')
    flow = TerminalWork(call, save, connection, load())
    operation = flow.resume()
    assert operation['operation_id'] == before['work']['submission']['operation_id']
    assert operation['scope']['session_id'] == before['session_id']
    turn = {'operation_id': operation['submission_turn_operation_id']}
    wait_receipt(setup, turn)
    assert native.opens == 1 and len(native.native.sent) == 1
    replies = []
    async def reply(request, decision, response):
        replies.append((decision, response))
    native.native.reply_native_approval = reply
    with deps.connection_factory.unit_of_work(write=False) as uow:
        stream = dict(uow.connection.execute('SELECT * FROM execution_local_streams').fetchone())
    request = dict(schema_version=1, request_id=7, request_hash='a'*64,
        method='item/commandExecution/requestApproval',
        params={'threadId': 'synthetic-thread', 'turnId': 'turn-from-native', 'itemId': 'synthetic-item'})
    client.portal.call(native.native.queue.put, RuntimeEvent(stream['server_id'], stream['executor_id'],
        stream['session_id'], stream['stream_epoch'], 0, 'approval_request', request['method'],
        {'native_approval': request, 'native_approval_display': request}, turn['operation_id']))
    deadline = time.monotonic() + 15
    while True:
        observed = flow.observe()
        if observed['requests']['items']:
            break
        assert time.monotonic() < deadline
        time.sleep(.03)
    detail = observed['requests']['items'][0]
    proposal = detail['request_payload']['kwargs']
    state.arm('decision', 'connector', detail['approval_id'])
    with pytest.raises(ConnectionError) as error:
        flow.decide(detail['approval_id'], 'approve', reviewed_revision=document_revision(proposal))
    assert error.value.stage == 'm1_response_loss'
    saved_decision = deepcopy(load()['decision'])
    state = CampaignState(state.path)
    call = FiniteResponseLoss(http, load, state, 'connector')
    flow = TerminalWork(call, save, connection, load())
    decision = flow.decide(detail['approval_id'], 'approve', reviewed_revision=document_revision(proposal))
    assert decision['canonical_state'] == 'CONFIRMED'
    assert decision['client_intent_id'] == saved_decision['client_intent_id']
    assert decision['approval_key'] == saved_decision['approval_key']
    while not replies:
        assert time.monotonic() < deadline
        time.sleep(.03)
    assert len(replies) == 1
    assert sum(m == 'POST' and p.endswith('/runtime/operations') for m, p in calls) == 1
    assert sum(m == 'POST' and p.endswith('/runtime/approval-decisions') for m, p in calls) == 1
    client.portal.call(native.native.queue.put, RuntimeEvent(stream['server_id'], stream['executor_id'],
        stream['session_id'], stream['stream_epoch'], 0, 'turn_state', 'fixture.completed',
        dict(delivery_phase='terminal', delivery_outcome='success', output_text='Synthetic result'),
        operation_id=turn['operation_id']))
    wait_receipt(setup, turn, stages=('SUCCEEDED',))
    assert flow.observe()['state'] == 'completed'
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_operations WHERE action='turn.submit'").fetchone()[0] == 1
        assert uow.connection.execute('SELECT COUNT(*) FROM execution_sessions').fetchone()[0] == 1
    assert 'PRIVATE_PROMPT_CANARY' not in checkpoint.read_text() + state.path.read_text()
    close = flow.submit(action='close', client_intent_id='m1-synthetic-close')
    wait_receipt(setup, close, stages=('SUCCEEDED',))
    assert native.native.stopped
    assert all(v['phase'] == 'consumed' for v in state.snapshot()['faults'].values())

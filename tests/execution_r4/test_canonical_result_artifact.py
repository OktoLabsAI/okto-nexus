"""Large canonical output uses the existing private artifact publication path."""
import json
import threading
from pathlib import Path

import pytest
from nexus_connector_core import RuntimeEvent
from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, qualified_contract, admit, wait_receipt
from test_canonical_delivery import connected_local
from test_canonical_result_publication import current_turn, emit, wait_result, workspace
from test_message_workspace import call as send_message


def test_large_canonical_result_publishes_private_complete_artifact(connected_local, monkeypatch):
    setup, binding, native = connected_local
    deps, _, client, *_ = setup
    wid = workspace(setup)
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agent_endpoints SET consumption='exclusive',response_policy='conversation' WHERE endpoint_id=?", (binding['endpoint_id'],))
    sent = send_message(setup, monkeypatch, workspace_id=wid)
    assert sent['ok'], sent
    turn = current_turn(setup)
    wait_receipt(setup, turn)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        stream = dict(uow.connection.execute('SELECT * FROM execution_local_streams').fetchone())
    text = 'A' * 30000
    for _ in range(3):
        client.portal.call(native.native.queue.put, RuntimeEvent(stream['server_id'], stream['executor_id'],
            stream['session_id'], stream['stream_epoch'], 0, 'text_delta', 'fixture.output',
            dict(output_text=text), operation_id=turn['operation_id']))
    emit(setup, native, turn, '')
    row = wait_result(setup, 'PUBLISHED')
    assert row['output_artifact_id'] and row['artifact_reserved_bytes'] == 90000
    from okto_nexus.adapters.inbound.mcp.tools.artifacts import build_service
    payload, _, _ = build_service(deps).payload_for_operator(workspace_id=wid, artifact_id=row['output_artifact_id'])
    assert payload.decode() == text * 3
    with deps.connection_factory.unit_of_work(write=False) as uow:
        artifact = deps.repos.artifacts.get(uow, workspace_id=wid, artifact_id=row['output_artifact_id'])
        assert artifact.reader_agent_ids == ['operator', 'subject']
        message = uow.connection.execute('SELECT body,artifacts FROM messages WHERE message_id=?', (row['publication_message_id'],)).fetchone()
        assert 'Preview truncated' in message['body']
        assert json.loads(message['artifacts']) == [row['output_artifact_id']]
        assert uow.connection.execute('PRAGMA foreign_key_check').fetchall() == []
    wait_receipt(setup, admit(setup, binding, 'artifact-close', 'runtime.close', session_id=turn['session_id']), stages=('SUCCEEDED',))


def large_result(connected, monkeypatch):
    setup, binding, native = connected
    deps = setup[0]
    # Exercise automatic publication retries within a bounded test deadline.
    deps.runtime_dispatcher.recovery_seconds = .2
    deps.runtime_dispatcher.wake()
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agent_endpoints SET consumption='exclusive',response_policy='conversation' WHERE endpoint_id=?",
                               (binding['endpoint_id'],))
    sent = send_message(setup, monkeypatch, workspace_id=workspace(setup))
    assert sent['ok'], sent
    turn = current_turn(setup)
    wait_receipt(setup, turn)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        stream = dict(uow.connection.execute('SELECT * FROM execution_local_streams').fetchone())
    for _ in range(3):
        setup[2].portal.call(native.native.queue.put, RuntimeEvent(stream['server_id'], stream['executor_id'],
            stream['session_id'], stream['stream_epoch'], 0, 'text_delta', 'fixture.large',
            dict(output_text='L' * 30000), operation_id=turn['operation_id']))
    emit(setup, native, turn, '')
    return turn


@pytest.mark.parametrize('decision', ['approve', 'reject'])
def test_large_result_stays_private_until_governance_decision(connected_local, monkeypatch, decision):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1]))
    from test_hitl import _attach, _rule
    from test_pr34_remediation import tool
    from okto_nexus.application.runtime_results import RuntimeResultService
    setup, binding, native = connected_local
    deps, _, client, headers, *_ = setup
    deps.config.feature_hitl = True
    _attach(deps, 'subject', governance=[_rule('message_create', 'require_approval')])
    turn = large_result(connected_local, monkeypatch)
    pending = wait_result(setup, 'PENDING_APPROVAL')
    artifact_id = RuntimeResultService.artifact_id(pending)
    client.headers['host'] = '127.0.0.1:8000'
    key = headers['subject']['Authorization'].removeprefix('Bearer ')
    args = dict(project_root=str(setup[-1]), artifact_id=artifact_id)
    hidden = tool(client, key, 'artifact_get', args)
    assert not hidden['ok'] and hidden['error']['code'] == 'NOT_FOUND', hidden
    assert pending['artifact_reserved_bytes'] == 90000
    response = client.post('/api/v1/approvals/' + pending['publication_approval_id'] + '/decision',
        headers=headers['operator'], json=dict(decision=decision))
    assert response.status_code == 200, response.text
    final = wait_result(setup, 'PUBLISHED' if decision == 'approve' else 'BLOCKED')
    assert bool(final['output_artifact_id']) == (decision == 'approve')
    assert tool(client, key, 'artifact_get', args)['ok'] == (decision == 'approve')
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM delivery_outbox').fetchone()[0] == 1
    assert native.opens == 1 and len(native.native.sent) == 1
    wait_receipt(setup, admit(setup, binding, 'artifact-decision-close', 'runtime.close',
                             session_id=turn['session_id']), stages=('SUCCEEDED',))


def test_artifact_catalog_and_publication_rollback_together(connected_local, monkeypatch):
    from okto_nexus.application.runtime_results import RuntimeResultService
    setup, binding, native = connected_local
    deps = setup[0]
    finish = RuntimeResultService.finish
    failed = threading.Event()
    def cut(uow, **kwargs):
        finish(uow, **kwargs)
        failed.set()
        raise OSError('Publication commit cut')
    with monkeypatch.context() as patch:
        patch.setattr(RuntimeResultService, 'finish', staticmethod(cut))
        turn = large_result(connected_local, monkeypatch)
        assert failed.wait(10), 'Publication did not reach the commit cut'
        with deps.connection_factory.unit_of_work(write=False) as uow:
            assert uow.connection.execute('SELECT COUNT(*) FROM artifacts').fetchone()[0] == 0
            row = uow.connection.execute('SELECT publication_state,publication_message_id FROM runtime_results').fetchone()
            assert row[:] == ('PENDING_AUTHORIZATION', None)
        blobs = list(deps.repos.artifact_store.root.rglob('runtime-result.txt'))
        assert len(blobs) == 1 and blobs[0].read_bytes() == b'L' * 90000
    published = wait_result(setup, 'PUBLISHED')
    assert published['output_artifact_id']
    assert list(deps.repos.artifact_store.root.rglob('runtime-result.txt')) == blobs
    assert native.opens == 1 and len(native.native.sent) == 1
    wait_receipt(setup, admit(setup, binding, 'artifact-rollback-close', 'runtime.close',
                             session_id=turn['session_id']), stages=('SUCCEEDED',))

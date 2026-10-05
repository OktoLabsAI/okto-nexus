"""Large canonical output uses the existing private artifact publication path."""
import json
from nexus_connector_core import RuntimeEvent
from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, connected_local, qualified_contract, admit, wait_receipt
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

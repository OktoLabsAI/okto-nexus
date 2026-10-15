"""One registered agent keeps workspace context and native owners separate."""
import json

from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, qualified_contract, admit, wait_receipt
from test_canonical_delivery import connected_local, enable
from test_canonical_identity_lifecycle import second_binding
from test_runtime_contract_migration import mcp


def test_same_agent_in_two_workspaces_keeps_context_and_close_isolated(connected_local, monkeypatch):
    from test_vertical_inventory import _Native
    setup, first, native = connected_local
    deps, _, client, headers, *_, root = setup
    other = root.parent / 'other-workspace'
    other.mkdir()
    second = second_binding(setup, monkeypatch, workspace_root=other)
    enable(setup, first)
    enable(setup, second)
    captured = []
    original = _Native.send
    async def capture(peer, verb, payload, operation_id, **kwargs):
        captured.append((peer, operation_id, json.dumps(payload)))
        return await original(peer, verb, payload, operation_id, **kwargs)
    monkeypatch.setattr(_Native, 'send', capture)
    sessions = []
    for index, (project, binding) in enumerate(((root, first), (other, second))):
        created = mcp(setup, monkeypatch, headers['operator']['Authorization'].removeprefix('Bearer '),
            'message_create', dict(project_root=str(project), from_agent_id='operator',
                subject='Workspace isolation', body=f'PRIVATE_WORKSPACE_{index}',
                target=dict(strategy='broadcast')))
        assert created['ok'], created
        assert created['data']['recipients'] == ['subject']
        assert created['data']['delivered_count'] == 1
        with deps.connection_factory.unit_of_work(write=False) as uow:
            row = dict(uow.connection.execute("SELECT * FROM execution_operations WHERE action='turn.submit' AND binding_id=?",
                (binding['binding_id'],)).fetchone())
            envelope = json.loads(uow.connection.execute('SELECT envelope FROM delivery_outbox WHERE operation_id=?',
                (created['data']['runtime_operations'][0],)).fetchone()[0])
        wait_receipt(setup, row)
        assert row['workspace_id'] == binding['workspace_id'] == envelope['workspace_id']
        assert row['subject_agent_id'] == 'subject'
        sessions.append(row['session_id'])
    assert sessions[0] != sessions[1]
    assert first['workspace_id'] != second['workspace_id']
    assert len(captured) == 2 and native.opens == 2
    for index, (_, _, payload) in enumerate(captured):
        assert f'PRIVATE_WORKSPACE_{index}' in payload
        assert f'PRIVATE_WORKSPACE_{1-index}' not in payload
    wait_receipt(setup, admit(setup, first, 'workspace-first-close', 'runtime.close',
        session_id=sessions[0]), stages=('SUCCEEDED',))
    assert captured[0][0].stopped and not captured[1][0].stopped
    with deps.connection_factory.unit_of_work(write=False) as uow:
        states = dict(uow.connection.execute('SELECT session_id,lifecycle_state FROM execution_sessions'))
    assert states[sessions[0]] == 'CLOSED' and states[sessions[1]] == 'READY'
    # Closing a native conversation does not disconnect the configured runtime.
    # Its connected binding can automatically open a later conversation.
    wait_receipt(setup, admit(setup, first, 'workspace-first-reopen', 'runtime.start', new_session=True))
    assert native.opens == 3 and not captured[1][0].stopped
    wait_receipt(setup, admit(setup, second, 'workspace-second-close', 'runtime.close',
        session_id=sessions[1]), stages=('SUCCEEDED',))

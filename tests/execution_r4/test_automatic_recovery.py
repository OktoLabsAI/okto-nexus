import time
import json
from contextlib import contextmanager
import pytest
from test_embedded_dispatch import local_setup, connected_local, qualified_contract
from test_sender_sessions import configure, sender, turn_for
from test_runtime_policy_defaults import read, save
from okto_nexus.application.runtime_recovery import drain_pending


@pytest.mark.parametrize('possible_effect', [False, True])
def test_restart_after_dispatch_refusal_without_core_journal(tmp_path, monkeypatch, possible_effect):
    from fastapi.testclient import TestClient
    from test_embedded_inventory import app_for
    from test_embedded_dispatch import admit
    from okto_nexus.application import execution_dispatch_pump
    from okto_nexus.errors import ErrorCode, OktoNexusError
    with contextmanager(local_setup.__wrapped__)(tmp_path, monkeypatch, None) as setup:
        setup, binding, native = connected_local.__wrapped__(setup)
        deps, app, client, *_ = setup
        def refuse(**kwargs):
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED, 'Test authority was revoked before dispatch.', {})
        with monkeypatch.context() as patch:
            patch.setattr(execution_dispatch_pump, 'begin_execution_send', refuse)
            opened = admit(setup, binding, 'denied-before-core', 'runtime.start', new_session=True, text='Do not replay')
            deadline = time.monotonic() + 5
            while True:
                with deps.connection_factory.unit_of_work(write=False) as uow:
                    row = uow.connection.execute('SELECT lifecycle_state FROM execution_sessions WHERE session_id=?', (opened['session_id'],)).fetchone()
                if row[0] == 'FAILED': break
                assert time.monotonic() < deadline
                time.sleep(.02)
        assert native.opens == 0
        assert not app.state.embedded_dispatch_owner.host._journal_path(binding['executor_id'], opened['session_id']).exists()
    if possible_effect:
        with deps.connection_factory.unit_of_work() as uow:
            row = uow.connection.execute('SELECT last_error FROM execution_dispatch_outbox WHERE operation_id=?', (opened['operation_id'],)).fetchone()
            error = json.loads(row[0]); error['possible_effect'] = True
            uow.connection.execute('UPDATE execution_dispatch_outbox SET last_error=? WHERE operation_id=?', (json.dumps(error), opened['operation_id']))
    for _ in range(2):
        deps, app = app_for(tmp_path / 'home')
        with TestClient(app):
            owner = app.state.embedded_dispatch_owner
            assert owner.pump is not None
            assert ('subject' in owner.agents.blocked) is possible_effect
            with deps.connection_factory.unit_of_work(write=False) as uow:
                if not possible_effect:
                    assert uow.connection.execute("SELECT COUNT(*) FROM execution_operations WHERE admission_state<>'RESOLVED_TERMINAL'").fetchone()[0] == 0
                    assert uow.connection.execute('SELECT lease_state FROM execution_sessions').fetchone()[0] == 'CLOSED'
        assert native.opens == 0


def test_recovery_defaults_and_independent_switch(connected_local):
    setup,_,_=connected_local
    assert read(setup)['automatic_recovery'] is True
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        before=[tuple(r) for r in uow.connection.execute('SELECT * FROM runtime_execution_grants')]
    assert save(setup,automatic_recovery=False).status_code==200
    assert read(setup)['automatic_recovery'] is False
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        assert before==[tuple(r) for r in uow.connection.execute('SELECT * FROM runtime_execution_grants')]
    assert save(setup,automatic_recovery=True).status_code==200
    from okto_nexus.application.execution_log import read_execution_log
    log = read_execution_log(setup[0].connection_factory, agent_id='subject')
    assert any(row['code'] == 'RECOVERY_READY' for row in log['items'])


@pytest.mark.parametrize('claimed',[False,True])
def test_waiting_message_admitted_once_or_left_to_mcp(connected_local,monkeypatch,claimed):
    setup,binding,native=connected_local
    deps,app,client,*_=setup
    configure(setup,binding,'per_sender')
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE execution_executors SET control_state='RECOVERING'")
    mid=sender(setup,monkeypatch)('operator')
    with deps.connection_factory.unit_of_work() as uow:
        assert uow.connection.execute('SELECT status FROM runtime_pending_deliveries').fetchone()[0]=='waiting'
        assert uow.connection.execute('SELECT COUNT(*) FROM delivery_outbox').fetchone()[0]==0
        if claimed: uow.connection.execute("UPDATE message_deliveries SET status='read' WHERE message_id=?",(mid,))
        uow.connection.execute("UPDATE execution_executors SET control_state='CONTROL_READY'")
    drain_pending(deps)
    drain_pending(deps)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM delivery_outbox').fetchone()[0]==(0 if claimed else 1)
        assert uow.connection.execute('SELECT status FROM runtime_pending_deliveries').fetchone()[0]==('resolved' if claimed else 'submitted')


def test_disabled_recovery_keeps_conflict(connected_local,monkeypatch):
    setup,binding,_=connected_local
    configure(setup,binding,'shared')
    assert save(setup,automatic_recovery=False).status_code==200
    with setup[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE execution_executors SET control_state='RECOVERING'")
    with pytest.raises(AssertionError,match='reconciliation'):
        sender(setup,monkeypatch)('operator')
    with setup[0].connection_factory.unit_of_work() as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM runtime_pending_deliveries').fetchone()[0]==0
        uow.connection.execute("UPDATE execution_executors SET control_state='CONTROL_READY'")


def test_long_recovery_keeps_retrying_without_claiming_or_replaying_message(connected_local, monkeypatch):
    setup, binding, _ = connected_local
    deps = setup[0]
    configure(setup, binding, 'shared')
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE execution_executors SET control_state='RECOVERING'")
    sender(setup, monkeypatch)('operator')
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute('UPDATE runtime_pending_deliveries SET attempts=119')
    drain_pending(deps)
    with deps.connection_factory.unit_of_work() as uow:
        assert uow.connection.execute('SELECT status FROM runtime_pending_deliveries').fetchone()[0] == 'waiting'
        assert uow.connection.execute('SELECT consumer_kind FROM message_deliveries').fetchone()[0] is None
        assert uow.connection.execute('SELECT COUNT(*) FROM delivery_outbox').fetchone()[0] == 0
        uow.connection.execute("UPDATE execution_executors SET control_state='CONTROL_READY'")
    from okto_nexus.application.execution_log import read_execution_log
    log = read_execution_log(deps.connection_factory, agent_id='subject', severity='warning')
    assert any(row['code'] == 'WAITING_FOR_RUNTIME_RECOVERY' for row in log['items'])
    deadline = time.monotonic() + 10
    while True:
        with deps.connection_factory.unit_of_work(write=False) as uow:
            status = uow.connection.execute('SELECT status FROM runtime_pending_deliveries').fetchone()[0]
        if status == 'submitted':
            break
        assert time.monotonic() < deadline
        time.sleep(.02)
    drain_pending(deps)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM delivery_outbox').fetchone()[0] == 1


def test_queued_message_revalidates_rotated_sender_key(connected_local, monkeypatch):
    setup, binding, _ = connected_local
    deps = setup[0]
    configure(setup, binding, 'shared')
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE execution_executors SET control_state='RECOVERING'")
    sender(setup, monkeypatch)('operator')
    with deps.connection_factory.unit_of_work() as uow:
        setup[1].state.auth.issue_key(uow, agent_id='operator')
        uow.connection.execute("UPDATE execution_executors SET control_state='CONTROL_READY'")
    drain_pending(deps)
    with deps.connection_factory.unit_of_work() as uow:
        assert uow.connection.execute('SELECT status FROM runtime_pending_deliveries').fetchone()[0] == 'attention'
        assert uow.connection.execute('SELECT COUNT(*) FROM delivery_outbox').fetchone()[0] == 0


def test_deleting_unsubmitted_delivery_cleans_recovery_queue(connected_local, monkeypatch):
    setup, binding, _ = connected_local
    configure(setup, binding, 'shared')
    with setup[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE execution_executors SET control_state='RECOVERING'")
    message_id = sender(setup, monkeypatch)('operator')
    with setup[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute('DELETE FROM message_deliveries WHERE message_id=?', (message_id,))
        assert uow.connection.execute('SELECT COUNT(*) FROM runtime_pending_deliveries').fetchone()[0] == 0
        uow.connection.execute("UPDATE execution_executors SET control_state='CONTROL_READY'")

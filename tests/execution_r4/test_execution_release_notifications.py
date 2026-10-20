"""Contained native work reports uncertainty without fabricating completion."""
import pytest

from test_embedded_dispatch import local_setup, connected_local, qualified_contract, wait_receipt
from test_embedded_owner_replacement import fail_owner, wait_until
from test_sender_sessions import Peers, configure, sender, turn_for, complete
from okto_nexus.application.execution_release_notifications import publish_release_notifications
from okto_nexus.adapters.inbound.mcp.tools.harness import build_message_service


def replies(setup, message_id):
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        return [dict(row) for row in uow.connection.execute(
            'SELECT m.*,d.recipient_agent_id FROM messages m '
            'JOIN message_deliveries d USING(message_id) WHERE m.parent_message_id=?', (message_id,))]


@pytest.mark.parametrize('local_setup', ['pi_rpc', 'claude_stream', 'codex_app_server'], indirect=True)
def test_replacement_reports_interrupted_request_once_and_serves_new_work(connected_local, monkeypatch):
    setup, binding, _ = connected_local
    deps, app, client, *_ = setup
    old = app.state.embedded_dispatch_owner
    peers = Peers()
    old.native_factory = peers
    configure(setup, binding, 'per_sender')
    send = sender(setup, monkeypatch)
    message_id = send('sender-b')
    turn = turn_for(setup, message_id)
    wait_receipt(setup, turn)
    assert not replies(setup, message_id)
    peer = peers.sessions[turn['session_id']]
    fail_owner(client, old)
    wait_until(lambda: bool(replies(setup, message_id)))
    result = replies(setup, message_id)
    assert len(result) == 1
    assert result[0]['recipient_agent_id'] == 'sender-b'
    assert result[0]['from_agent_id'] == 'subject'
    assert result[0]['subject'] == 'Nexus runtime interrupted'
    assert 'RUNTIME_SESSION_ENDED' in result[0]['body']
    assert 'Actions may already have taken effect' in result[0]['body']
    assert peer.stopped and len(peer.sent) == 1
    assert publish_release_notifications(deps, build_message_service(deps)) == 0
    with deps.connection_factory.unit_of_work(write=False) as uow:
        conn = uow.connection
        assert conn.execute('SELECT COUNT(*) FROM runtime_results').fetchone()[0] == 0
        assert conn.execute('SELECT stage FROM execution_receipts WHERE operation_id=? '
            'ORDER BY receipt_revision DESC', (turn['operation_id'],)).fetchone()[0] == 'SUBMITTED'
        assert conn.execute('SELECT COUNT(*) FROM execution_release_notifications').fetchone()[0] == 1
        assert not conn.execute('SELECT 1 FROM delivery_outbox WHERE message_id=?', (result[0]['message_id'],)).fetchone()
        assert not conn.execute('PRAGMA foreign_key_check').fetchall()
    wait_until(lambda: app.state.embedded_dispatch_owner is not old
               and app.state.embedded_dispatch_owner.pump is not None)
    new = app.state.embedded_dispatch_owner
    client.portal.call(new.inventory.wait_usable_observation, setup[5].adapter_id)
    second_message = send('sender-b', 'New independent work')
    second = turn_for(setup, second_message)
    wait_receipt(setup, second)
    complete(setup, peers, second, 'New response')
    wait_until(lambda: bool(replies(setup, second_message)))
    assert len(replies(setup, message_id)) == 1
    assert replies(setup, second_message)[0]['body'] == 'New response'
    assert len(peer.sent) == 1


def test_notification_failure_rolls_back_and_retries_atomically(connected_local, monkeypatch):
    import okto_nexus.application.execution_release_notifications as notices
    setup, binding, _ = connected_local
    deps, app, client, *_ = setup
    owner = app.state.embedded_dispatch_owner
    configure(setup, binding, 'per_sender')
    message_id = sender(setup, monkeypatch)('operator')
    turn = turn_for(setup, message_id)
    wait_receipt(setup, turn)
    # Disable only the periodic notifier; all physical containment and release
    # proofs still come from the real supervisor, Core journals and ingress.
    monkeypatch.setattr(notices, 'publish_release_notifications', lambda *_: 0)
    fail_owner(client, owner)
    def released():
        with deps.connection_factory.unit_of_work(write=False) as uow:
            return uow.connection.execute('SELECT 1 FROM execution_delivery_releases').fetchone()
    wait_until(released)
    service = build_message_service(deps)
    # A release belonging to another admitted sender must not redirect a
    # notification. The observer also must not duplicate one-shot replies.
    with deps.connection_factory.unit_of_work() as uow:
        operation = uow.connection.execute('SELECT domain_operation_id FROM execution_delivery_releases').fetchone()[0]
        uow.connection.execute("UPDATE delivery_outbox SET actor_agent_id='sender-b' WHERE operation_id=?", (operation,))
    assert publish_release_notifications(deps, service) == 0
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE delivery_outbox SET actor_agent_id='operator' WHERE operation_id=?", (operation,))
    original = service._emitter.emit
    def fail_append(*args, **kwargs):
        raise RuntimeError('Injected notification append failure')
    monkeypatch.setattr(service._emitter, 'emit', fail_append)
    with pytest.raises(RuntimeError, match='notification append'):
        publish_release_notifications(deps, service)
    assert not replies(setup, message_id)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert tuple(uow.connection.execute('SELECT state,message_id FROM execution_release_notifications').fetchone()) == ('PENDING', None)
    monkeypatch.setattr(service._emitter, 'emit', original)
    assert publish_release_notifications(deps, service) == 1
    assert publish_release_notifications(deps, service) == 0
    assert len(replies(setup, message_id)) == 1


def test_upgrade_does_not_notify_historical_conversations():
    import importlib.resources
    import sqlite3
    conn = sqlite3.connect(':memory:')
    conn.executescript('''
        PRAGMA foreign_keys=ON;
        CREATE TABLE delivery_outbox(operation_id TEXT PRIMARY KEY);
        CREATE TABLE messages(message_id TEXT PRIMARY KEY);
        CREATE TABLE execution_delivery_releases(domain_operation_id TEXT PRIMARY KEY,created_at TEXT);
        INSERT INTO delivery_outbox VALUES('old-request');
        INSERT INTO execution_delivery_releases VALUES('old-request','2026-10-01T00:00:00Z');
    ''')
    migration = importlib.resources.files('okto_nexus').joinpath(
        'migrations/146_execution_release_notifications.sql').read_text(encoding='utf-8')
    conn.executescript(migration)
    assert conn.execute('SELECT * FROM execution_release_notifications').fetchall() == [
        ('old-request', None, 'HISTORICAL', '2026-10-01T00:00:00Z')]
    assert not conn.execute('SELECT 1 FROM messages').fetchone()
    assert not conn.execute('PRAGMA foreign_key_check').fetchall()
    conn.close()

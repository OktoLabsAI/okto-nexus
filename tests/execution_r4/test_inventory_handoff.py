"""Inventory producer replacement requires the current reconciled socket."""

from nexus_connector_core import R4_PREVIEW_REVISION, __version__, build_executor_inventory_snapshot

from okto_nexus.adapters.inbound.http import executor_link, runtime_v1
from test_binding_operator import onboarding


def test_inventory_handoff_fences_old_ticket_producer_and_precommit_revocation(onboarding, monkeypatch):
    deps, client, headers, _ = onboarding
    body = dict(client_intent_id='handoff-registration', connector_id='handoff-connector',
                label='Handoff host', control_capabilities=[])
    first = client.post('/v1/connections/executors:register', headers=headers['subject'], json=body).json()
    server_id, executor_id = first['server_id'], first['executor_id']
    ticket1 = first['bootstrap_ticket']
    active_ticket = ticket1['ticket']
    def publish(producer, seq, ticket=None):
        snapshot = build_executor_inventory_snapshot([], server_id=server_id, executor_id=executor_id,
            producer_instance_id=producer, publication_sequence=seq)
        return client.put(f'/v1/runtime/executors/{executor_id}/inventory', json=snapshot,
                          headers={'Authorization': 'Bearer ' + (ticket or active_ticket)})
    assert publish('initial-process', 1, ticket1['ticket']).status_code == 200
    second = client.post('/v1/connections/executors:register', headers=headers['subject'], json=body).json()
    ticket2 = second['bootstrap_ticket']
    active_ticket = ticket2['ticket']
    info = executor_link.protocol_info()
    monkeypatch.setattr(executor_link, 'protocol_info', lambda: {
        **info, 'remote_execution_ready': True, 'nxl_accepted': [R4_PREVIEW_REVISION]})
    with client.websocket_connect(f'wss://127.0.0.1:8202/v1/runtime/executors/{executor_id}/link',
            headers={'Authorization': 'Bearer ' + ticket2['ticket']}, subprotocols=['nxl.v1']) as ws:
        ws.send_json(dict(protocol_major=1, contract_revision=R4_PREVIEW_REVISION, type='hello',
            link_attempt_id='handoff-link', server_id=server_id, executor_id=executor_id,
            core_version=__version__, management_revision=info['management_revision'],
            supported_nxl=[R4_PREVIEW_REVISION], snapshot_formats=[info['executor_snapshot_format']],
            control_capabilities=[]))
        welcome, request = ws.receive_json(), ws.receive_json()
        producer = welcome['connection_id']
        assert publish(producer, 2).status_code == 409  # Still recovering.
        ws.send_json({k: request[k] for k in ('protocol_major', 'contract_revision', 'server_id', 'executor_id',
            'connection_id', 'connection_generation', 'reconcile_id', 'cursor')} | dict(
                type='reconcile.report', next_cursor=None, complete=True, receipts=[], claims=[],
                stream_watermarks=[], ownership_facts=[]))
        assert ws.receive_json()['recovery_remaining'] is False
        assert publish(producer, 1).status_code == 409  # New owner cannot reset sequence.
        assert publish(producer, 2).status_code == 200
        assert publish(producer, 2).status_code == 200  # Exact current replay.
        assert publish(producer, 3, ticket1['ticket']).status_code == 403
        assert publish('another-process', 3).status_code == 409
        assert publish('initial-process', 3, ticket1['ticket']).status_code == 403

        original = runtime_v1.verify_execution_ticket
        def revoke_after_validation(*args, **kwargs):
            verified = original(*args, **kwargs)
            with deps.connection_factory.unit_of_work() as uow:
                uow.connection.execute("UPDATE execution_link_tickets SET revoked_at='2026-09-30T00:00:00Z' "
                                       'WHERE ticket_id=?', (verified.ticket_id,))
            return verified
        monkeypatch.setattr(runtime_v1, 'verify_execution_ticket', revoke_after_validation)
        refused = publish(producer, 3)
        assert refused.status_code == 403, refused.text
        assert refused.json()['error']['message'] == 'The inventory publication authority has changed.'
    with deps.connection_factory.unit_of_work(write=False) as uow:
        row = uow.connection.execute('SELECT publication_sequence FROM execution_inventory_current '
                                    'WHERE executor_id=?', (executor_id,)).fetchone()
        assert row[0] == 2

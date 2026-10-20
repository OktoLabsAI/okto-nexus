"""Deferred canonical boot resolves again only with durable no-effect proof."""
import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from okto_nexus.adapters.inbound.mcp.tools import harness
from test_canonical_boot import configure
from test_embedded_dispatch import local_setup, connected_local, qualified_contract, wait_receipt
from okto_nexus.errors import ErrorCode, OktoNexusError


def test_blocked_inventory_boot_recovers_and_keeps_admitted_intent(connected_local):
    setup, binding, native = connected_local
    deps, app, client, *_ = setup
    configure(setup, binding)
    owner = app.state.embedded_inventory_owner
    scope = (owner.key.server_id, owner.key.executor_id)
    original = owner.fresh.pop(scope)
    try:
        first = harness.run_runtime_boot(deps)[0]
        assert first['state'] == 'blocked' and first['retryable']
        assert native.opens == 0
    finally:
        owner.fresh[scope] = original
    with ThreadPoolExecutor(max_workers=2) as workers:
        retries = list(workers.map(lambda _: harness.run_runtime_boot(deps)[0], range(2)))
    second = retries[0]
    assert retries[1]['operation_id'] == second['operation_id']
    assert second['state'] == 'ACCEPTED'
    wait_receipt(setup, second)
    third = harness.run_runtime_boot(deps)[0]
    assert third['operation_id'] == second['operation_id'] and third['reused']
    assert native.opens == 1
    with deps.connection_factory.unit_of_work(write=False) as uow:
        rows = uow.connection.execute('SELECT client_intent_id,resolved_json FROM execution_client_intents '
            "WHERE client_intent_id LIKE 'boot:%' ORDER BY created_at").fetchall()
        assert len(rows) == 2
        assert not json.loads(rows[0]['resolved_json'])['can_submit']
        assert rows[1]['client_intent_id'] == rows[0]['client_intent_id'] + ':retry:1'


def test_admitted_boot_is_not_replaced_when_inventory_later_disappears(connected_local):
    setup, binding, native = connected_local
    deps, app, *_ = setup
    configure(setup, binding)
    first = harness.run_runtime_boot(deps)[0]
    wait_receipt(setup, first)
    owner = app.state.embedded_inventory_owner
    scope = (owner.key.server_id, owner.key.executor_id)
    receipt = owner.fresh.pop(scope)
    try:
        repeat = harness.run_runtime_boot(deps)[0]
        assert repeat['operation_id'] == first['operation_id'] and repeat['reused']
        assert native.opens == 1
    finally:
        owner.fresh[scope] = receipt


def test_expired_unadmitted_boot_gets_new_resolution_after_transient_failure(connected_local, monkeypatch):
    from okto_nexus.bootstrap import execution_compat
    setup, binding, native = connected_local
    deps, *_ = setup
    configure(setup, binding)
    original = execution_compat.submit_execution_operation
    def unavailable(*args, **kwargs):
        raise OktoNexusError(ErrorCode.DB_ERROR, 'Transient admission failure', {}, retryable=True)
    monkeypatch.setattr(execution_compat, 'submit_execution_operation', unavailable)
    first = harness.run_runtime_boot(deps)[0]
    assert first['state'] == 'blocked' and first['retryable'] and native.opens == 0
    with deps.connection_factory.unit_of_work() as uow:
        row = uow.connection.execute('SELECT client_intent_id,resolved_json FROM execution_client_intents '
            "WHERE client_intent_id LIKE 'boot:%'").fetchone()
        resolution = json.loads(row['resolved_json'])
        assert resolution['can_submit'] and not resolution['blockers']
        assert uow.connection.execute('SELECT COUNT(*) FROM execution_operations').fetchone()[0] == 0
        resolution['expires_at'] = '2000-01-01T00:00:00+00:00'
        uow.connection.execute('UPDATE execution_client_intents SET resolved_json=? WHERE client_intent_id=?',
            (json.dumps(resolution), row['client_intent_id']))
    monkeypatch.setattr(execution_compat, 'submit_execution_operation', original)
    second = harness.run_runtime_boot(deps)[0]
    assert second['state'] == 'ACCEPTED'
    wait_receipt(setup, second)
    assert native.opens == 1

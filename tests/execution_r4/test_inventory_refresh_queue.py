"""Durable refresh correlation; synthetic executor, no transport delivery yet."""
import json

import pytest

from test_binding_operator import onboarding
from test_binding_views import bound
from okto_nexus.application.execution_inventory_refresh import request_inventory_refresh, claim_inventory_refresh
from okto_nexus.application.executor_inventory import publish_executor_inventory
from okto_nexus.bootstrap.execution_authority import build_execution_access
from okto_nexus.domain.execution.keys import ExecutorKey
from okto_nexus.domain.runtime_context import RuntimeRequestContext
from okto_nexus.errors import OktoNexusError


def request(state, intent='refresh-1', actor='subject'):
    deps, _, _, binding = state
    with deps.connection_factory.unit_of_work(write=False) as uow:
        credential = uow.connection.execute('SELECT api_key_hash FROM agents WHERE agent_id=?', (actor,)).fetchone()[0]
    return request_inventory_refresh(deps.connection_factory,
        context=RuntimeRequestContext(actor, 'agent_key', credential_binding=credential),
        access=build_execution_access(deps), server_id=binding['server_id'],
        executor_id=binding['executor_id'], client_intent_id=intent)


def channel(state, generation=1):
    deps, _, _, binding = state
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE execution_executors SET owner_instance_id='peer',generation=?,"
            "control_state='CONTROL_READY' WHERE executor_id=?", (generation, binding['executor_id']))


def claim(state, generation=1):
    deps, _, _, binding = state
    with deps.connection_factory.unit_of_work() as uow:
        return claim_inventory_refresh(uow, server_id=binding['server_id'], executor_id=binding['executor_id'],
            producer_instance_id='peer', connection_generation=generation)


def publish(state, delivery=None, increment=1):
    deps, _, _, binding = state
    with deps.connection_factory.unit_of_work(write=False) as uow:
        row = uow.connection.execute('SELECT s.canonical_projection FROM execution_inventory_current c '
            'JOIN execution_inventory_snapshots s USING(server_id,executor_id,publication_sequence) '
            'WHERE c.executor_id=?', (binding['executor_id'],)).fetchone()
    snapshot = json.loads(row[0])
    snapshot['publication_sequence'] += increment
    return publish_executor_inventory(deps.connection_factory,
        principal=ExecutorKey(binding['server_id'], binding['executor_id']),
        producer_instance_id='peer', snapshot=snapshot, refresh_delivery_id=delivery)


def test_refresh_is_idempotent_and_only_correlated_new_publication_completes(bound):
    first = request(bound)
    assert request(bound) == first and first['state'] == 'OFFLINE'
    channel(bound)
    assert request(bound)['state'] == 'PENDING'
    delivery = claim(bound)
    assert claim(bound) == delivery and request(bound)['state'] == 'REQUESTED'
    with pytest.raises(OktoNexusError, match='does not match'):
        publish(bound, delivery, increment=0)
    publish(bound)  # An unrelated periodic publication is not the requested observation.
    assert request(bound)['state'] == 'REQUESTED'
    result = publish(bound, delivery)
    final = request(bound)
    assert final['refresh_id'] == first['refresh_id'] and final['state'] == 'UPDATED'
    assert publish(bound, delivery, increment=0).reused
    assert claim(bound) is None
    with bound[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT completed_sequence FROM execution_inventory_refresh').fetchone()[0] == result.publication_sequence
        assert uow.connection.execute('SELECT COUNT(*) FROM execution_operations').fetchone()[0] == 0


def test_refresh_queue_is_bounded_and_does_not_charge_replays(bound):
    for index in range(32):
        request(bound, str(index))
    assert request(bound, '0')['refresh_id']
    with pytest.raises(OktoNexusError) as error:
        request(bound, 'overflow')
    assert error.value.code == 'CAPACITY_EXCEEDED'


def test_refresh_scope_is_rechecked_on_replay(bound):
    request(bound)
    with pytest.raises(OktoNexusError) as error:
        request(bound, actor='other')
    assert error.value.code == 'NOT_FOUND'
    deps, _, _, binding = bound
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE execution_executors SET registered_by_agent_id='operator' WHERE executor_id=?",
                               (binding['executor_id'],))
        uow.connection.execute('UPDATE agent_endpoints SET enabled=0 WHERE endpoint_id=?', (binding['endpoint_id'],))
    with pytest.raises(OktoNexusError):
        request(bound)
    assert request(bound, actor='operator')['refresh_id']


def test_old_delivery_cannot_complete_after_channel_generation_changes(bound):
    request(bound)
    channel(bound)
    delivery = claim(bound)
    channel(bound, generation=2)
    with pytest.raises(OktoNexusError):
        claim(bound)
    replacement = claim(bound, generation=2)
    assert replacement != delivery
    with pytest.raises(OktoNexusError):
        publish(bound, delivery)
    # Failure rolls back the snapshot as well as leaving the request pending.
    assert publish(bound, replacement).publication_sequence == 2
    assert request(bound)['state'] == 'UPDATED'


def test_request_arriving_after_claim_waits_for_a_separate_observation(bound):
    request(bound)
    channel(bound)
    delivery = claim(bound)
    later = request(bound, 'later')
    assert later['state'] == 'PENDING'
    publish(bound, delivery)
    assert request(bound, 'later')['state'] == 'PENDING'
    next_delivery = claim(bound)
    assert next_delivery != delivery
    publish(bound, next_delivery)
    assert request(bound, 'later')['state'] == 'UPDATED'


def test_request_survives_new_factory_and_stale_credential_is_refused(bound):
    from dataclasses import replace
    from okto_nexus.adapters.outbound.sqlite.connection import ConnectionFactory
    deps, client, headers, binding = bound
    first = request(bound)
    replacement = replace(deps, connection_factory=ConnectionFactory(deps.config))
    assert request((replacement, client, headers, binding)) == first
    with deps.connection_factory.unit_of_work() as uow:
        old = uow.connection.execute("SELECT api_key_hash FROM agents WHERE agent_id='subject'").fetchone()[0]
        client.app.state.auth.issue_key(uow, agent_id='subject')
    with pytest.raises(OktoNexusError) as error:
        request_inventory_refresh(deps.connection_factory,
            context=RuntimeRequestContext('subject', 'agent_key', credential_binding=old),
            access=build_execution_access(deps), server_id=binding['server_id'],
            executor_id=binding['executor_id'], client_intent_id='refresh-1')
    assert error.value.code == 'PERMISSION_DENIED'

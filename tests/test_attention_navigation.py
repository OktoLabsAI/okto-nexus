"""Canonical references, maintenance lookup and material attention revisions."""
import json
from types import SimpleNamespace

import pytest

import test_attention_operations as operation_fixtures
from test_attention_operations import cleanup, delivery, handoff, only, NOW, LATER
from okto_nexus.errors import ErrorCode, OktoNexusError

cleanup_service = operation_fixtures.cleanup_service
db = operation_fixtures.db


def test_delivery_attention_references_the_original_message_without_copying_it(db):
    delivery(db, status='parked')
    item, = only(db, 'delivery_parked')
    assert item['source_id'] == 'd' and item['message_id'] == 'm-d'
    assert 'SECRET BODY' not in json.dumps(item)
    db.execute("UPDATE message_deliveries SET status='unread' WHERE delivery_id='d'")
    db.execute("INSERT INTO runtime_pending_deliveries(delivery_id,status,reason,context_json,authorization_revision,created_at) "
               "VALUES('d','attention','fixture','{}','fixture',?)", (NOW,))
    recovered, = only(db, 'runtime_recovery_attention')
    assert recovered['message_id'] == 'm-d'


def test_age_threshold_change_fences_the_view_but_preserves_the_waiting_episode(db):
    handoff(db, status='OPEN', claimant=None)
    first, = only(db, 'handoff_unclaimed_aged', now=LATER, policy={'handoff_unclaimed_seconds': 300})
    second, = only(db, 'handoff_unclaimed_aged', now=LATER, policy={'handoff_unclaimed_seconds': 600})
    assert first['attention_id'] == second['attention_id']
    assert first['source_revision'] != second['source_revision']
    assert first['first_detected_at'] != second['first_detected_at']
    assert second['source_revision'] == only(db, 'handoff_unclaimed_aged', now=LATER,
        policy={'handoff_unclaimed_seconds': 600})[0]['source_revision']


def dump(factory):
    with factory.unit_of_work(write=False) as uow:
        return list(uow.connection.iterdump())


def test_canonical_cleanup_lookup_reaches_beyond_the_summary_and_resumes_the_same_receipt(cleanup_service):
    service, factory, artifacts, calls, _ = cleanup_service
    with pytest.raises(OktoNexusError) as failure:
        cleanup(service)
    target = failure.value.details['maintenance_id']
    with factory.unit_of_work() as uow:
        for index in range(105):
            uow.connection.execute("INSERT INTO runtime_result_maintenance "
                "(maintenance_id,actor_agent_id,idempotency_key,request_hash,action,result_id,reason,status,created_at,updated_at) "
                "VALUES(?,'operator',?,'fixture','quota',NULL,'Synthetic older record','PENDING',?,?)",
                (f'older-{index:03}', f'older-key-{index:03}', '2020-01-01T00:00:00Z', NOW))
    context = SimpleNamespace(actor_agent_id='operator')
    before, effect_count = dump(factory), len(calls)
    overview = service.artifacts(context)
    assert len(overview['pending_maintenance']) == 100
    assert target not in {row['maintenance_id'] for row in overview['pending_maintenance']}
    inspected = service.artifacts(context, maintenance_id=target)
    record = inspected['maintenance']
    assert record['maintenance_id'] == target and record['status'] == 'PENDING'
    assert inspected['pending_maintenance'] == [record]
    assert inspected['results'][0]['result_id'] == record['result_id'] == 'result'
    assert record['attention_failure_code'] == 'ARTIFACT_CLEANUP_UNCONFIRMED'
    assert len(calls) == effect_count and dump(factory) == before
    assert 'SECRET' not in json.dumps(inspected) and 'output_text' not in json.dumps(inspected)
    with factory.unit_of_work(write=False) as uow:
        attention, = only(uow.connection, 'cleanup_attention')
        assert attention['source_id'] == target and attention['result_id'] == 'result'
    artifacts.discard_unpublished = lambda **kwargs: {'absent': True, 'removed_directories': []}
    result = service.artifacts(context, action=record['action'], result_id=record['result_id'],
        idempotency_key=record['idempotency_key'], reason=record['reason'])
    assert result['maintenance_id'] == target and result['state'] == 'DONE'
    complete = service.artifacts(context, maintenance_id=target)
    assert complete['maintenance']['status'] == 'DONE' and complete['pending_maintenance'] == []


@pytest.mark.parametrize('parameters', [
    {'maintenance_id': ''}, {'maintenance_id': True}, {'maintenance_id': 'x'*129},
    {'maintenance_id': 'missing', 'action': 'cleanup', 'result_id': 'result',
     'idempotency_key': 'new', 'reason': 'must not run'},
    {'maintenance_id': 'missing', 'reason': 'not an inspection field'},
])
def test_maintenance_selector_cannot_be_used_as_a_mutation(cleanup_service, parameters):
    service, factory, _, calls, _ = cleanup_service
    before = dump(factory)
    with pytest.raises(OktoNexusError) as error:
        service.artifacts(SimpleNamespace(actor_agent_id='operator'), **parameters)
    assert error.value.code == ErrorCode.VALIDATION_ERROR
    assert not calls and dump(factory) == before


def test_missing_maintenance_is_not_an_empty_success(cleanup_service):
    service, factory, _, calls, _ = cleanup_service
    before = dump(factory)
    with pytest.raises(OktoNexusError) as error:
        service.artifacts(SimpleNamespace(actor_agent_id='operator'), maintenance_id='missing')
    assert error.value.code == ErrorCode.NOT_FOUND
    assert not calls and dump(factory) == before

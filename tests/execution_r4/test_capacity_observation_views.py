"""Real Core assessments and read-only Server projection invalidate changed scopes."""
import json

import pytest
from okto_nexus.bootstrap.capacity_observations import build_capacity_observation_view
from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, qualified_contract, wait_receipt
from test_canonical_delivery import connected_local
from test_canonical_handoff_regressions import runtime
from test_handoff_runtime_attempts import prepared
from test_handoff_runtime_candidates import enable_capacity


def assessed(runtime, *, freeze_observation_clock=False):
    service, port, attempt, hid, _ = prepared(runtime)
    enable_capacity(runtime)
    registry = runtime[0][0].runtime_availability
    if freeze_observation_clock:
        # Core assessments last 100 ms. Isolate configuration invalidation from
        # wall-clock scheduling; TTL expiry has separate cache/browser coverage.
        now = registry.monotonic()
        registry.monotonic = registry.diagnostics.monotonic = lambda: now
    result = runtime[0][2].portal.call(registry.assess_capacity, attempt.request)
    assert result.available, result
    service.capacity = registry
    return service, port, attempt, hid


def overview(setup):
    response = setup[2].get('/api/v1/agents/subject/runtime-administration', headers=setup[3]['operator'])
    assert response.status_code == 200, response.text
    return response.json()['data']['capacity_observations']


@pytest.mark.parametrize('change', [
    "UPDATE agents SET permissions='{\"handoffs\":{\"work\":false}}' WHERE agent_id='subject'",
    "UPDATE agents SET metadata='{\"changed\":true}' WHERE agent_id='subject'",
    "UPDATE agents SET api_key_hash='rotated-test-key' WHERE agent_id='subject'",
    "UPDATE agents SET is_active=0 WHERE agent_id='subject'",
    "UPDATE execution_bindings SET binding_revision=binding_revision+1",
    "UPDATE execution_workspace_bindings SET status='STALE'",
])
def test_config_authority_and_binding_changes_invalidate_observations_without_writes(runtime, change):
    setup = runtime[0]
    assessed(runtime, freeze_observation_clock=True)
    before = overview(setup)
    assert before['items'][0]['state'] == 'OPENING_CAPACITY_OBSERVED' and before['items'][0]['fresh']
    with setup[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute(change)
        old = tuple(uow.connection.execute('SELECT * FROM execution_agent_revisions WHERE agent_id=\'subject\'').fetchone())
    view = build_capacity_observation_view(setup[0])
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        changes = uow.connection.total_changes
        statements = []
        uow.connection.set_trace_callback(statements.append)
        result = view.read(uow, 'subject')
        assert uow.connection.total_changes == changes
        assert len(statements) <= 7
        assert tuple(uow.connection.execute('SELECT * FROM execution_agent_revisions WHERE agent_id=\'subject\'').fetchone()) == old
    row = result['items'][0]
    assert row['state'] == 'UNKNOWN' and not row['fresh']
    assert row['reason'] == 'STALE_OBSERVATION'
    assert runtime[2].opens == 0


def test_operator_projection_tracks_real_reservation_and_release_without_invoking_model(runtime):
    setup = runtime[0]
    service, _, attempt, _ = assessed(runtime)
    aid = attempt.request.attempt_id
    setup[2].portal.call(service.reserve, aid)
    row = overview(setup)['items'][0]
    assert row['state'] == 'RESERVED' and row['fresh']
    registry = setup[0].runtime_availability
    held = service.get(aid).reservation
    setup[2].portal.call(registry.release_capacity, attempt.request, held.reservation_id, 'CANCELLED')
    released = overview(setup)['items'][0]
    assert released['state'] == 'UNKNOWN' and released['reason'] == 'RELEASED'
    assert runtime[2].opens == 0
    assert setup[2].get('/api/v1/agents/subject/runtime-administration', headers=setup[3]['subject']).status_code == 403
    raw = json.dumps(overview(setup))
    assert held.reservation_id not in raw and attempt.request.request_hash not in raw
    for headers in setup[3].values():
        assert headers['Authorization'].removeprefix('Bearer ') not in raw

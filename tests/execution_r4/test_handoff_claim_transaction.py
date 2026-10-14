"""The outer claim transaction owns every admission effect and wakeup."""
import pytest

from okto_nexus.adapters.inbound.mcp.tools.handoff import build_service
from okto_nexus.domain.runtime_context import RuntimeRequestContext
from okto_nexus.errors import OktoNexusError
from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, qualified_contract, wait_receipt
from test_canonical_delivery import connected_local
from test_canonical_handoff_regressions import runtime, work, grant, claim, assert_unclaimed
from test_canonical_result_publication import current_turn, workspace
from test_sender_sessions import configure
from test_one_shot_runtime import query, wait_until


def composed(runtime, hid, gid, monkeypatch):
    deps = runtime[0][0]
    service = build_service(deps)
    # Actual existing actor authority, not a scheduler principal or fake key.
    with deps.connection_factory.unit_of_work(write=False) as uow:
        actor = deps.repos.agents.get(uow, 'caller')
    context = RuntimeRequestContext('caller', 'agent_key', credential_binding=actor.api_key_hash)
    calls = []
    monkeypatch.setattr(service.runtime_work, 'wake', lambda: calls.append('wake'))
    def forbidden(*args, **kwargs):
        raise AssertionError('The supplied claim transaction must not open another UoW')
    # Replace only this service factory; runtime owners still use the real one.
    from types import SimpleNamespace
    service._cf = SimpleNamespace(unit_of_work=forbidden)
    service._request_context_provider = forbidden
    def apply(uow, **options):
        return service.claim_managed_in_transaction(uow, workspace_id=workspace(runtime[0]),
            handoff_id=hid, agent_id='subject', context=context,
            runtime_endpoint_id=runtime[1]['endpoint_id'], execution_grant_id=gid,
            idempotency_key='outer-claim', **options)
    return service, apply, calls


def test_outer_rollback_and_commit_preserve_single_canonical_claim(runtime, monkeypatch):
    hid, gid = work(runtime), grant(runtime)
    service, apply, wakes = composed(runtime, hid, gid, monkeypatch)
    deps = runtime[0][0]
    with pytest.raises(RuntimeError, match='outer rollback'):
        with deps.connection_factory.unit_of_work() as uow:
            first = apply(uow)
            assert first['claim_epoch'] == 1
            assert uow.connection.execute('SELECT count(*) FROM execution_operations').fetchone()[0] == 2
            assert wakes == []
            # An independent reader cannot observe the claim before commit.
            with deps.connection_factory.unit_of_work(write=False) as reader:
                assert reader.connection.execute('SELECT status FROM handoffs WHERE handoff_id=?', (hid,)).fetchone()[0] == 'OPEN'
            raise RuntimeError('outer rollback')
    assert_unclaimed(runtime, hid, gid)
    assert wakes == []
    with deps.connection_factory.unit_of_work() as uow:
        committed = apply(uow)
    assert wakes == []
    service.wake_claim_dispatch()
    assert wakes == ['wake']
    with deps.connection_factory.unit_of_work() as uow:
        replayed = apply(uow)
        assert replayed['runtime_operation']['reused']
        assert replayed['runtime_operation']['operation_id'] == committed['runtime_operation']['operation_id']
        assert uow.connection.execute('SELECT used_executions FROM runtime_execution_grants WHERE grant_id=?', (gid,)).fetchone()[0] == 1
    wait_receipt(runtime[0], current_turn(runtime[0]))
    assert runtime[2].opens == len(runtime[2].native.sent) == 1


def test_immediate_one_shot_refuses_full_pool_without_claim_or_queue(runtime, monkeypatch):
    setup, binding, _ = runtime
    configure(setup, binding, 'one_shot')
    with setup[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agent_endpoints SET response_policy='none' WHERE endpoint_id=?", (binding['endpoint_id'],))
    first, second, gid = work(runtime), work(runtime), grant(runtime)
    assert claim(runtime, first, gid, key='occupy')['ok']
    wait_until(setup, lambda: query(setup, "SELECT 1 FROM execution_operations WHERE action='turn.submit'"))
    wait_receipt(setup, current_turn(setup))
    _, apply, wakes = composed(runtime, second, gid, monkeypatch)
    with pytest.raises(OktoNexusError, match='POOL_FULL'):
        with setup[0].connection_factory.unit_of_work() as uow:
            apply(uow, immediate_only=True)
    assert wakes == []
    assert query(setup, 'SELECT status,claim_epoch FROM handoffs WHERE handoff_id=?', (second,))[0][:] == ('OPEN', 0)
    assert query(setup, 'SELECT count(*) FROM one_shot_calls')[0][0] == 1
    assert query(setup, 'SELECT count(*) FROM runtime_handoff_bindings')[0][0] == 1
    assert query(setup, 'SELECT used_executions FROM runtime_execution_grants WHERE grant_id=?', (gid,))[0][0] == 1
    # The unchanged explicit endpoint retains its intentional queue behavior.
    assert claim(runtime, second, gid, key='explicit-wait')['ok']
    assert query(setup, "SELECT count(*) FROM one_shot_calls WHERE state='QUEUED'")[0][0] == 1


def test_immediate_cold_one_shot_is_admitted_in_claim_transaction(runtime, monkeypatch):
    setup, binding, _ = runtime
    configure(setup, binding, 'one_shot')
    with setup[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agent_endpoints SET response_policy='none' WHERE endpoint_id=?", (binding['endpoint_id'],))
    hid, gid = work(runtime), grant(runtime)
    _, apply, wakes = composed(runtime, hid, gid, monkeypatch)
    with setup[0].connection_factory.unit_of_work() as uow:
        result = apply(uow, immediate_only=True)
        call_id = result['runtime_operation']['operation_id']
        row = uow.connection.execute('SELECT state,admission_deadline,enqueued_at FROM one_shot_calls WHERE call_id=?', (call_id,)).fetchone()
        assert row['state'] == 'ADMITTED'
        assert 0 < row['admission_deadline'] - row['enqueued_at'] <= 60
        slot = uow.connection.execute('SELECT state,session_id,open_operation_id FROM one_shot_slots WHERE call_id=?', (call_id,)).fetchone()
        assert slot['state'] == 'STARTING' and slot['session_id'] and slot['open_operation_id']
        assert wakes == [] and runtime[2].opens == 0
    wait_receipt(setup, current_turn(setup))
    assert runtime[2].opens == len(runtime[2].native.sent) == 1


def test_empty_canonical_admission_cannot_commit_immediate_claim(runtime, monkeypatch):
    hid, gid = work(runtime), grant(runtime)
    service, apply, wakes = composed(runtime, hid, gid, monkeypatch)
    monkeypatch.setattr(service.runtime_work, 'canonical_admit', lambda *args, **kwargs: [])
    with pytest.raises(OktoNexusError, match='requires an execution'):
        with runtime[0][0].connection_factory.unit_of_work() as uow:
            apply(uow, immediate_only=True)
    assert_unclaimed(runtime, hid, gid)
    assert wakes == []

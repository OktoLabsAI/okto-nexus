"""Transient Server writes cannot revoke the shared embedded owner."""
import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from okto_nexus.bootstrap.embedded_dispatch import EmbeddedDispatchOwner
from okto_nexus.errors import ErrorCode, OktoNexusError


@pytest.mark.parametrize('phase', ['grant', 'ack'])
@pytest.mark.parametrize('expired', [False, True])
def test_transient_renewal_failure_retries_or_contains_only_session(phase, expired):
    async def scenario():
        import time
        calls, recovered, failed_agents, failed_hosts = [], [], [], []
        deadline = time.monotonic() + (-1 if expired else 60)
        context = SimpleNamespace(lease_deadline_monotonic=deadline)
        application = SimpleNamespace(context=context, acknowledgement={'serial': 2})
        fault = OktoNexusError(ErrorCode.DB_ERROR, 'writer timeout', {}, retryable=True)

        async def renew(**kwargs):
            calls.append('grant')
            if phase == 'grant' and calls.count('grant') == 1:
                raise fault
            return application

        def applied(*args, **kwargs):
            calls.append('ack')
            if phase == 'ack' and calls.count('ack') == 1:
                raise fault

        @asynccontextmanager
        async def gate(_):
            yield

        async def fail_agent(*args):
            failed_agents.append(args)

        async def fail_host():
            failed_hosts.append(True)

        session = {'scope': {'agent_id': 'Pi'}, 'executor': SimpleNamespace(
            context=context, renew_r4=renew), 'renew_at': 0}
        owner = SimpleNamespace(
            sessions={'one': session}, _stopping=asyncio.Event(), _renewal_gate=gate,
            channel=SimpleNamespace(connection_id='link', connection_generation=1),
            _request_grant=None, leases=SimpleNamespace(applied=applied), failure=None,
            verify=lambda: None, failed=fail_host,
            agents=SimpleNamespace(fail=fail_agent, recover_session=recovered.append),
            _schedule_renewal=lambda *args: calls.append('scheduled'))
        await EmbeddedDispatchOwner._renew_owned(owner, 'one', session)
        assert not failed_agents and not failed_hosts
        assert context.lease_deadline_monotonic == deadline
        if expired:
            assert recovered == ['one']
        else:
            assert not recovered
            assert time.monotonic() <= session['renew_at'] <= deadline
            await EmbeddedDispatchOwner._renew_owned(owner, 'one', session)
            assert calls[-1] == 'scheduled'
            # Persist the exact already-installed ACK; never issue another
            # authority revision while that application is unacknowledged.
            assert calls.count('grant') == (2 if phase == 'grant' else 1)
            assert 'renewal_application' not in session
    asyncio.run(scenario())


@pytest.mark.parametrize('local_setup', ['codex_app_server', 'claude_stream', 'pi_rpc'], indirect=True)
@pytest.mark.parametrize('phase', ['grant', 'ack'])
def test_real_writer_timeout_preserves_runtime_and_next_renewal(local_setup, monkeypatch, phase):
    import threading
    from test_embedded_dispatch import connect_local, admit, wait_receipt
    setup, binding, native = connect_local(local_setup)
    deps, app, client, *_ = setup
    owner = app.state.embedded_dispatch_owner
    opened = admit(setup, binding, 'renew-contention-open', 'runtime.start', new_session=True)
    wait_receipt(setup, opened)
    sid = opened['session_id']
    session = owner.sessions[sid]
    original_uow = owner.factory.unit_of_work
    target = owner.leases.issue if phase == 'grant' else owner.leases.applied
    local = threading.local()
    failures = []

    def uow(*args, **kwargs):
        transaction = original_uow(*args, **kwargs)
        if getattr(local, 'inject', False):
            transaction._busy_timeout_ms = 25
        return transaction

    def contend(*args, **kwargs):
        if failures:
            return target(*args, **kwargs)
        failures.append(1)
        gate = owner.factory._writer_gate
        gate.acquire(5)
        local.inject = True
        try:
            return target(*args, **kwargs)
        finally:
            local.inject = False
            gate.release()

    monkeypatch.setattr(owner.factory, 'unit_of_work', uow)
    monkeypatch.setattr(owner.leases, 'issue' if phase == 'grant' else 'applied', contend)
    client.portal.call(owner._renew_owned, sid, session)
    assert failures == [1]
    assert owner.failure is None and not owner._stopping.is_set()
    assert not owner.agents.blocked and not session.get('recovering')
    assert not native.native.stopped
    client.portal.call(owner._renew_owned, sid, session)
    assert 'renewal_application' not in session
    turn = admit(setup, binding, 'renew-contention-turn', 'turn.submit',
                 session_id=sid, text='Exactly once after writer contention')
    wait_receipt(setup, turn)
    assert len(native.native.sent) == 1 and native.opens == 1
    with deps.connection_factory.unit_of_work(write=False) as tx:
        assert tx.connection.execute("SELECT control_state FROM execution_executors WHERE kind='embedded'").fetchone()[0] == 'CONTROL_READY'


from test_embedded_dispatch import local_setup, qualified_contract


@pytest.mark.parametrize('phase', ['state', 'diagnostic'])
def test_recovery_status_timeout_retains_subject_fence_without_host_containment(phase):
    from okto_nexus.bootstrap.embedded_agent_recovery import EmbeddedAgentRecovery
    from nexus_connector_core import CoreError

    async def scenario():
        def timeout(*args, **kwargs):
            raise OktoNexusError(ErrorCode.DB_ERROR, 'writer timeout', {}, retryable=True)
        owner = SimpleNamespace(verify=lambda: None, _recovery_event=timeout if phase == 'diagnostic' else lambda *a, **k: None)
        agents = EmbeddedAgentRecovery(owner)
        owner.agents = agents
        agents._state = timeout if phase == 'state' else lambda *a: None
        original = CoreError('EVENT_STREAM_UNAVAILABLE', 'fixture')
        await agents.fail('Pi', original)
        assert agents.blocked == {'Pi'} and agents.errors['Pi'] is original
        for action in ('runtime.open', 'turn.submit', 'turn.steer'):
            with pytest.raises(CoreError) as caught:
                EmbeddedDispatchOwner._require_subject_available(owner, {'agent_id': 'Pi', 'action': action})
            assert caught.value.code == 'RECONCILIATION_REQUIRED'
            EmbeddedDispatchOwner._require_subject_available(owner, {'agent_id': 'claude', 'action': action})
        for action in ('runtime.close', 'turn.interrupt'):
            EmbeddedDispatchOwner._require_subject_available(owner, {'agent_id': 'Pi', 'action': action})
    asyncio.run(scenario())


def test_nonretryable_recovery_state_failure_remains_fatal():
    from okto_nexus.bootstrap.embedded_agent_recovery import EmbeddedAgentRecovery

    async def scenario():
        owner = SimpleNamespace(verify=lambda: None)
        agents = EmbeddedAgentRecovery(owner)
        def permanent(*args):
            raise OktoNexusError(ErrorCode.DB_ERROR, 'permanent', {}, retryable=False)
        agents._state = permanent
        with pytest.raises(OktoNexusError) as caught:
            await agents.fail('Pi', ValueError())
        assert not caught.value.retryable
    asyncio.run(scenario())

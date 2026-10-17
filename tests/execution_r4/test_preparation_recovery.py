"""A failed pre-Core preparation must converge under its current host owner."""
from nexus_connector_core import LocalRuntimeCore
from nexus_connector_core.native.adapter_types import NativeAdapterError, ErrorCode
import pytest

from test_agent_recovery_isolation import eventually
from test_embedded_dispatch import local_setup, connect_local, admit, wait_receipt


def test_failed_preparation_recovers_without_restarting_owner(local_setup, monkeypatch):
    setup, binding, native = connect_local(local_setup)
    _, app, client, *_ = setup
    owner = app.state.embedded_dispatch_owner
    prepare = LocalRuntimeCore.prepare
    failures = []
    injected = []
    original_fail = owner.agents.fail

    async def fail(agent_id, error):
        failures.append((getattr(error, 'code', type(error).__name__), getattr(error, 'stage', None)))
        await original_fail(agent_id, error)

    async def unavailable(runtime, *args, **kwargs):
        if not injected:
            injected.append(True)
            raise NativeAdapterError(ErrorCode.CONFIG_ERROR, 'Native version probe exceeded its deadline.',
                                     {'reason': 'version_probe_timeout'})
        return await prepare(runtime, *args, **kwargs)

    monkeypatch.setattr(owner.agents, 'fail', fail)
    monkeypatch.setattr(LocalRuntimeCore, 'prepare', unavailable)
    opened = admit(setup, binding, 'preparation-failed', 'runtime.start', new_session=True)
    eventually(lambda: bool(injected))
    def settled():
        with setup[0].connection_factory.unit_of_work(write=False) as uow:
            state = uow.connection.execute('SELECT lifecycle_state FROM execution_sessions WHERE session_id=?',
                                           (opened['session_id'],)).fetchone()[0]
        return state in ('CLOSED', 'FAILED') and 'subject' not in owner.agents.blocked
    try:
        eventually(settled, seconds=45)
    except AssertionError as error:
        raise AssertionError(f'Recovery did not converge: {failures}') from error
    assert native.opens == 0
    assert not failures, 'Preparation recovery must not fence the whole agent'
    assert owner.failure is None
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT lifecycle_state FROM execution_sessions WHERE session_id=?',
                                      (opened['session_id'],)).fetchone()[0] in ('CLOSED', 'FAILED')
    next_open = admit(setup, binding, 'after-preparation-recovery', 'runtime.start', new_session=True)
    wait_receipt(setup, next_open)
    assert native.opens == 1


@pytest.mark.parametrize('local_setup', ['pi_rpc', 'codex_app_server', 'claude_stream'], indirect=True)
def test_failed_native_launch_recovers_under_current_owner(local_setup, monkeypatch):
    setup, binding, native = connect_local(local_setup)
    _, app, client, *_ = setup
    owner = app.state.embedded_dispatch_owner
    connection_generation = owner.channel.connection_generation
    original = native.open
    failures = []

    async def failed_once(prepared, session_id, context, *, stream_epoch, process_launch):
        if not failures:
            def fail():
                failures.append(session_id)
                raise NativeAdapterError(ErrorCode.CONFIG_ERROR, 'Version probe deadline',
                                         {'reason':'version_probe_timeout'})
            return await process_launch.produce(validate_authority=lambda: None, start=fail)
        return await original(prepared, session_id, context, stream_epoch=stream_epoch)

    monkeypatch.setattr(native, 'open', failed_once)
    opened = admit(setup, binding, 'native-start-failed', 'runtime.start', new_session=True)
    eventually(lambda: bool(failures))
    def settled():
        with setup[0].connection_factory.unit_of_work(write=False) as uow:
            row = uow.connection.execute('SELECT lifecycle_state,lease_state FROM execution_sessions WHERE session_id=?',
                                        (opened['session_id'],)).fetchone()
        return tuple(row) in (('CLOSED','CLOSED'),('FAILED','CLOSED')) and 'subject' not in owner.agents.blocked
    eventually(settled, seconds=45)
    assert owner.channel.connection_generation == connection_generation
    assert owner.failure is None
    assert failures == [opened['session_id']]
    assert native.opens == 0
    next_open = admit(setup, binding, 'after-native-failure', 'runtime.start', new_session=True)
    wait_receipt(setup, next_open)
    assert native.opens == 1

"""A delayed coordinator heartbeat must not contain the entire local host."""
from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, qualified_contract, admit, wait_receipt
from test_canonical_delivery import connected_local


def test_local_dispatch_continues_after_expired_heartbeat(connected_local):
    setup, binding, native = connected_local
    deps, app, *_ = setup
    owner = app.state.embedded_dispatch_owner
    opened = admit(setup, binding, 'before-pause', 'runtime.start', new_session=True)
    wait_receipt(setup, opened)
    session = opened['scope']['session_id']
    generation = owner.channel.connection_generation
    with deps.connection_factory.unit_of_work() as uow:
        # Equivalent persisted owner state after a suspend longer than 40s.
        # Verify inside this transaction so a concurrent heartbeat cannot hide it.
        uow.connection.execute("UPDATE runtime_dispatcher_owner SET lease_expires_at='2000-01-01T00:00:00Z'")
        owner.verify(uow=uow)
    sent = admit(setup, binding, 'after-pause', 'turn.submit', session_id=session, text='Still available')
    wait_receipt(setup, sent)
    assert owner.failure is None and not owner._stopping.is_set()
    assert not deps.runtime_dispatcher._stop.is_set()
    assert owner.channel.connection_generation == generation
    assert native.opens == 1 and len(native.native.sent) == 1
    wait_receipt(setup, admit(setup, binding, 'pause-close', 'runtime.close', session_id=session), stages=('SUCCEEDED',))

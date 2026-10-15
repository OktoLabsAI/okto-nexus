"""One slow agent cannot consume all shared pre-ack dispatch reservations."""
import asyncio

from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, qualified_contract, connect_local, admit, wait_receipt
from test_canonical_delivery import connected_local
from test_agent_recovery_isolation import create_agent, eventually
from test_sender_sessions import Peers


def test_slow_agent_cannot_fill_every_dispatch_slot_with_parallel_sessions(connected_local):
    setup, binding, _ = connected_local
    healthy_setup, healthy_binding, _ = connect_local(create_agent(setup, 'healthy'), agent_id='healthy')
    release = asyncio.Event()
    started = []
    class Held(Peers):
        async def open(self, prepared, session_id, context, *, stream_epoch):
            started.append(context.agent_id)
            if context.agent_id == 'subject':
                await release.wait()
            return await super().open(prepared, session_id, context, stream_epoch=stream_epoch)
    factory = Held()
    setup[1].state.embedded_dispatch_owner.native_factory = factory
    pending = []
    try:
        for index in range(4):
            pending.append(admit(setup, binding, 'slow-parallel-'+str(index), 'runtime.start', new_session=True))
        eventually(lambda: 'subject' in started)
        healthy = admit(healthy_setup, healthy_binding, 'healthy-amid-openings', 'runtime.start', new_session=True)
        wait_receipt(healthy_setup, healthy)
        assert not release.is_set()
        # Sessions of the same agent remain independent. With four regular
        # workers, three can start concurrently and one stays available to
        # another agent without waiting for those openings to finish.
        eventually(lambda: started.count('subject') == 3)
        assert started.count('subject') == 3, started
        assert started.count('healthy') == 1, started
    finally:
        setup[2].portal.call(release.set)
    for opening in pending:
        wait_receipt(setup, opening)
    assert started.count('subject') == 4

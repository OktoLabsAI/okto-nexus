"""The transition out of opening must join its in-flight authority update."""
import asyncio

from okto_nexus.bootstrap import embedded_dispatch


def test_opening_exit_joins_renewal_before_admitting_productive_turn():
    async def run():
        owner = object.__new__(embedded_dispatch.EmbeddedDispatchOwner)
        session = dict(gate=asyncio.Lock(), authority_gate=embedded_dispatch.SessionAuthorityGate())
        opened, finish_open = asyncio.Event(), asyncio.Event()
        renewing, finish_renewal = asyncio.Event(), asyncio.Event()
        productive = asyncio.Event()
        async def opening():
            async with owner._gate(session, 'runtime.open'):
                opened.set()
                await finish_open.wait()
        async def renewal():
            async with owner._renewal_gate(session):
                renewing.set()
                await finish_renewal.wait()
        async def turn():
            async with owner._gate(session, 'turn.submit'):
                productive.set()
        tasks = []
        try:
            tasks.append(asyncio.create_task(opening()))
            await opened.wait()
            tasks.append(asyncio.create_task(renewal()))
            await asyncio.wait_for(renewing.wait(), 1)
            tasks.append(asyncio.create_task(turn()))
            finish_open.set()
            await asyncio.sleep(0)
            assert not productive.is_set() and not tasks[0].done()
            finish_renewal.set()
            await asyncio.wait_for(asyncio.gather(*tasks), 1)
            assert productive.is_set() and session['opening'] is False
        finally:
            finish_open.set()
            finish_renewal.set()
            await asyncio.gather(*tasks, return_exceptions=True)
    asyncio.run(run())

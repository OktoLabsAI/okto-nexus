"""NS14.03: storage/publication waits cannot postpone native containment."""
import asyncio
import threading

import pytest
from nexus_connector_core import OperationKey

from test_embedded_dispatch import (
    local_setup, connected_local, qualified_contract, admit, wait_receipt,
)


@pytest.mark.parametrize("blocked", ["quiesce", "pump", "history"])
def test_native_containment_precedes_cleanup_and_preserves_stores(
        connected_local, monkeypatch, blocked):
    setup, binding, native = connected_local
    _, app, client, *_ = setup
    owner = app.state.embedded_dispatch_owner
    instances = []
    original_open = native.open

    async def capture(*args, **kwargs):
        result = await original_open(*args, **kwargs)
        instances.append(result)
        return result

    monkeypatch.setattr(native, "open", capture)
    opened = [admit(setup, binding, "shutdown-order-" + str(i),
                    "runtime.start", new_session=True) for i in range(2)]
    for operation in opened:
        wait_receipt(setup, operation)
    assert len(instances) == 2 and native.opens == 2

    entered = threading.Event()
    release = threading.Event()
    original_quiesce = owner._quiesce
    original_stop = owner.pump.stop

    def quiesce():
        entered.set()
        assert release.wait(10), "Cleanup was not released"
        original_quiesce()

    async def pump_stop():
        entered.set()
        await asyncio.to_thread(release.wait)
        await original_stop()

    if blocked == "quiesce":
        monkeypatch.setattr(owner, "_quiesce", quiesce)
    elif blocked == "pump":
        monkeypatch.setattr(owner.pump, "stop", pump_stop)

    async def scenario():
        history = None
        if blocked == "history":
            async def read(journal):
                entered.set()
                await asyncio.to_thread(release.wait)
                return await journal.get_receipt(
                    OperationKey(
                        opened[0]["scope"]["server_id"],
                        opened[0]["scope"]["executor_id"],
                        opened[0]["operation_id"]))
            history = asyncio.create_task(owner.host.with_history(
                executor_id=opened[0]["scope"]["executor_id"],
                session_id=opened[0]["scope"]["session_id"], read=read))
            await asyncio.wait_for(asyncio.to_thread(entered.wait), 3)
        closing = asyncio.create_task(owner.close())
        try:
            await asyncio.wait_for(asyncio.to_thread(entered.wait), 3)
            async with asyncio.timeout(2):
                while not all(instance.stopped for instance in instances):
                    await asyncio.sleep(.01)
            assert not closing.done()
            assert len(owner.host._runtime_tasks) == 2
            for operation in opened:
                receipt = await owner.host.operation_receipt(
                    session_id=operation["scope"]["session_id"],
                    key=OperationKey(operation["scope"]["server_id"],
                        operation["scope"]["executor_id"], operation["operation_id"]))
                assert receipt is not None
        finally:
            release.set()
            if history is not None:
                assert await asyncio.wait_for(history, 5) is not None
            await asyncio.wait_for(closing, 5)
        assert not owner.host._runtime_tasks
        assert native.opens == 2

    client.portal.call(scenario)

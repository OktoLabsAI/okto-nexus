"""NS14.03: storage/publication waits cannot postpone native containment."""
import asyncio
import threading

import pytest
from nexus_connector_core import OperationKey

from test_embedded_dispatch import (
    local_setup, connected_local, qualified_contract, admit, wait_receipt,
)


@pytest.mark.parametrize("bounded", [False, True])
@pytest.mark.parametrize("blocked", ["quiesce", "pump", "history"])
def test_native_containment_precedes_cleanup_and_preserves_stores(
        connected_local, monkeypatch, blocked, bounded):
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
        closing = None
        try:
            if bounded:
                started = asyncio.get_running_loop().time()
                report = await owner.request_shutdown(timeout_seconds=.1)
                assert asyncio.get_running_loop().time() - started < .5
                assert report["state"] == "DRAINING_PENDING"
                assert {r["session_id"] for r in report["resources"]} == {
                    operation["scope"]["session_id"] for operation in opened}
                assert all(r["store_retained"] for r in report["resources"])
                retained_task = owner._close_task
                repeated = await owner.request_shutdown(timeout_seconds=10)
                assert repeated["deadline_monotonic"] == report["deadline_monotonic"]
                assert owner._close_task is retained_task and not retained_task.cancelled()
            closing = asyncio.create_task(owner.close())
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
            await asyncio.wait_for(closing if closing is not None else owner.close(), 5)
        assert not owner.host._runtime_tasks
        assert native.opens == 2
        if bounded:
            await asyncio.wait_for(owner.wait_shutdown(), 5)
            report = await owner.request_shutdown(timeout_seconds=.1)
            assert report["state"] == "DRAINED" and report["resources"] == []

    client.portal.call(scenario)


@pytest.mark.parametrize("fault", ["unknown", "error"])
def test_bounded_shutdown_recovers_same_uncertain_runtime(connected_local, monkeypatch, fault):
    setup, binding, native = connected_local
    _, app, client, *_ = setup
    owner = app.state.embedded_dispatch_owner
    opened = admit(setup, binding, "uncertain-shutdown", "runtime.start", new_session=True)
    wait_receipt(setup, opened)
    native_instance = native.native
    original_close = native_instance.close

    async def unknown_close():
        return "unknown"

    original_shutdown = owner.host.shutdown
    restored = threading.Event()

    async def failed_shutdown(*args, **kwargs):
        if not restored.is_set():
            raise OSError("Technical containment failure")
        return await original_shutdown(*args, **kwargs)

    if fault == "unknown":
        monkeypatch.setattr(native_instance, "close", unknown_close)
    else:
        monkeypatch.setattr(owner.host, "shutdown", failed_shutdown)

    async def scenario():
        original_runtimes = dict(owner.host._runtime_tasks)
        try:
            report = await owner.request_shutdown(timeout_seconds=.1)
            if fault == "error":
                with pytest.raises(OSError, match="Technical containment failure"):
                    await asyncio.wait_for(owner.close(), 10)
            else:
                await asyncio.wait_for(owner.close(), 10)
            assert owner.shutdown_status()["state"] == "DRAINING_PENDING"
            assert owner.host._runtime_tasks == original_runtimes
            monkeypatch.setattr(native_instance, "close", original_close)
            restored.set()
            recovered = await owner.request_shutdown(timeout_seconds=20)
            assert recovered["deadline_monotonic"] == report["deadline_monotonic"]
            await asyncio.wait_for(owner.wait_shutdown(), 10)
            assert owner.shutdown_status()["state"] == "DRAINED"
            assert native_instance.stopped and native.opens == 1
        finally:
            monkeypatch.setattr(native_instance, "close", original_close)
            restored.set()
            if owner.host._runtime_tasks:
                await owner.request_shutdown(timeout_seconds=0)
                await asyncio.wait_for(owner.wait_shutdown(), 10)

    client.portal.call(scenario)


def test_cancelled_shutdown_request_keeps_cleanup_owned(connected_local, monkeypatch):
    setup, binding, native = connected_local
    _, app, client, *_ = setup
    owner = app.state.embedded_dispatch_owner
    opened = admit(setup, binding, "cancelled-shutdown", "runtime.start", new_session=True)
    wait_receipt(setup, opened)
    entered, release = threading.Event(), threading.Event()
    original = owner._quiesce

    def quiesce():
        entered.set()
        assert release.wait(10)
        original()

    monkeypatch.setattr(owner, "_quiesce", quiesce)

    async def scenario():
        observer = asyncio.create_task(owner.request_shutdown(timeout_seconds=50))
        try:
            await asyncio.wait_for(asyncio.to_thread(entered.wait), 3)
            retained = owner._close_task
            observer.cancel()
            with pytest.raises(asyncio.CancelledError):
                await observer
            assert owner._close_task is retained and not retained.done()
            assert owner.shutdown_status()["state"] == "DRAINING_PENDING"
        finally:
            release.set()
            await asyncio.wait_for(owner.wait_shutdown(), 5)
        assert owner.shutdown_status()["state"] == "DRAINED"
        assert native.native.stopped and native.opens == 1

    client.portal.call(scenario)


def test_shutdown_retries_final_publication_without_reopening_native(connected_local, monkeypatch):
    setup, binding, native = connected_local
    owner = setup[1].state.embedded_dispatch_owner
    opened = admit(setup, binding, 'publication-shutdown-open', 'runtime.start', new_session=True)
    wait_receipt(setup, opened)
    restored = threading.Event()
    original = owner.events.recover

    async def unavailable(**kwargs):
        if owner._stopping.is_set() and not restored.is_set():
            raise OSError('Final publication storage unavailable')
        return await original(**kwargs)

    monkeypatch.setattr(owner.events, 'recover', unavailable)

    async def scenario():
        try:
            await owner.request_shutdown(timeout_seconds=.05)
            with pytest.raises(OSError, match='Final publication storage unavailable'):
                await asyncio.wait_for(owner.close(), 10)
            assert native.native.stopped
            assert owner.shutdown_status()['state'] == 'DRAINING_PENDING'
            assert owner.host._runtime_tasks
            receipt = await owner.host.historical_receipt(session_id=opened['session_id'],
                key=OperationKey(opened['scope']['server_id'], opened['scope']['executor_id'], opened['operation_id']))
            assert receipt is not None and receipt.stage == 'SUBMITTED'
        finally:
            restored.set()
            await asyncio.wait_for(owner.wait_shutdown(), 10)
        assert owner.shutdown_status()['state'] == 'DRAINED'
        assert not owner.host._runtime_tasks and native.opens == 1

    setup[2].portal.call(scenario)
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT lifecycle_state FROM execution_sessions WHERE session_id=?',
                                      (opened['session_id'],)).fetchone()[0] == 'CLOSED'


def test_lifespan_retains_embedded_owner_until_pending_recovery(tmp_path, monkeypatch):
    from contextlib import contextmanager
    import time
    from test_embedded_dispatch import connect_local

    released = threading.Event()
    observations = []
    errors = []
    watcher = None
    with contextmanager(local_setup.__wrapped__)(tmp_path, monkeypatch, None) as setup:
        setup, binding, native = connect_local(setup)
        deps, app, client, *_ = setup
        owner = app.state.embedded_dispatch_owner
        opened = admit(setup, binding, "lifespan-pending", "runtime.start", new_session=True)
        wait_receipt(setup, opened)
        original_close = native.native.close
        original_request = owner.request_shutdown

        async def held_close():
            if not released.is_set():
                return "unknown"
            return await original_close()

        async def short_request(**kwargs):
            return await original_request(timeout_seconds=.05)

        monkeypatch.setattr(native.native, "close", held_close)
        monkeypatch.setattr(owner, "request_shutdown", short_request)

        def observe_and_restore():
            try:
                deadline = time.monotonic() + 5
                while getattr(app.state, "embedded_shutdown_report", None) is None:
                    assert time.monotonic() < deadline
                    time.sleep(.01)
                report = app.state.embedded_shutdown_report
                assert report["state"] == "DRAINING_PENDING"
                assert deps.runtime_admission_fence.closed
                assert len(owner.host._runtime_tasks) == 1
                with deps.connection_factory.unit_of_work(write=False) as uow:
                    assert owner.inventory.dispatcher.repo.owns(uow,
                        owner_id=owner.inventory.dispatcher.owner_id,
                        epoch=owner.inventory.dispatcher.epoch, now=deps.clock.now_iso())
                observations.append(report["state"])
            except BaseException as error:
                errors.append(error)
            finally:
                released.set()

        watcher = threading.Thread(target=observe_and_restore)
        watcher.start()
    watcher.join(5)
    assert not watcher.is_alive() and not errors, errors
    assert observations == ["DRAINING_PENDING"]
    assert app.state.embedded_shutdown_report["state"] == "DRAINED"
    assert native.native.stopped and native.opens == 1
    assert not owner.host._runtime_tasks

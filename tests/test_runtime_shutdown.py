"""Production lifespan must retain the owner and journal through native drain."""
import asyncio
import threading
import time

import pytest

from okto_nexus.adapters.inbound.http.app import build_app
from okto_nexus.adapters.inbound.mcp.server import bootstrap
from okto_nexus.adapters.outbound.sqlite.runtime_outbox_repo import SqliteRuntimeOutboxRepo
from okto_nexus.application.runtime_shutdown import shutdown_runtime
from okto_nexus.domain.base import iso_plus
from okto_nexus.errors import OktoNexusError
from test_pr34_remediation import runtime as runtime_fixture, open_rest

runtime = runtime_fixture


def test_lifespan_does_not_release_owner_before_runtime_drain(runtime, monkeypatch):
    deps = runtime[0]
    assert open_rest(runtime).status_code == 200
    dispatcher, supervisor = deps.runtime_dispatcher, deps.harness_supervisor
    release = dispatcher.repo.release_owner
    observations = []

    def observed_release(*args, **kwargs):
        observations.append(len(supervisor.list_live()))
        return release(*args, **kwargs)

    monkeypatch.setattr(dispatcher.repo, "release_owner", observed_release)

    async def shutdown_through_lifespan():
        app = build_app(deps)
        async with app.router.lifespan_context(app):
            pass

    asyncio.run(shutdown_through_lifespan())
    assert observations and observations[0] == 0, "runtime owner released before session drain"


def test_shutdown_deadline_retains_owner_and_journal_for_late_activity(runtime, monkeypatch):
    deps, _, _, peers, _, _ = runtime
    response = open_rest(runtime)
    assert response.status_code == 200
    dispatcher, supervisor = deps.runtime_dispatcher, deps.harness_supervisor
    peer = peers[0]
    entered, release = threading.Event(), threading.Event()
    original_send = peer.send

    def delayed_end(session, command):
        if command.verb == "end":
            entered.set()
            assert release.wait(5)
        return original_send(session, command)

    monkeypatch.setattr(peer, "send", delayed_end)
    supervisor._close_timeout_s = .05
    try:
        began = time.monotonic()
        result = shutdown_runtime(dispatcher, supervisor, timeout=.1)
        assert time.monotonic() - began < 1
        assert entered.is_set()
        assert result == {"state": "pending", "owner_released": False}
        assert not supervisor.drained(), "timed-out helper still owns capacity"
        supervisor.event_ingress.journal.check_admission()  # Still capture-capable.
        with deps.connection_factory.unit_of_work() as uow:
            now = deps.clock.now_iso()
            assert dispatcher.repo.owns(uow, owner_id=dispatcher.owner_id, epoch=dispatcher.epoch, now=now)
            assert dispatcher.repo.acquire_owner(uow, owner_id="fixture-contender", now=now,
                                                 lease_expires_at=iso_plus(now, 40)) is None
        with pytest.raises(OktoNexusError, match="shutting down"):
            supervisor.open(owning_agent_id="worker", endpoint_id="other")
        with pytest.raises(OktoNexusError, match="shutting down"):
            supervisor.send(peer.session.session_id, "send_turn", {"text": "never delivered"})
        assert len(supervisor._shutdown_threads) == 1
    finally:
        release.set()
        dispatcher.wake()
    assert dispatcher._shutdown_finished.wait(3)
    assert supervisor.drained()
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert not dispatcher.repo.owns(uow, owner_id=dispatcher.owner_id, epoch=dispatcher.epoch,
                                       now=deps.clock.now_iso())


def test_open_finishing_after_shutdown_cannot_leave_a_live_session(runtime, monkeypatch):
    deps = runtime[0]
    supervisor, dispatcher = deps.harness_supervisor, deps.runtime_dispatcher
    original_start = supervisor._bounded_start
    entered, release = threading.Event(), threading.Event()
    results = []

    def pause_start(*args, **kwargs):
        result = original_start(*args, **kwargs)
        entered.set()
        assert release.wait(5)
        return result

    monkeypatch.setattr(supervisor, "_bounded_start", pause_start)
    opener = threading.Thread(target=lambda: results.append(open_rest(runtime)), daemon=True)
    opener.start()
    try:
        assert entered.wait(3)
        assert shutdown_runtime(dispatcher, supervisor, timeout=.05)["state"] == "pending"
        assert not supervisor.drained()
    finally:
        release.set()
        opener.join(5)
    assert not opener.is_alive()
    assert results[0].status_code >= 400
    assert dispatcher._shutdown_finished.wait(3)
    assert supervisor.list_live() == []


def test_lifespan_refuses_startup_when_another_owner_holds_store(tmp_path):
    deps = bootstrap({}, ["--home", str(tmp_path / "home")])
    deps.config.feature_harness_integrations = True
    repo = SqliteRuntimeOutboxRepo()
    now = deps.clock.now_iso()
    with deps.connection_factory.unit_of_work() as uow:
        epoch = repo.acquire_owner(uow, owner_id="fixture-first", now=now,
                                   lease_expires_at=iso_plus(now, 40))

    async def try_start():
        app = build_app(deps)
        async with app.router.lifespan_context(app):
            pytest.fail("contending owner exposed a serving app")

    with pytest.raises(RuntimeError, match="Another runtime owner"):
        asyncio.run(try_start())
    assert deps.runtime_dispatcher.epoch is None
    assert deps.harness_supervisor.list_live() == []
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert repo.owns(uow, owner_id="fixture-first", epoch=epoch, now=deps.clock.now_iso())

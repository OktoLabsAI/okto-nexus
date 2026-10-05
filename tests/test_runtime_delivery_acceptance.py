"""Canonical message rollback, independent admission and dropped-wake recovery."""
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from okto_nexus.adapters.outbound.sqlite.runtime_outbox_repo import SqliteRuntimeOutboxRepo
from okto_nexus.application.messages import MessageService
from test_pr34_remediation import runtime as runtime_fixture, open_rest, send_message, tool
from test_runtime_outbox import wait_status

runtime = runtime_fixture
TABLES = ("messages", "message_deliveries", "delivery_outbox", "events",
          "runtime_causal_roots", "runtime_message_causality")


def counts(uow):
    return {table: uow.connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            for table in TABLES}


@pytest.mark.parametrize("cut", ["message", "delivery", "outbox", "event"])
def test_each_canonical_write_rolls_back_without_orphan_intent(runtime, monkeypatch, cut):
    deps, client, root, peers, _, caller = runtime
    assert open_rest(runtime).status_code == 200
    with deps.connection_factory.unit_of_work(write=False) as uow:
        before = counts(uow)
    targets = {
        "message": (deps.repos.messages, "create", "messages"),
        "delivery": (deps.repos.deliveries, "create", "message_deliveries"),
        "outbox": (SqliteRuntimeOutboxRepo, "enqueue", "delivery_outbox"),
        "event": (deps.event_emitter, "emit", "events"),
    }
    target, method, table = targets[cut]
    original = getattr(target, method)
    reached = []

    def fail_after_real_write(*args, **kwargs):
        result = original(*args, **kwargs)
        if cut == "event" and kwargs.get("type") != "message.created":
            return result
        uow = args[1] if cut == "outbox" else args[0]
        current = counts(uow)
        assert current[table] == before[table] + 1
        reached.append(current)
        raise OSError("Disposable canonical write failure")

    monkeypatch.setattr(target, method, fail_after_real_write)
    result = tool(client, caller, "message_create", {
        "project_root": root, "from_agent_id": "caller", "subject": "atomic fixture",
        "body": "must roll back", "target": {"strategy": "direct", "agent_id": "worker"}})
    assert not result["ok"], result
    assert len(reached) == 1, "failure must follow a real canonical write"
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert counts(uow) == before
        assert not uow.connection.execute("PRAGMA foreign_key_check").fetchall()
    assert peers[0].sent == []
    # Prove the same production composition remains usable after rollback.
    monkeypatch.setattr(target, method, original)
    admitted = send_message(runtime, body="fresh request after rollback")
    wait_status(runtime, admitted["runtime_operations"][0], "SENT_UNCONFIRMED")
    assert len(peers[0].sent) == 1
    with deps.connection_factory.unit_of_work(write=False) as uow:
        after = counts(uow)
        for table in ("messages", "message_deliveries", "delivery_outbox"):
            assert after[table] == before[table] + 1


def test_message_admission_commits_while_native_write_is_blocked(runtime, monkeypatch):
    deps, _, _, peers, _, _ = runtime
    assert open_rest(runtime).status_code == 200
    entered, release = threading.Event(), threading.Event()
    original = peers[0].send

    def blocked(*args, **kwargs):
        entered.set()
        assert release.wait(10)
        return original(*args, **kwargs)

    monkeypatch.setattr(peers[0], "send", blocked)
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(send_message, runtime)
            assert entered.wait(5)
            admitted = future.result(timeout=1)
            operation = admitted["runtime_operations"][0]
            assert peers[0].sent == []
            with deps.connection_factory.unit_of_work(write=False) as uow:
                row = deps.runtime_dispatcher.repo.get(uow, operation)
                assert row["status"] == "SENDING" and row["ack_level"] == "NONE"
                assert uow.connection.execute("SELECT count(*) FROM messages").fetchone()[0] == 1
                assert uow.connection.execute("SELECT consumer_kind FROM message_deliveries").fetchone()[0] == "push"
    finally:
        release.set()
    wait_status(runtime, operation, "SENT_UNCONFIRMED")
    assert len(peers[0].sent) == 1


def test_recovery_interval_configuration_reaches_production_dispatcher(tmp_path):
    from okto_nexus.config import load_config
    from okto_nexus.adapters.inbound.mcp.server import bootstrap
    from okto_nexus.adapters.inbound.mcp.tools.harness import build_dispatcher
    from okto_nexus.errors import OktoNexusError

    variable = "OKTO_NEXUS_RUNTIME_RECOVERY_INTERVAL_SECONDS"
    flag = "--runtime-recovery-interval-seconds"
    assert load_config({}).runtime_recovery_interval_seconds == 30
    assert load_config({variable: "2"}).runtime_recovery_interval_seconds == 2
    deps = bootstrap({variable: "2"}, ["--home", str(tmp_path), flag, "1"])
    dispatcher = build_dispatcher(deps)
    assert dispatcher.recovery_seconds == 1
    assert dispatcher.epoch is None and not dispatcher._threads
    for value in ["0", "-1", "86401", "nan", "1.5", "true"]:
        with pytest.raises(OktoNexusError, match="CONFIG_ERROR"):
            load_config({variable: value})
        with pytest.raises(OktoNexusError, match="CONFIG_ERROR"):
            load_config({}, [flag, value])


def test_dropped_post_commit_wake_recovers_in_same_live_owner(runtime, monkeypatch):
    import okto_nexus.adapters.inbound.mcp.tools.messages as message_tools

    deps, _, _, peers, _, _ = runtime
    assert open_rest(runtime).status_code == 200
    owner = deps.runtime_dispatcher
    identity = (owner.owner_id, owner.epoch)
    scanned, release = threading.Event(), threading.Event()
    original_scan, original_wait = owner.scan_once, owner._wait_for_wake
    first = True
    waits = []
    owner.recovery_seconds = 1

    def paused_scan():
        nonlocal first
        original_scan()
        if first:
            first = False
            scanned.set()
            assert release.wait(5)

    def observed_wait(observed, timeout=10):
        generation = original_wait(observed, timeout)
        waits.append((observed, generation))
        return generation

    monkeypatch.setattr(owner, "scan_once", paused_scan)
    monkeypatch.setattr(owner, "_wait_for_wake", observed_wait)
    monkeypatch.setattr(message_tools, "wake_runtime", lambda _: None)
    monkeypatch.setattr(MessageService, "_maybe_notify_inbox_subscribers", lambda *args, **kwargs: None)
    try:
        owner.wake()
        assert scanned.wait(5)
        generation = owner._wake_generation
        admitted = send_message(runtime, body="durable despite dropped signal")
        operation = admitted["runtime_operations"][0]
        with deps.connection_factory.unit_of_work(write=False) as uow:
            assert owner.repo.get(uow, operation)["status"] == "PENDING"
        assert peers[0].sent == [] and owner._wake_generation == generation
        waits.clear()
        started = time.monotonic()
        release.set()
        # The one-second recovery interval must not inherit the ten-second
        # heartbeat wait. Allow scheduling/SQLite overhead, without any test
        # wake/scan after commit or restart of the live owner.
        deadline = started + 3
        while not peers[0].sent and time.monotonic() < deadline:
            time.sleep(.02)
        assert len(peers[0].sent) == 1
        assert waits and waits[0] == (generation, generation), waits
        assert (owner.owner_id, owner.epoch) == identity and owner._coordinator.is_alive()
        wait_status(runtime, operation, "SENT_UNCONFIRMED")
        with deps.connection_factory.unit_of_work(write=False) as uow:
            assert uow.connection.execute("SELECT count(*) FROM message_deliveries").fetchone()[0] == 1
            assert uow.connection.execute("SELECT count(*) FROM delivery_outbox").fetchone()[0] == 1
    finally:
        release.set()


def test_unavailable_store_keeps_bounded_recovery_delay(runtime, monkeypatch):
    owner = runtime[0].runtime_dispatcher
    owner.recovery_seconds = 1
    failed, waiting, release = threading.Event(), threading.Event(), threading.Event()
    heartbeat, wait = owner.repo.heartbeat_owner, owner._wait_for_wake
    delays = []

    def unavailable(*args, **kwargs):
        failed.set()
        raise OSError("Disposable unavailable writer")

    def observe_delay(observed, timeout=10):
        if failed.is_set():
            delays.append(timeout)
            waiting.set()
            assert release.wait(5)
        return wait(observed, timeout)

    monkeypatch.setattr(owner.repo, "heartbeat_owner", unavailable)
    monkeypatch.setattr(owner, "_wait_for_wake", observe_delay)
    try:
        owner.wake()
        assert waiting.wait(5)
        assert len(delays) == 1 and 0 < delays[0] <= 1
    finally:
        monkeypatch.setattr(owner.repo, "heartbeat_owner", heartbeat)
        release.set()
        owner.wake()

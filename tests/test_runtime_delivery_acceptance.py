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

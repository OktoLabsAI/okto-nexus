"""Shared production supervisor, real Codex transport and scripted native peer."""
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor
import pytest

from legacy_native_fixture.codex import CodexAppServerConnector
from test_harness_codex_connector import _FAKE_SERVER_SOURCE
from test_pr34_remediation import runtime as runtime_fixture

from test_runtime_commands import wait_close_result

runtime = runtime_fixture










def test_connection_leases_protect_live_and_starting_siblings():
    import pytest
    from okto_nexus.application.runtime_lifecycle import RuntimeConnectionLifecycle
    connection = RuntimeConnectionLifecycle()
    first = connection.new_scope(multiplexing=True)
    second = connection.new_scope(multiplexing=True)
    stopped = []
    first.register(lambda: stopped.append("owned-process"))
    assert not first.claim_exclusive_teardown()
    first.cancel()
    assert stopped == []
    third = connection.new_scope(multiplexing=True)
    second.cancel()
    assert stopped == []
    assert third.claim_exclusive_teardown()
    with pytest.raises(RuntimeError):
        connection.new_scope(multiplexing=True)
    third.cancel()
    assert stopped == ["owned-process"]
    with pytest.raises(RuntimeError):
        first.register(lambda: stopped.append("late-process"))
    assert stopped == ["owned-process", "late-process"]

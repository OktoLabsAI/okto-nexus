"""Pure fixture seam checks; no Server, process, provider or personal auth."""

import asyncio
import inspect
from pathlib import Path
import sys
import time
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))
sys.path.insert(0, str(Path(__file__).parents[1] / "execution_r4"))
from test_canonical_native_protocol_regressions import install_native  # noqa:E402
from test_harness_codex_connector import _FAKE_SERVER_SOURCE  # noqa:E402


def connection(tmp_path):
    owner = SimpleNamespace(native_factory=None)
    app = SimpleNamespace(state=SimpleNamespace(embedded_dispatch_owner=owner))
    return ((None, app, None, None, None, None, tmp_path), None, None), owner


def test_fixture_declares_and_propagates_exact_launch_guard_birth_and_container_hooks(
    tmp_path, monkeypatch
):
    from nexus_connector_core.native.adapters import codex
    from nexus_connector_core.native import runtime_bridge

    connected, owner = connection(tmp_path)
    calls = []

    class Peer:
        def __init__(self, **kwargs):
            self.arguments = kwargs

        def start(self, *, owning_agent_id):
            calls.append(("start", owning_agent_id, self._process_container_id))
            self._launch_guard("fixture_before_handshake")
            self._process_birth_observer("synthetic-birth-no-PID")
            calls.append(("after_birth",))
            return "synthetic-native"

        def close(self):
            calls.append(("close",))
            return "already_closed"

    monkeypatch.setattr(codex, "CodexAppServerConnector", Peer)
    monkeypatch.setattr(
        runtime_bridge,
        "CopiedAdapterSession",
        lambda peer, native, **kw: (peer, native, kw),
    )
    peers, _ = install_native(connected, _FAKE_SERVER_SOURCE)
    assert set(inspect.signature(owner.native_factory.open).parameters) >= {
        "opening_guard",
        "process_birth_recorder",
        "process_launch",
    }
    context = SimpleNamespace(
        server_id="server",
        executor_id="executor",
        agent_id="agent",
        lease_deadline_monotonic=time.monotonic() + 60,
    )
    guard = SimpleNamespace(closed=False, context_probe=lambda: context)

    class Launch:
        identity = SimpleNamespace(
            key=SimpleNamespace(
                server_id="server", executor_id="executor", session_id="session"
            ),
            container_id="synthetic-container",
        )

        async def produce(self, *, validate_authority, start):
            calls.append(("validate",))
            validate_authority()
            value = await asyncio.to_thread(start)
            calls.append(("produced",))
            return value

    async def recorded(evidence):
        calls.append(("birth_persisted", evidence))

    result = asyncio.run(
        owner.native_factory.open(
            None,
            "session",
            context,
            stream_epoch="epoch",
            opening_guard=guard,
            process_birth_recorder=recorded,
            process_launch=Launch(),
        )
    )
    assert result[1] == "synthetic-native"
    assert calls == [
        ("validate",),
        ("start", "agent", "synthetic-container"),
        ("birth_persisted", "synthetic-birth-no-PID"),
        ("after_birth",),
        ("produced",),
    ]
    assert len(peers) == 1
    source = peers[0].arguments["command"][3]
    assert source.count('elif method == "account/read":') == 1
    assert '"requiresOpenaiAuth":False,"account":None' in source


def test_fixture_closed_opening_guard_refuses_before_fake_start(tmp_path, monkeypatch):
    from nexus_connector_core import CoreError
    from nexus_connector_core.native.adapters import codex

    connected, owner = connection(tmp_path)
    calls = []

    class Peer:
        def __init__(self, **kwargs):
            pass

        def start(self, **kwargs):
            pytest.fail("closed guard must prevent any start")

        def close(self):
            calls.append("closed")
            return "already_closed"

    monkeypatch.setattr(codex, "CodexAppServerConnector", Peer)
    install_native(connected, _FAKE_SERVER_SOURCE)
    context = SimpleNamespace(lease_deadline_monotonic=time.monotonic() + 60)
    with pytest.raises(CoreError) as error:
        asyncio.run(
            owner.native_factory.open(
                None,
                "session",
                context,
                stream_epoch="epoch",
                opening_guard=SimpleNamespace(closed=True),
            )
        )
    assert error.value.code == "RUNTIME_DRAINING" and calls == ["closed"]


def test_fixture_preserves_explicit_negative_account_handshake_source(
    tmp_path, monkeypatch
):
    from nexus_connector_core.native.adapters import codex

    connected, _ = connection(tmp_path)
    marker = '        elif method == "thread/start":\n'
    source = _FAKE_SERVER_SOURCE.replace(
        marker,
        '        elif method == "account/read":\n            raise RuntimeError("explicit negative fixture")\n'
        + marker,
    )
    calls = []

    class Peer:
        def __init__(self, **kwargs):
            calls.append(kwargs)

        def start(self, **kwargs):
            raise ValueError("capture only, no native start")

        def close(self):
            return "already_closed"

    monkeypatch.setattr(codex, "CodexAppServerConnector", Peer)
    install_native(connected, source)
    context = SimpleNamespace(
        agent_id="agent", lease_deadline_monotonic=time.monotonic() + 60
    )
    with pytest.raises(ValueError, match="capture only"):
        asyncio.run(
            connected[0][1].state.embedded_dispatch_owner.native_factory.open(
                None, "session", context, stream_epoch="epoch"
            )
        )
    assert calls[0]["command"][3] == source

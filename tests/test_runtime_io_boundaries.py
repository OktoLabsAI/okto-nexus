"""Observed process, secret, transport and fixture-model IO outside write UoWs."""
import socket
import threading
from collections import Counter
from types import SimpleNamespace

from okto_nexus.adapters.inbound.mcp.tools import harness
from okto_nexus.adapters.outbound.harness import codex
from okto_nexus.adapters.outbound.embedding import StubEmbeddingProvider
from okto_nexus.adapters.outbound.sqlite.connection import SqliteUnitOfWork
from test_pr34_remediation import runtime as runtime_fixture
from test_runtime_commands import codex_session, wait_operation

runtime = runtime_fixture


def test_owned_spawn_secret_transport_and_fixture_model_network_are_outside_write_uow(runtime, monkeypatch):
    deps, client, _, _, operator, _ = runtime
    active = threading.local()
    observations, violations = Counter(), []
    lock = threading.Lock()
    enter, leave = SqliteUnitOfWork.__enter__, SqliteUnitOfWork.__exit__

    def checked_enter(uow):
        active.depth = getattr(active, "depth", 0) + int(uow._write)
        try:
            return enter(uow)
        except BaseException:
            active.depth -= int(uow._write)
            raise

    def checked_exit(uow, *args):
        try:
            return leave(uow, *args)
        finally:
            active.depth -= int(uow._write)

    def observe(name):
        with lock:
            observations[name] += 1
            if getattr(active, "depth", 0):
                violations.append(name)
        assert not getattr(active, "depth", 0), name

    monkeypatch.setattr(SqliteUnitOfWork, "__enter__", checked_enter)
    monkeypatch.setattr(SqliteUnitOfWork, "__exit__", checked_exit)
    resolver, spawn, write = harness.profile_environment, codex.spawn_owned_process, codex._CodexTransport._write

    def resolve(*args, **kwargs):
        observe("secret_resolver")
        result = resolver(*args, **kwargs)
        assert result["FIXTURE_CREDENTIAL"] == "disposable-uow-secret"
        return result

    def spawn_checked(*args, **kwargs):
        observe("owned_spawn")
        return spawn(*args, **kwargs)

    def write_checked(*args, **kwargs):
        observe("native_transport")
        return write(*args, **kwargs)

    monkeypatch.setattr(harness, "profile_environment", resolve)
    monkeypatch.setattr(codex, "spawn_owned_process", spawn_checked)
    monkeypatch.setattr(codex._CodexTransport, "_write", write_checked)
    monkeypatch.setenv("FIXTURE_UOW_SECRET", "disposable-uow-secret")
    response = client.patch("/api/v1/harness/profiles/profile-codex", headers={"x-api-key": operator},
        json={"expected_revision": 1, "secret_refs": {"FIXTURE_CREDENTIAL": "env:FIXTURE_UOW_SECRET"}})
    assert response.status_code == 200, response.text
    sid = codex_session(runtime)
    # Explicit synthetic model with a real, exclusively loopback TCP write.
    # No provider configuration, model download, account or external address.
    class FixtureModel(StubEmbeddingProvider):
        def encode(self, text):
            observe("model_encode")
            # Each callback owns its sockets; concurrent receipt embeddings or
            # teardown cannot race a test-level connection's lifetime.
            with socket.socket() as listener:
                listener.bind(("127.0.0.1", 0))
                listener.listen(1)
                listener.settimeout(5)
                with socket.create_connection(listener.getsockname(), timeout=5) as sender:
                    receiver, _ = listener.accept()
                    with receiver:
                        receiver.settimeout(5)
                        observe("model_network_write")
                        sender.sendall(b"fixture")
                        received = b""
                        while len(received) < 7:
                            chunk = receiver.recv(7 - len(received))
                            assert chunk, "fixture connection closed before complete payload"
                            received += chunk
                        assert received == b"fixture"
            return super().encode(text)

    monkeypatch.setattr(deps, "embedding", SimpleNamespace(provider=FixtureModel(), search_enabled=False))
    with deps.connection_factory.unit_of_work(write=False) as uow:
        workspace = uow.connection.execute("SELECT workspace_id FROM harness_sessions WHERE session_id=?", (sid,)).fetchone()[0]
    response = client.post("/api/v1/steering/messages", headers={"x-api-key": operator}, json={
        "workspace": workspace, "to_agent_id": "worker", "body": "fixture IO boundary", "subject": "isolated model"})
    assert response.status_code == 200, response.text
    admitted = response.json()["data"]
    op = admitted["runtime_operations"][0]
    completed = wait_operation(runtime, op, lambda row: row["result_durable"])
    assert completed["result"], completed
    assert not violations, violations  # Also catches errors swallowed by best-effort paths.
    for name in ("secret_resolver", "owned_spawn", "native_transport", "model_encode", "model_network_write"):
        assert observations[name] > 0, (name, observations)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT 1 FROM message_embeddings WHERE message_id=?", (admitted["message_id"],)).fetchone()

"""Observe actual provider, native pipe and embedding I/O outside write UoWs."""
import asyncio
import socket
import sys
import threading
from collections import Counter
from types import SimpleNamespace

from nexus_connector_core.native.adapters import codex
from nexus_connector_core.native.runtime_bridge import CopiedAdapterSession
from okto_nexus.adapters.outbound.embedding import StubEmbeddingProvider
from okto_nexus.adapters.outbound.sqlite.connection import SqliteUnitOfWork
from okto_nexus.application.execution_local_launch import ProviderSecretResolver
from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, connect_local, qualified_contract, admit, wait_receipt
from test_harness_codex_connector import _FAKE_SERVER_SOURCE
from test_canonical_result_publication import current_turn, wait_result, send_message, workspace


def test_provider_spawn_native_and_embedding_io_are_outside_write_transactions(local_setup, monkeypatch):
    setup, binding, _ = connect_local(local_setup, secret_bindings={'OPENAI_API_KEY': 'provider:FIXTURE_UOW_SECRET'})
    deps, app, client, headers, *_, root = setup
    monkeypatch.setenv('FIXTURE_UOW_SECRET', 'disposable-uow-secret')
    active = threading.local()
    observations, violations = Counter(), []
    lock = threading.Lock()
    enter, leave = SqliteUnitOfWork.__enter__, SqliteUnitOfWork.__exit__

    def checked_enter(uow):
        active.depth = getattr(active, 'depth', 0) + int(uow._write)
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
            if getattr(active, 'depth', 0):
                violations.append(name)
        assert not getattr(active, 'depth', 0), name

    monkeypatch.setattr(SqliteUnitOfWork, '__enter__', checked_enter)
    monkeypatch.setattr(SqliteUnitOfWork, '__exit__', checked_exit)
    resolver, spawn, write = ProviderSecretResolver.resolve, codex.spawn_owned_process, codex._CodexTransport._write

    async def resolve(*args, **kwargs):
        observe('secret_resolver')
        value = await resolver(*args, **kwargs)
        assert value == 'disposable-uow-secret'
        return value

    def spawn_checked(*args, **kwargs):
        observe('owned_spawn')
        return spawn(*args, **kwargs)

    def write_checked(*args, **kwargs):
        observe('native_transport')
        return write(*args, **kwargs)

    monkeypatch.setattr(ProviderSecretResolver, 'resolve', resolve)
    monkeypatch.setattr(codex, 'spawn_owned_process', spawn_checked)
    monkeypatch.setattr(codex._CodexTransport, '_write', write_checked)
    owner = app.state.embedded_dispatch_owner
    peers = []

    class Factory:
        async def open(self, prepared, session_id, context, *, stream_epoch):
            environment = await owner.sessions[session_id]['executor'].environment(prepared)
            assert environment['OPENAI_API_KEY'] == 'disposable-uow-secret'
            peer = codex.CodexAppServerConnector(command=[sys._base_executable, '-u', '-c', _FAKE_SERVER_SOURCE],
                                                cwd=str(root), env=environment)
            peers.append(peer)
            native = await asyncio.to_thread(peer.start, owning_agent_id=context.agent_id)
            return CopiedAdapterSession(peer, native, session_id=session_id, stream_epoch=stream_epoch, context=context)

    owner.native_factory = Factory()
    opened = admit(setup, binding, 'io-open', 'runtime.start', new_session=True)
    wait_receipt(setup, opened)

    class FixtureModel(StubEmbeddingProvider):
        def encode(self, text):
            observe('model_encode')
            with socket.socket() as listener:
                listener.bind(('127.0.0.1', 0))
                listener.listen(1)
                listener.settimeout(5)
                with socket.create_connection(listener.getsockname(), timeout=5) as sender:
                    receiver, _ = listener.accept()
                    with receiver:
                        receiver.settimeout(5)
                        observe('model_network_write')
                        sender.sendall(b'fixture')
                        received = b''
                        while len(received) < 7:
                            chunk = receiver.recv(7 - len(received))
                            assert chunk
                            received += chunk
                        assert received == b'fixture'
            return super().encode(text)

    monkeypatch.setattr(deps, 'embedding', SimpleNamespace(provider=FixtureModel(), search_enabled=False))
    response = client.post('/api/v1/steering/messages', headers=headers['operator'], json=dict(
        workspace=workspace(setup), to_agent_id='subject', body='Fixture IO boundary', subject='Isolated model'))
    assert response.status_code == 200, response.text
    sent = response.json()
    assert sent['ok'], sent
    turn = current_turn(setup)
    result = wait_result(setup, 'PUBLISHED')
    assert result['output_text']
    assert not violations, violations
    for name in ('secret_resolver', 'owned_spawn', 'native_transport', 'model_encode', 'model_network_write'):
        assert observations[name] > 0, (name, observations)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT 1 FROM message_embeddings WHERE message_id=?',
                                      (sent['data']['message_id'],)).fetchone()
    wait_receipt(setup, admit(setup, binding, 'io-close', 'runtime.close', session_id=turn['session_id']), stages=('SUCCEEDED',))
    assert peers[0]._transport._proc.wait(timeout=5) is not None

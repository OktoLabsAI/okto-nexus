"""Actual serve ownership and committed inbox recovery across process death."""
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time

import httpx
import okto_nexus
import pytest

import runtime_serve_shutdown_fixture as fixture
from test_pr34_remediation import tool


def rows(server, sql, params=()):
    with closing(sqlite3.connect(server.home / 'nexus.db')) as connection:
        connection.row_factory = sqlite3.Row
        return [dict(r) for r in connection.execute(sql, params)]


def environment(server):
    env = {k: v for k, v in os.environ.items() if k.upper() in {'PATH', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP'}}
    env.update(HOME=str(server.home), USERPROFILE=str(server.home),
        PYTHONPATH=os.pathsep.join((str(Path(okto_nexus.__file__).resolve().parent.parent),
                                 str(Path(fixture.__file__).resolve().parent))),
        PYTHONIOENCODING='utf-8', OKTO_NEXUS_NO_BANNER='1')
    return env


def completing_peer(monkeypatch):
    peer = fixture.PEER.replace('    if msg.get("type"):', '''    if msg.get("type")=="prompt":
        with open(sys.argv[1]+".writes", "a", encoding="utf-8") as log:
            log.write(json.dumps(msg)+"\\n")
        def emit(value): print(json.dumps(value),flush=True)
        emit({"type":"response","command":"prompt","success":True,"data":{}})
        emit({"type":"agent_start"})
        emit({"type":"turn_start"})
        emit({"type":"message_start","role":"assistant"})
        emit({"type":"message_update","assistantMessageEvent":{"type":"text_delta","delta":"canonical owner completed"}})
        emit({"type":"message_end","role":"assistant","stopReason":"stop"})
        emit({"type":"turn_end"})
        emit({"type":"agent_end"})
        emit({"type":"agent_settled"})
        continue
    if msg.get("type"):''')
    assert peer != fixture.PEER
    monkeypatch.setattr(fixture, 'PEER', peer)


def send(server):
    return tool(server.client, server.operator, 'message_create', dict(project_root=str(server.project),
        from_agent_id='operator', target=dict(strategy='direct', agent_id='shutdown-fixture'),
        subject='Canonical ownership', body='One surviving owner'))


def open_for_messages(server, *, start_native=True):
    from okto_nexus.domain.ids import resolve_workspace_id
    workspace = resolve_workspace_id(str(server.project))
    with server.deps.connection_factory.unit_of_work() as uow:
        server.deps.repos.workspaces.upsert(uow, workspace_id=workspace,
            root_realpath=str(server.project), last_seen_at=server.deps.clock.now_iso())
    return server.open(actions=('open', 'send', 'close'), workspace_id=workspace, start_native=start_native)


def completed(server):
    deadline = time.monotonic() + 20
    while True:
        result = rows(server, 'SELECT * FROM runtime_results')
        if result:
            assert len(result) == 1 and result[0]['output_text'] == 'canonical owner completed', result
            return result[0]
        assert server.process.poll() is None, server.log_path.read_text(encoding='utf-8')
        assert time.monotonic() < deadline, (rows(server, 'SELECT * FROM delivery_outbox'),
            server.log_path.read_text(encoding='utf-8')[-4000:])
        time.sleep(.05)


def writes(server):
    path = Path(str(server.marker) + '.writes')
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()] if path.exists() else []


def test_second_serve_process_cannot_take_live_owner_and_first_keeps_delivering(tmp_path, monkeypatch):
    completing_peer(monkeypatch)
    server = fixture.ServeFixture(tmp_path)
    try:
        before = rows(server, 'SELECT owner_id,epoch FROM runtime_dispatcher_owner')
        contender = subprocess.run(server.process.args, env=environment(server), cwd=server.project,
            input='stop\n', capture_output=True, text=True, timeout=30,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        assert contender.returncode != 0, (contender.stdout, contender.stderr)
        assert 'already running for this home' in contender.stderr + contender.stdout
        assert server.process.poll() is None
        assert rows(server, 'SELECT owner_id,epoch FROM runtime_dispatcher_owner') == before
        assert not server.marker.exists()
        open_for_messages(server)
        created = send(server)
        assert created['ok'], created
        result = completed(server)
        assert result['operation_id'] == created['data']['runtime_operations'][0]
        assert len(writes(server)) == 1
        assert rows(server, 'SELECT owner_id,epoch FROM runtime_dispatcher_owner') == before
        assert len(rows(server, 'SELECT * FROM delivery_outbox')) == 1
        assert rows(server, 'PRAGMA foreign_key_check') == []
        server.stop('clean')
    finally:
        server.close()


COMMIT_CUT = r'''
import os,json
from okto_nexus.application import execution_dispatch_pump
from okto_nexus.adapters.inbound.mcp.tools import messages
arm=Path(marker).with_name('cut-before-wake')
reserve_original=execution_dispatch_pump.reserve_execution_dispatch
def reserved(**kwargs):
    return None if arm.exists() else reserve_original(**kwargs)
execution_dispatch_pump.reserve_execution_dispatch=reserved
wake_original=messages.wake_runtime
def wake(deps):
    if arm.exists():
        with deps.connection_factory.unit_of_work(write=False) as uow:
            counts={table:uow.connection.execute('SELECT count(*) FROM '+table).fetchone()[0]
                for table in ('messages','message_deliveries','delivery_outbox')}
        assert counts==dict(messages=1,message_deliveries=1,delivery_outbox=1),counts
        Path(marker).with_name('committed-before-wake.json').write_text(json.dumps(counts))
        os._exit(76)
    return wake_original(deps)
messages.wake_runtime=wake
'''


@pytest.mark.parametrize('revoke_sender', [False, True])
def test_committed_message_survives_serve_death_before_wake_without_duplicate_effect(tmp_path, monkeypatch, revoke_sender):
    completing_peer(monkeypatch)
    monkeypatch.setattr(fixture, 'LAUNCHER', fixture.LAUNCHER.replace('Original=uvicorn.Server', COMMIT_CUT+'\nOriginal=uvicorn.Server'))
    server = fixture.ServeFixture(tmp_path)
    try:
        open_for_messages(server, start_native=False)
        before_owner = rows(server, 'SELECT owner_id,epoch FROM runtime_dispatcher_owner')[0]
        arm = tmp_path / 'cut-before-wake'
        arm.touch()
        try:
            response = send(server)
            assert response['ok'], response
        except (httpx.ReadError, httpx.RemoteProtocolError):
            pass
        assert server.process.wait(timeout=15) == 76, server.log_path.read_text(encoding='utf-8')
        for witness in server.witnesses:
            witness.assert_stopped()
        assert json.loads((tmp_path/'committed-before-wake.json').read_text(encoding='utf-8')) == dict(
            messages=1, message_deliveries=1, delivery_outbox=1)
        before = rows(server, 'SELECT * FROM delivery_outbox')[0]
        assert before['status'] == 'PENDING' and writes(server) == []
        if revoke_sender:
            with server.deps.connection_factory.unit_of_work() as uow:
                uow.connection.execute("UPDATE agents SET api_key_hash='revoked-before-recovery' WHERE agent_id='operator'")
        arm.unlink()
        args = server.process.args
        server.process.stdin.close()
        server.process = subprocess.Popen(args, env=environment(server), cwd=server.project,
            stdin=subprocess.PIPE, stdout=server.log, stderr=subprocess.STDOUT, text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        if revoke_sender:
            deadline = time.monotonic() + 20
            while True:
                refused = rows(server, 'SELECT status,reason FROM delivery_outbox')[0]
                if refused['status'] == 'REJECTED':
                    break
                assert time.monotonic() < deadline, refused
                time.sleep(.05)
            assert writes(server) == [] and not server.marker.exists()
            assert rows(server, 'SELECT * FROM runtime_results') == []
        else:
            result = completed(server)
            assert result['operation_id'] == before['operation_id']
        after_owner = rows(server, 'SELECT owner_id,epoch FROM runtime_dispatcher_owner')[0]
        assert after_owner['epoch'] > before_owner['epoch']
        assert after_owner['owner_id'] != before_owner['owner_id']
        assert len(rows(server, 'SELECT * FROM delivery_outbox')) == 1
        assert rows(server, 'SELECT count(*) AS n FROM message_deliveries WHERE message_id=?',
            (before['message_id'],)) == [{'n': 1}]
        assert len(writes(server)) == int(not revoke_sender) and rows(server, 'PRAGMA foreign_key_check') == []
        from test_runtime_relay_process_restart import PeerWitness
        if not revoke_sender:
            identities = json.loads(server.marker.read_text(encoding='utf-8'))
            for name in ('peer', 'child'):
                server.witnesses.append(PeerWitness(identities[name]))
        server.stop('clean')
    finally:
        server.close()

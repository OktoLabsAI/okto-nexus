"""Passive participant diagnosis and bounded real MCP negotiation without work."""
import asyncio
import json
import socket
import time

import httpx
import pytest
import uvicorn

import test_participant_init as fixtures
from okto_nexus.application.participant_diagnostics import ParticipantDiagnostics, inspect_participant
from okto_nexus.application.terminal_connection import ConnectionError
from okto_nexus.adapters.outbound import participant_client, participant_mcp, participant_files
from okto_nexus.adapters.outbound.service_manager.context import atomic_json
from okto_nexus.adapters.inbound.cli.main import main

local_setup = fixtures.local_setup
setup = fixtures.setup


def configured(s):
    saved = s.flow.review(s.selection, s.key)
    s.flow.apply(saved, s.key, saved['review_revision'])
    path = s.home / 'terminal/participants/external.json'
    participant_files.private_directory(path.parent)
    atomic_json(path, s.saves[-1])
    return path, s.saves[-1]


def checks(value):
    return {item['id']: item for item in value['checks']}


def test_passive_doctor_preserves_files_without_vault_http_process_or_recovery(setup, monkeypatch, capsys):
    s = setup
    path, saved = configured(s)
    original = path.read_bytes()
    target = s.root / '.mcp.json'
    content = target.read_bytes()
    def forbidden(*args, **kwargs):
        pytest.fail('Passive diagnostics must not read credentials, use HTTP or open a process')
    monkeypatch.setattr(s.vault, 'get', forbidden)
    monkeypatch.setattr(s.bridge, 'open', forbidden)
    import subprocess
    monkeypatch.setattr(subprocess, 'Popen', forbidden)
    assert main(['doctor', '--mode=participant', '--profile', 'external', '--home', str(s.home), '--json']) == 0
    result = json.loads(capsys.readouterr().out)
    rows = checks(result)
    assert rows['participant_profile']['status'] == rows['client_configuration']['status'] == 'PASS'
    assert rows['mcp_negotiation']['status'] == rows['credential_environment']['status'] == 'UNKNOWN'
    assert rows['participant_authentication']['status'] == 'UNKNOWN'
    assert not any(result['effects'].values())
    assert path.read_bytes() == original and target.read_bytes() == content
    assert fixtures.snapshot(s.deps) == s.before


def test_missing_profile_does_not_create_directories(tmp_path, capsys):
    absent = tmp_path / 'absent'
    assert main(['doctor', '--mode', 'participant', '--profile', 'missing', '--home', str(absent), '--json']) == 0
    assert checks(json.loads(capsys.readouterr().out))['participant_profile']['code'] == 'PROFILE_ABSENT'
    assert not absent.exists()


@pytest.mark.parametrize('environment', ['absent', 'invalid', 'valid'])
def test_environment_check_proves_only_current_doctor_context(setup, environment):
    s = setup
    _, saved = configured(s)
    name = saved['review']['configuration']['credential_environment']
    env = {} if environment == 'absent' else {name: 'malformed' if environment == 'invalid' else s.key}
    report = ParticipantDiagnostics('external')
    inspect_participant(report, s.home, saved, check_server=True, check_environment=True, environment=env)
    result = report.result()
    row = checks(result)['credential_environment']
    assert row['status'] == ('PASS' if environment == 'valid' else 'FAIL')
    if environment == 'valid':
        assert row['evidence']['context'] == 'doctor_process'
        assert checks(result)['participant_authentication']['status'] == 'PASS'
    assert checks(result)['client_reload']['status'] == checks(result)['mcp_negotiation']['status'] == 'UNKNOWN'
    assert s.key not in json.dumps(result)


def test_file_drift_does_not_hide_independent_authentication(setup):
    s = setup
    _, saved = configured(s)
    path = s.root / '.mcp.json'
    path.write_bytes(path.read_bytes().replace(b'nexus.example', b'edited.example'))
    before = path.read_bytes()
    report = ParticipantDiagnostics('external')
    inspect_participant(report, s.home, saved, check_server=True)
    rows = checks(report.result())
    assert rows['client_configuration']['status'] == 'FAIL'
    assert rows['participant_authentication']['status'] == rows['credential_store']['status'] == 'PASS'
    assert path.read_bytes() == before


def test_revoked_credential_is_not_repaired_or_used_for_mcp(setup, monkeypatch):
    s = setup
    _, saved = configured(s)
    with s.deps.connection_factory.unit_of_work() as uow:
        s.client.app.state.auth.issue_key(uow, agent_id='subject')
        after = uow.connection.execute("SELECT api_key_hash FROM agents WHERE agent_id='subject'").fetchone()[0]
    import okto_nexus.application.participant_diagnostics as diagnostic
    monkeypatch.setattr(diagnostic, 'inspect_mcp', lambda *args, **kwargs: pytest.fail('Refused credentials cannot negotiate MCP'))
    report = ParticipantDiagnostics('external')
    inspect_participant(report, s.home, saved, check_mcp=True)
    rows = checks(report.result())
    assert rows['server_reachability']['status'] == 'PASS'
    assert rows['participant_authentication']['status'] == 'FAIL'
    assert rows['mcp_negotiation']['status'] == 'UNKNOWN'
    assert s.vault.writes == 1
    with s.deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT api_key_hash FROM agents WHERE agent_id='subject'").fetchone()[0] == after


def test_actual_tcp_mcp_is_not_agent_participation_or_model_work(setup, monkeypatch, capsys):
    from urllib.request import build_opener
    s = setup
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    sock.listen(128)
    address = f'http://127.0.0.1:{sock.getsockname()[1]}'
    calls = []
    async def observe(scope, receive, send):
        if scope['type'] == 'http' and scope['path'].startswith('/mcp'):
            headers = dict(scope['headers'])
            calls.append(dict(method=scope['method'], path=scope['path'],
                authenticated=headers.get(b'authorization') == ('Bearer ' + s.key).encode()))
        await s.client.app(scope, receive, send)
    server = uvicorn.Server(uvicorn.Config(observe, lifespan='off', log_level='error'))
    async def serve():
        await server.serve(sockets=[sock])
    running = s.client.portal.start_task_soon(serve)
    try:
        until = time.monotonic() + 5
        while not server.started:
            assert time.monotonic() < until
            time.sleep(.01)
        monkeypatch.setattr(participant_client, 'build_opener', build_opener)
        s.selection['server'] = address
        path, _ = configured(s)
        original = path.read_bytes()
        with s.deps.connection_factory.unit_of_work(write=False) as uow:
            sessions = [tuple(row) for row in uow.connection.execute('SELECT * FROM sessions')]
        assert main(['doctor', '--mode', 'participant', '--profile', 'external', '--home', str(s.home),
            '--check-mcp', '--timeout', '15', '--json']) == 0
        result = json.loads(capsys.readouterr().out)
        rows = checks(result)
        assert rows['participant_authentication']['status'] == 'PASS'
        assert rows['mcp_negotiation']['status'] == rows['mcp_surface']['status'] == 'PASS', result
        assert rows['mcp_negotiation']['evidence']['tools_called'] == 0
        for level in ('client_reload', 'credential_environment', 'coordination_participation', 'handoff_test', 'work_result'):
            assert rows[level]['status'] == 'UNKNOWN'
        assert calls and all(item['authenticated'] for item in calls)
        assert {item['method'] for item in calls} <= {'GET', 'POST', 'DELETE'}
        assert path.read_bytes() == original and fixtures.snapshot(s.deps) == s.before
        with s.deps.connection_factory.unit_of_work(write=False) as uow:
            assert [tuple(row) for row in uow.connection.execute('SELECT * FROM sessions')] == sessions
        assert s.key not in json.dumps(result)
    finally:
        server.should_exit = True
        running.result(timeout=10)
        sock.close()


def mock_mcp(monkeypatch, mode):
    calls = []
    async def handle(request):
        assert request.url.host == 'nexus.example'
        if mode == 'timeout':
            await asyncio.sleep(2)
        if mode == 'redirect':
            return httpx.Response(307, headers={'Location': 'https://other.example/mcp'})
        if mode == 'oversized':
            return httpx.Response(200, content=b'x' * 1048577, headers={'Content-Type': 'application/json'})
        if mode == 'stream_limit':
            return httpx.Response(200, stream=httpx.ByteStream(b'x' * 1048577), headers={'Content-Type': 'application/json'})
        if mode == 'compression':
            return httpx.Response(200, headers={'Content-Encoding': 'gzip'}, stream=httpx.ByteStream(b'not-used'))
        if request.method == 'GET':
            return httpx.Response(405)
        if request.method == 'DELETE':
            return httpx.Response(204)
        value = json.loads(request.content)
        calls.append(value['method'])
        if value['method'] == 'notifications/initialized':
            return httpx.Response(202)
        if value['method'] == 'initialize':
            result = dict(protocolVersion=value['params']['protocolVersion'], capabilities={'tools': {}},
                serverInfo={'name': 'synthetic', 'version': '1'})
            if mode == 'malformed':
                result['protocolVersion'] = 'nxs_' + 'a' * 48
        else:
            result = dict(tools=[dict(name=name, inputSchema={'type': 'object', 'properties':
                {} if mode == 'schema' else {field: {} for field in participant_mcp._SURFACE[name]}}) for name in
                ('session_open', 'message_create', 'handoff_create') if mode != 'missing'])
            if mode == 'pages':
                result['nextCursor'] = 'again'
            if mode == 'tools':
                result['tools'] = [dict(name='tool_' + str(index), inputSchema={'type': 'object'}) for index in range(513)]
        return httpx.Response(200, json=dict(jsonrpc='2.0', id=value['id'], result=result))
    transport = participant_mcp._OriginTransport
    monkeypatch.setattr(participant_mcp, '_OriginTransport', lambda origin: transport(origin, transport=httpx.MockTransport(handle)))
    return calls


@pytest.mark.parametrize('mode,code', [('redirect', 'SERVER_REDIRECT_REFUSED'), ('pages', 'MCP_RESPONSE_LIMIT'),
    ('timeout', 'MCP_NEGOTIATION_UNCONFIRMED'), ('malformed', 'MCP_NEGOTIATION_UNCONFIRMED'),
    ('oversized', 'MCP_RESPONSE_LIMIT'), ('stream_limit', 'MCP_RESPONSE_LIMIT'),
    ('compression', 'MCP_RESPONSE_UNCONFIRMED'), ('tools', 'MCP_RESPONSE_LIMIT')])
def test_mcp_limits_redirects_and_unsafe_diagnostics_are_closed(monkeypatch, caplog, mode, code):
    secret = 'nxs_' + 'a' * 48
    calls = mock_mcp(monkeypatch, mode)
    with caplog.at_level('DEBUG'), pytest.raises(ConnectionError) as error:
        participant_mcp.inspect_mcp(fixtures.ORIGIN, secret, 'subject', timeout=.2 if mode == 'timeout' else 5)
    assert error.value.code == code
    assert secret not in caplog.text and secret not in str(error.value)
    assert not any(method == 'tools/call' for method in calls)


@pytest.mark.parametrize('mode', ['missing', 'schema'])
def test_initialized_transport_with_incompatible_surface_is_reported_separately(monkeypatch, mode):
    mock_mcp(monkeypatch, mode)
    result = participant_mcp.inspect_mcp(fixtures.ORIGIN, 'nxs_' + 'a' * 48, 'subject')
    assert result['compatible_surface'] is False and result['tools_called'] == 0


def test_transport_enforces_request_budget_before_sending_any_excess_request():
    sent = []
    def handle(request):
        sent.append(request.url)
        return httpx.Response(202)
    async def run():
        async with participant_mcp._OriginTransport(fixtures.ORIGIN, transport=httpx.MockTransport(handle)) as transport:
            for _ in range(16):
                response = await transport.handle_async_request(httpx.Request('POST', fixtures.ORIGIN + '/mcp'))
                await response.aclose()
            with pytest.raises(ConnectionError) as error:
                await transport.handle_async_request(httpx.Request('POST', fixtures.ORIGIN + '/mcp'))
            assert error.value.code == 'MCP_REQUEST_LIMIT'
    asyncio.run(run())
    assert len(sent) == 16

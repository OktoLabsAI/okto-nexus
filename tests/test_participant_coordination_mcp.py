"""Participant SDK over real TCP, canonical MCP and isolated SQLite state."""
import asyncio
import json
from types import SimpleNamespace

import pytest

import test_pr34_remediation as fixtures
from okto_nexus.adapters.outbound.participant_coordination_mcp import ParticipantMCP
from okto_nexus.adapters.outbound.participant_mcp import inspect_mcp
from okto_nexus.application.terminal_connection import ConnectionError


class ResponseFault:
    """Observe real calls, injecting transport cuts only after canonical work."""
    def __init__(self, app):
        self.app = app
        self.mode = None
        self.tool = 'message_create'
        self.calls = []
        self.hosts = []
        self.redirect = None
        self.key = None
        self.page = 0

    async def __call__(self, scope, receive, send):
        # The mount's /mcp -> /mcp/ redirect precedes the canonical handler.
        # Faults and call counts target the handler, never that empty response.
        if scope['type'] != 'http' or scope['path'] != '/mcp/':
            return await self.app(scope, receive, send)
        self.hosts.append(dict(scope['headers']).get(b'host'))
        received = []
        while True:
            item = await receive()
            received.append(item)
            if not item.get('more_body'):
                break
        raw = b''.join(item.get('body', b'') for item in received)
        request = json.loads(raw) if raw else {}
        method, tool = request.get('method'), request.get('params', {}).get('name')
        if method:
            self.calls.append((method, tool))

        async def replay():
            return received.pop(0) if received else await receive()

        mode = self.mode
        if mode == 'redirect' and method == 'initialize':
            self.mode = None
            await send(dict(type='http.response.start', status=307, headers=[(b'location', self.redirect.encode())]))
            return await send(dict(type='http.response.body', body=b''))
        catalogue = mode in ('schema', 'pages', 'too_many', 'missing') and method == 'tools/list'
        effect = mode in ('lost', 'malformed', 'oversized', 'key_echo', 'invalid_envelope',
                         'canonical_db', 'canonical_internal') and tool == self.tool
        if not catalogue and not effect:
            return await self.app(scope, replay, send)
        if mode != 'pages':
            self.mode = None
        captured = []

        async def capture(message):
            captured.append(message)

        await self.app(scope, replay, capture)
        # The real use case and its transaction completed before any cut.
        payload = b''.join(item.get('body', b'') for item in captured)
        if mode == 'lost':
            await asyncio.sleep(2)
            body = b'{}'
        elif mode == 'malformed':
            body = b'not-json PRIVATE-COORDINATION-PAYLOAD ' + self.key.encode()
        elif mode == 'oversized':
            body = b'x' * 1048577
        else:
            if payload.startswith(b'event:') or payload.startswith(b'data:'):
                payload = next(line[6:] for line in payload.splitlines() if line.startswith(b'data: '))
            value = json.loads(payload)
            result = value['result']
            if mode == 'schema':
                for item in result['tools']:
                    if item['name'] == self.tool:
                        item['outputSchema'] = dict(type='object', required=['PRIVATE-COORDINATION-PAYLOAD'])
            elif mode == 'pages':
                self.page += 1
                result['tools'] = [dict(name='page_' + str(self.page), inputSchema={'type': 'object'})]
                result['nextCursor'] = str(self.page)
            elif mode == 'too_many':
                result['tools'] = [dict(name='tool_' + str(i), inputSchema={'type': 'object'}) for i in range(513)]
            elif mode == 'missing':
                result['tools'] = [item for item in result['tools'] if item['name'] != 'nexus_info']
            elif mode in ('canonical_db', 'canonical_internal'):
                envelope = dict(ok=False, data=None, error=dict(
                    code='DB_ERROR' if mode == 'canonical_db' else 'INTERNAL_ERROR',
                    message='PRIVATE-COORDINATION-PAYLOAD'))
                # The canonical creation already committed; a subsequent hook
                # can still fail and be converted to a canonical error envelope.
                result['structuredContent'] = envelope
                result['content'] = [dict(type='text', text=json.dumps(envelope))]
            else:
                result['structuredContent'] = (dict(ok=True, data=dict(secret=self.key)) if mode == 'key_echo'
                                               else dict(ok='PRIVATE-COORDINATION-PAYLOAD', data={}))
            body = json.dumps(value).encode()
        await send(dict(type='http.response.start', status=200, headers=[(b'content-type', b'application/json')]))
        await send(dict(type='http.response.body', body=body))


@pytest.fixture
def server(tmp_path, monkeypatch):
    original = fixtures.build_app
    spies = []

    def build(*args, **kwargs):
        app = ResponseFault(original(*args, **kwargs))
        spies.append(app)
        return app

    monkeypatch.setattr(fixtures, 'build_app', build)
    running = fixtures._runtime(tmp_path, SimpleNamespace(param=False), monkeypatch)
    state = next(running)
    try:
        deps, client, root, _, _, key = state
        workspace = fixtures.tool(client, key, 'workspace_resolve', dict(project_root=root))['data']['workspace_id']
        spy = spies[0]
        spy.key = key
        spy.calls.clear()
        yield SimpleNamespace(deps=deps, client=client, key=key, workspace=workspace, spy=spy,
                              api=ParticipantMCP(str(client.base_url).rstrip('/'), key, 'caller', timeout=4))
    finally:
        running.close()


def args(server, operation='message_create'):
    data = dict(workspace_id=server.workspace, from_agent_id='caller', client_request_id='tcp-coordination',
                target=dict(strategy='direct', agent_id='worker'))
    return data | (dict(subject='Coordination', body='PRIVATE-COORDINATION-PAYLOAD') if operation == 'message_create'
                   else dict(visibility='eligible', payload=dict(objective='PRIVATE-COORDINATION-PAYLOAD')))


def recover(server, operation='message_create'):
    return server.api.call('coordination_request_get', dict(workspace_id=server.workspace,
        operation=operation, client_request_id='tcp-coordination'))


@pytest.mark.parametrize('operation', ['message_create', 'handoff_create'])
def test_real_tcp_discovery_creation_and_recovery_use_canonical_identity(server, operation):
    discovered = server.api.discover()
    assert discovered['info']['coordination_requests']['revision'] == 1
    assert 'client_request_id' in discovered['schemas'][operation]['properties']
    assert {tool for method, tool in server.spy.calls if method == 'tools/call'} == {'nexus_info'}
    first = server.api.call(operation, args(server, operation))
    assert first['status'] == 'created' and first['reused'] is False
    again = recover(server, operation)
    assert again['request_receipt'] == first['request_receipt'] and again['reused'] is True
    with server.deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM coordination_requests').fetchone()[0] == 1
        assert uow.connection.execute('SELECT COUNT(*) FROM sessions').fetchone()[0] == 0
        assert uow.connection.execute('SELECT COUNT(*) FROM execution_operations').fetchone()[0] == 0
    assert not any(tool == 'session_open' for _, tool in server.spy.calls)


def test_known_canonical_refusal_is_not_reported_as_uncertain_or_echoed(server, caplog):
    with caplog.at_level('DEBUG', logger='mcp.client'), pytest.raises(ConnectionError) as caught:
        server.api.call('message_create', args(server) | {'from_agent_id': 'worker'})
    error = caught.value
    assert (error.code, error.stage, error.possible_effect) == ('PERMISSION_DENIED', 'coordination', False)
    assert server.key not in caplog.text + str(error)
    assert 'PRIVATE-COORDINATION-PAYLOAD' not in caplog.text + str(error)
    with server.deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM messages').fetchone()[0] == 0


@pytest.mark.parametrize('mode', ['lost', 'malformed', 'oversized', 'key_echo', 'invalid_envelope', 'schema',
                                  'canonical_db', 'canonical_internal'])
def test_postcommit_transport_or_sdk_failure_recovers_without_a_second_create(server, caplog, mode):
    server.spy.mode = mode
    with caplog.at_level('DEBUG', logger='mcp.client'), pytest.raises(ConnectionError) as caught:
        server.api.call('message_create', args(server), timeout=1 if mode == 'lost' else 4)
    assert caught.value.possible_effect is True and caught.value.stage == 'coordination'
    if mode in ('canonical_db', 'canonical_internal'):
        assert caught.value.code == ('DB_ERROR' if mode == 'canonical_db' else 'INTERNAL_ERROR')
    assert server.key not in caplog.text + str(caught.value)
    assert 'PRIVATE-COORDINATION-PAYLOAD' not in caplog.text + str(caught.value)
    found = recover(server)
    assert found['status'] == 'created'
    assert sum(tool == 'message_create' for _, tool in server.spy.calls) == 1
    with server.deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM messages').fetchone()[0] == 1
        assert uow.connection.execute('SELECT COUNT(*) FROM coordination_requests').fetchone()[0] == 1


def test_read_response_failure_does_not_claim_a_productive_effect(server):
    server.spy.mode, server.spy.tool = 'invalid_envelope', 'coordination_request_get'
    with pytest.raises(ConnectionError) as caught:
        recover(server)
    assert caught.value.possible_effect is False
    assert caught.value.stage == 'coordination'


@pytest.mark.parametrize('mode,code', [('pages', 'MCP_RESPONSE_LIMIT'), ('too_many', 'MCP_RESPONSE_LIMIT'),
                                     ('missing', 'SERVER_UPGRADE_REQUIRED')])
def test_discovery_limits_and_old_server_refusal_precede_productive_calls(server, mode, code):
    server.spy.mode = mode
    with pytest.raises(ConnectionError) as caught:
        server.api.discover()
    assert caught.value.code == code and caught.value.possible_effect is False
    assert not any(method == 'tools/call' for method, _ in server.spy.calls)
    assert sum(method == 'tools/list' for method, _ in server.spy.calls) <= 4


def test_real_tcp_redirect_does_not_forward_the_participant_credential(server):
    origin = str(server.client.base_url).rstrip('/')
    server.spy.mode, server.spy.redirect = 'redirect', origin.replace('127.0.0.1', 'localhost') + '/mcp'
    with pytest.raises(ConnectionError) as caught:
        server.api.discover()
    assert caught.value.code == 'SERVER_REDIRECT_REFUSED' and caught.value.possible_effect is False
    assert all(host.startswith(b'127.0.0.1:') for host in server.spy.hosts)
    assert server.spy.calls == [('initialize', None)]


def test_doctor_still_only_initializes_and_lists_tools_over_real_tcp(server):
    report = inspect_mcp(str(server.client.base_url).rstrip('/'), server.key, 'caller', timeout=4)
    assert report['tools_called'] == 0 and report['agent_session_opened'] is False
    assert report['compatible_surface'] is True
    assert all(method in ('initialize', 'notifications/initialized', 'tools/list') for method, _ in server.spy.calls)
    with server.deps.connection_factory.unit_of_work(write=False) as uow:
        for table in ('sessions', 'messages', 'handoffs', 'coordination_requests'):
            assert uow.connection.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0] == 0


@pytest.mark.parametrize('timeout', [0, -1, 36, float('inf'), float('nan'), True, '15'])
def test_timeout_validation_precedes_transport(timeout):
    with pytest.raises(ConnectionError) as caught:
        ParticipantMCP('http://127.0.0.1:1', 'nxs_' + 'a' * 48, 'caller', timeout=timeout)
    assert caught.value.code == 'VALIDATION_ERROR' and caught.value.possible_effect is False


@pytest.mark.parametrize('tool,arguments', [('session_open', {}), ('message_create', []),
                                         ('message_create', {'body': float('nan')}),
                                         ('message_create', {'body': 'x' * 1048577})])
def test_invalid_call_is_refused_before_transport(tool, arguments):
    api = ParticipantMCP('http://127.0.0.1:1', 'nxs_' + 'a' * 48, 'caller')
    with pytest.raises(ConnectionError) as caught:
        api.call(tool, arguments)
    assert caught.value.code == 'VALIDATION_ERROR' and caught.value.possible_effect is False

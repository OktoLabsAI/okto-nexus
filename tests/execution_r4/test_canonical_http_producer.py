"""A separate MCP client admits work only through the existing serve owner."""
import socket
from types import SimpleNamespace

import pytest
import uvicorn

from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, qualified_contract, wait_receipt
from test_canonical_delivery import connected_local, enable
from test_canonical_result_publication import current_turn
from test_agent_recovery_isolation import eventually
from test_canonical_grant_regressions import mcp_helpers
from runtime_http_client import process_tool


@pytest.mark.parametrize('operation', ['open', 'message'])
def test_isolated_http_producer_keeps_native_execution_in_existing_owner(connected_local, operation):
    setup, binding, native = connected_local
    deps, app, client, headers, *_, root = setup
    owner = app.state.embedded_dispatch_owner
    channel = owner.channel
    enable(setup, binding)
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    sock.listen(128)
    address = f'http://127.0.0.1:{sock.getsockname()[1]}'
    server = uvicorn.Server(uvicorn.Config(app, lifespan='off', log_level='error'))
    async def serve():
        await server.serve(sockets=[sock])
    running = client.portal.start_task_soon(serve)
    try:
        eventually(lambda: server.started)
        actor = 'subject' if operation == 'open' else 'operator'
        key = headers[actor]['Authorization'].removeprefix('Bearer ')
        # Reuse the isolated -I child: its environment has no PATH/provider
        # configuration and it asserts that none of the three products import.
        runtime = (deps, SimpleNamespace(base_url=address), str(root), None, key, key)
        if operation == 'open':
            arguments = dict(agent_id='subject', kind='codex', project_root=str(root),
                endpoint_id=binding['endpoint_id'], idempotency_key='isolated-http-open')
            result = process_tool(runtime, 'harness_open', arguments)
            assert result['ok'], result
            replay = process_tool(runtime, 'harness_open', arguments)
            assert replay['ok'] and replay['data']['operation_id'] == result['data']['operation_id'], replay
            wait_receipt(setup, result['data'])
        else:
            result = process_tool(runtime, 'message_create', dict(project_root=str(root),
                from_agent_id='operator', subject='Isolated producer', body='One durable intent',
                target=dict(strategy='direct', agent_id='subject')))
            assert result['ok'] and len(result['data']['runtime_operations']) == 1, result
            wait_receipt(setup, current_turn(setup))
        assert owner.channel == channel and native.opens == 1
        assert len(native.native.sent) == (operation == 'message')
        with deps.connection_factory.unit_of_work(write=False) as uow:
            assert uow.connection.execute('SELECT COUNT(*) FROM execution_operations').fetchone()[0] == (1 if operation == 'open' else 2)
            assert uow.connection.execute('SELECT COUNT(*) FROM harness_sessions').fetchone()[0] == 0
            assert uow.connection.execute('SELECT COUNT(*) FROM message_deliveries').fetchone()[0] == (operation == 'message')
    finally:
        server.should_exit = True
        running.result(timeout=10)
        sock.close()

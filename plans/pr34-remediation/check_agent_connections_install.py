"""Installed-package smoke: disposable store, actual HTTP/MCP, no native launch.

Run with the installed tool's Python. No repository src path is injected.
The approved fixture endpoint is never opened with a valid credential, so no
provider, model, personal configuration or secret resolver is invoked.
"""
import json
import re
import socket
import tempfile
import threading
from pathlib import Path

import httpx
import uvicorn

from okto_nexus.adapters.inbound.http.app import build_app, ensure_operator_key
from okto_nexus.adapters.inbound.mcp.server import bootstrap
from okto_nexus.application.auth import AgentKeyAuthService


def main():
    with tempfile.TemporaryDirectory(prefix="nexus-connection-install-") as directory:
        root = Path(directory)
        project = root / "project"
        project.mkdir()
        deps = bootstrap({}, ["--home", str(root / "home"), "--embedding-mode", "off",
                              "--feature-harness-integrations", "true"])
        _, operator = ensure_operator_key(deps, AgentKeyAuthService(deps.repos.agents, deps.clock))
        ready = threading.Event()

        class Server(uvicorn.Server):
            async def startup(self, sockets=None):
                await super().startup(sockets)
                ready.set()

        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        address = "http://127.0.0.1:" + str(sock.getsockname()[1])
        server = Server(uvicorn.Config(build_app(deps, runtime_owner_api_url=address), log_level="error"))
        thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
        thread.start()
        try:
            assert ready.wait(15), "Isolated HTTP server did not start"
            with httpx.Client(base_url=address, trust_env=False, timeout=15) as client:
                headers = {"x-api-key": operator}

                def post(path, body):
                    response = client.post('/api/v1/' + path, headers=headers, json=body)
                    assert response.status_code == 200, (path, response.status_code)
                    return response.json()['data']

                post('agents', {'agent_id': 'fixture-connection', 'role': 'reviewer'})
                post('harness/profiles', {'profile_id': 'fixture-profile', 'adapter_id': 'pi', 'enabled': True})
                post('harness/endpoints', {'endpoint_id': 'fixture-endpoint', 'agent_id': 'fixture-connection',
                    'adapter_id': 'pi', 'project_root': str(project), 'profile_id': 'fixture-profile', 'enabled': True})
                issued = post('agents/fixture-connection/connection-keys', {'endpoint_id': 'fixture-endpoint'})
                assert issued['expires_at'] is not None
                assert client.get('/api/v1/agents', headers=issued['request']['headers']).status_code == 401
                assert client.delete('/api/v1/agents/fixture-connection/connection-keys/' + issued['key_id'], headers=headers).status_code == 200
                assert client.post('/api/v1/connections/open', headers=issued['request']['headers'], json={}).status_code == 403
                response = client.post('/mcp/', headers={**headers, 'Accept': 'application/json, text/event-stream'}, json={
                    'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {'name': 'harness_list',
                    'arguments': {'view': 'connections', 'maintenance': {'agent_id': 'fixture-connection'}}}})
                assert response.status_code == 200
                result = (json.loads(next(line[6:] for line in response.text.splitlines() if line.startswith('data: ')))
                    if 'text/event-stream' in response.headers.get('content-type', '') else response.json())['result']
                envelope = result.get('structuredContent') or json.loads(result['content'][0]['text'])
                assert envelope['ok'] and envelope['data']['effective_key_ttl_seconds'] == 86400
                html = client.get('/').text
                script = re.search(r'src="([^"]+\.js)"', html).group(1)
                bundle = client.get(script).text
                assert 'Connection methods' in bundle and 'Copy request' in bundle
                assert not deps.harness_supervisor.list_live() if deps.harness_supervisor else True
                print(json.dumps({'status': 'PASS', 'http_mcp_policy_and_credentials': True,
                    'packaged_dashboard': True, 'native_processes_started': 0}))
        finally:
            server.should_exit = True
            thread.join(15)
            sock.close()
            assert not thread.is_alive()


if __name__ == '__main__':
    main()

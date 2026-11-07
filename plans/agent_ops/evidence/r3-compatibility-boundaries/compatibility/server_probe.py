"""Installed Server public-protocol fixture; lifecycle/native startup disabled."""
from pathlib import Path
import asyncio
import hashlib
import importlib.metadata
import json
import os
import socket
import sys

import uvicorn
from okto_nexus.bootstrap.dependencies import bootstrap
from okto_nexus.adapters.inbound.http.app import build_app

root = Path(sys.argv[1])
root.mkdir()
deps = bootstrap({}, ['--home', str(root / 'home')])
app = build_app(deps)
requests = []


def snapshot():
    rows = {}
    with deps.connection_factory.unit_of_work(write=False) as uow:
        conn = uow.connection
        names = [row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        for name in names:
            quoted = '"' + name.replace('"', '""') + '"'
            serialized = sorted(json.dumps(list(row), ensure_ascii=False, separators=(',', ':'),
                                default=lambda value: {'bytes_sha256': hashlib.sha256(value).hexdigest()})
                                for row in conn.execute('SELECT * FROM ' + quoted))
            rows[name] = {'count': len(serialized),
                          'sha256': hashlib.sha256('\n'.join(serialized).encode('utf-8')).hexdigest()}
    return rows


async def monitored(scope, receive, send):
    if scope['type'] != 'http':
        raise AssertionError('Only HTTP protocol discovery is allowed')
    headers = {key.lower(): value for key, value in scope['headers']}
    row = {'method': scope['method'], 'path': scope['path'],
           'query_present': bool(scope.get('query_string')),
           'authorization_present': b'authorization' in headers,
           'cookie_present': b'cookie' in headers, 'x_api_key_present': b'x-api-key' in headers}
    requests.append(row)
    if row['method'] != 'GET' or row['path'] != '/v1/connections/protocol':
        row['status'] = 405
        await send({'type': 'http.response.start', 'status': 405, 'headers': []})
        await send({'type': 'http.response.body', 'body': b''})
        return

    async def observed_send(message):
        if message['type'] == 'http.response.start':
            row['status'] = message['status']
        await send(message)

    await app(scope, receive, observed_send)


async def run():
    before = snapshot()
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    sock.listen()
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(monitored, lifespan='off', log_level='error', access_log=False))
    task = asyncio.create_task(server.serve(sockets=[sock]))
    try:
        while not server.started:
            if task.done():
                await task
                raise RuntimeError('Server did not start')
            await asyncio.sleep(.01)
        (root / 'ready.json').write_text(json.dumps({
            'pid': os.getpid(), 'url': f'http://127.0.0.1:{port}',
            'nexus_version': importlib.metadata.version('okto-nexus'),
            'core_version': importlib.metadata.version('okto-nexus-connector-core'),
            'fixture': 'public protocol only; app lifespan disabled; no daemon or native lifecycle',
        }, indent=2) + '\n', encoding='utf-8')
        deadline = asyncio.get_running_loop().time() + 90
        while not (root / 'stop').exists():
            if asyncio.get_running_loop().time() > deadline:
                raise TimeoutError('Finite fixture deadline exceeded')
            await asyncio.sleep(.05)
    finally:
        server.should_exit = True
        await asyncio.wait_for(task, 10)
        sock.close()
        after = snapshot()
        changed = sorted(name for name in before.keys() | after.keys() if before.get(name) != after.get(name))
        (root / 'proof.json').write_text(json.dumps({
            'requests': requests, 'before': before, 'after': after, 'changed_tables': changed,
            'all_requests_public_uncredentialed': all(
                row['method'] == 'GET' and row['path'] == '/v1/connections/protocol'
                and not any(row[key] for key in ('authorization_present', 'cookie_present', 'x_api_key_present', 'query_present'))
                for row in requests),
            'no_application_lifespan': True, 'socket_closed': True,
        }, indent=2) + '\n', encoding='utf-8')
        assert not changed, changed


asyncio.run(run())

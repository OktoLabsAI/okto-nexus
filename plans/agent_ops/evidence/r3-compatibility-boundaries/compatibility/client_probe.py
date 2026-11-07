"""Use the installed Connector's unmodified public protocol negotiation."""
from pathlib import Path
import asyncio
from dataclasses import asdict
import importlib.metadata
import json
import sys

import httpx
from okto_nexus_connector.errors import ConnectorError
from okto_nexus_connector.transport.https_client import NexusHTTPClient

url, report = sys.argv[1:]


async def run():
    calls = []

    async def observe(request):
        calls.append({'method': request.method, 'path': request.url.path,
                      'query_present': bool(request.url.query),
                      'authorization_present': 'authorization' in request.headers,
                      'cookie_present': 'cookie' in request.headers,
                      'x_api_key_present': 'x-api-key' in request.headers,
                      'body_bytes': len(request.content)})

    result = {'connector_version': importlib.metadata.version('okto-nexus-connector'),
              'client_core_version': importlib.metadata.version('okto-nexus-connector-core')}
    async with httpx.AsyncClient(trust_env=False, follow_redirects=False,
                                 event_hooks={'request': [observe]}) as transport:
        client = NexusHTTPClient(url, client=transport)
        try:
            result['protocol'] = asdict(await client.r4_protocol())
            result['state'] = 'compatible'
        except ConnectorError as exc:
            result.update(state='refused', code=exc.code, stage=exc.stage,
                          possible_effect=exc.possible_effect, retry_safe=exc.retry_safe)
    result['requests'] = calls
    assert len(calls) == 1 and calls[0] == {
        'method': 'GET', 'path': '/v1/connections/protocol', 'query_present': False,
        'authorization_present': False, 'cookie_present': False,
        'x_api_key_present': False, 'body_bytes': 0}
    Path(report).write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')


asyncio.run(run())

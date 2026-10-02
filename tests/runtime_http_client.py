"""Independent MCP HTTP client; no Server composition or access to its store."""
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys


def process_tool(runtime, name, arguments, *, key=None):
    _, client, root, _, _, caller = runtime
    request = dict(url=str(client.base_url).rstrip('/') + '/mcp/',
                   key=key or caller, name=name, arguments=arguments)
    env = {k: v for k, v in os.environ.items()
           if k.upper() in {'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP'}}
    env['PYTHONIOENCODING'] = 'utf-8'
    result = subprocess.run([sys.executable, '-I', str(Path(__file__).resolve())],
        input=json.dumps(request), cwd=root, env=env,
        capture_output=True, text=True, encoding='utf-8', timeout=30)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


async def main(request):
    import httpx
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    async with httpx.AsyncClient(headers={'Authorization': 'Bearer ' + request['key']},
                                 trust_env=False) as http:
        async with streamable_http_client(request['url'], http_client=http) as (reader, writer, _):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                result = await session.call_tool(request['name'], request['arguments'])
    assert not any(name in sys.modules for name in
                   ('okto_nexus', 'okto_nexus_connector', 'nexus_connector_core'))
    return result.structuredContent or json.loads(result.content[0].text)


if __name__ == '__main__':
    print(json.dumps(asyncio.run(main(json.load(sys.stdin)))))

"""Explicit, bounded MCP initialize/list check; never invokes a tool or model."""
import asyncio
from contextvars import ContextVar
from datetime import timedelta
import logging
from urllib.parse import urlsplit

import httpx

from ...application.terminal_connection import ConnectionError
from .participant_client import participant_key
from .operator_client import server_origin

_checking = ContextVar('participant_mcp_check', default=False)
_SURFACE = {'session_open': {'agent_id'}, 'message_create': {'from_agent_id', 'body', 'workspace_id'},
    'handoff_create': {'from_agent_id', 'target', 'visibility', 'workspace_id'}}


class _PrivateSDKLogs(logging.Filter):
    def filter(self, record):
        # SDK diagnostics can include raw remote payloads or transport session
        # identifiers. Only suppress this check's async context, not other work.
        return not _checking.get()


class _BoundedStream(httpx.AsyncByteStream):
    def __init__(self, stream, refuse):
        self.stream, self.refuse = stream, refuse

    async def __aiter__(self):
        size = 0
        async for chunk in self.stream:
            size += len(chunk)
            if size > 1048576:
                self.refuse('MCP_RESPONSE_LIMIT')
            yield chunk

    async def aclose(self):
        await self.stream.aclose()


class _OriginTransport(httpx.AsyncBaseTransport):
    def __init__(self, origin, *, transport=None):
        self.origin, self.remaining = origin, 16
        self.refusal = None
        self.transport = transport or httpx.AsyncHTTPTransport(retries=0)

    def refuse(self, code):
        self.refusal = ConnectionError(code, 'The MCP response exceeded or violated the diagnostic limits.')
        raise self.refusal

    async def handle_async_request(self, request):
        address = urlsplit(str(request.url))
        origin = server_origin(address.scheme + '://' + address.netloc)
        if (origin != self.origin or address.path not in ('/mcp', '/mcp/') or address.query or
                request.method not in ('GET', 'POST', 'DELETE')):
            self.refuse('MCP_ORIGIN_REFUSED')
        self.remaining -= 1
        if self.remaining < 0:
            self.refuse('MCP_REQUEST_LIMIT')
        response = await self.transport.handle_async_request(request)
        if 300 <= response.status_code < 400:
            location = response.headers.get('location', '')
            # Permit only the Server mount's exact same-origin slash redirect.
            # This also keeps arbitrary redirect URLs out of SDK error logs.
            if not (response.status_code in (307, 308) and address.path == '/mcp' and
                    location in ('/mcp/', self.origin + '/mcp/')):
                await response.aclose()
                self.refuse('SERVER_REDIRECT_REFUSED')
        if response.headers.get('content-encoding', 'identity') != 'identity':
            await response.aclose()
            self.refuse('MCP_RESPONSE_UNCONFIRMED')
        length = response.headers.get('content-length')
        if length is not None and (not length.isdecimal() or len(length) > 12 or int(length) > 1048576):
            await response.aclose()
            self.refuse('MCP_RESPONSE_LIMIT')
        if response.is_stream_consumed and len(response.content) > 1048576:
            await response.aclose()
            self.refuse('MCP_RESPONSE_LIMIT')
        response.stream = _BoundedStream(response.stream, self.refuse)
        return response

    async def aclose(self):
        await self.transport.aclose()


async def _inspect(origin, key, agent_id, timeout):
    try:
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client
        from mcp.types import Implementation
    except ImportError:
        raise ConnectionError('MCP_CLIENT_UPGRADE_REQUIRED', 'Install a supported MCP SDK before running the active participant check.') from None

    token = _checking.set(True)
    private = _PrivateSDKLogs()
    loggers = [logging.getLogger(name) for name in list(logging.Logger.manager.loggerDict)
               if name == 'mcp' or name.startswith('mcp.')]
    for logger in loggers:
        logger.addFilter(private)
    transport = None
    try:
        transport = _OriginTransport(origin)
        async def query():
            async with httpx.AsyncClient(transport=transport, trust_env=False,
                    timeout=timeout, follow_redirects=False, headers={'Authorization': 'Bearer ' + key,
                    'X-Nexus-Agent-Hint': agent_id, 'Accept-Encoding': 'identity'}) as http:
                async with streamable_http_client(origin + '/mcp', http_client=http) as (reader, writer, _):
                    async with ClientSession(reader, writer, read_timeout_seconds=timedelta(seconds=timeout),
                            client_info=Implementation(name='okto-nexus-participant-doctor', version='1')) as session:
                        initialized = await session.initialize()
                        schemas, cursor = {}, None
                        for _ in range(4):
                            listed = await session.list_tools(cursor=cursor)
                            schemas.update((tool.name, tool.inputSchema) for tool in listed.tools)
                            if len(schemas) > 512:
                                raise ConnectionError('MCP_RESPONSE_LIMIT', 'The advertised surface exceeds the diagnostic limit.')
                            cursor = listed.nextCursor
                            if not cursor:
                                break
                        else:
                            raise ConnectionError('MCP_RESPONSE_LIMIT', 'The MCP tool listing exceeded the page budget.')
                        compatible = all(name in schemas and schemas[name].get('type') == 'object' and
                            isinstance(schemas[name].get('properties'), dict) and fields <= schemas[name]['properties'].keys()
                            for name, fields in _SURFACE.items())
                        return dict(protocol_version=initialized.protocolVersion, tool_count=len(schemas),
                            required_tools=sorted(_SURFACE), surface_check='names_and_input_fields_v1', compatible_surface=compatible,
                            context='participant_doctor', tools_called=0, agent_session_opened=False)
        result = await asyncio.wait_for(query(), timeout)
        if transport.refusal:
            raise transport.refusal
        return result
    except Exception as error:
        def find(error):
            if isinstance(error, ConnectionError):
                return error
            if isinstance(error, httpx.HTTPStatusError) and error.response.status_code in (401, 403):
                return ConnectionError('MCP_AUTH_REFUSED', 'The MCP endpoint refused the selected identity.')
            for child in getattr(error, 'exceptions', ()):
                matched = find(child)
                if matched:
                    return matched
        known = (transport.refusal if transport else None) or find(error)
        if known:
            raise known from None
        raise ConnectionError('MCP_NEGOTIATION_UNCONFIRMED',
            'The selected endpoint did not complete the bounded MCP check. No tools or model were invoked.') from None
    finally:
        for logger in loggers:
            logger.removeFilter(private)
        _checking.reset(token)


def inspect_mcp(origin, key, agent_id, *, timeout=10):
    if not 0 < timeout <= 30:
        raise ValueError('MCP timeout must be greater than zero and at most 30 seconds.')
    return asyncio.run(_inspect(server_origin(origin), participant_key(key), agent_id, timeout))

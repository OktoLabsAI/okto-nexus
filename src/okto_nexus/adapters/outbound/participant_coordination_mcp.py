"""Bounded participant MCP calls; request persistence belongs to the CLI facade.

Each invocation owns an ephemeral SDK transport, never a canonical agent
session. No productive call is resubmitted by this adapter.
"""
from __future__ import annotations

import asyncio
from datetime import timedelta
import json
import logging
import math

import httpx

from ...application.terminal_connection import ConnectionError
from ...errors import ERROR_CODES
from .operator_client import server_origin
from .participant_client import participant_key
from . import participant_mcp as diagnostic


PRODUCTIVE = frozenset({'message_create', 'handoff_create'})
TOOLS = PRODUCTIVE | {'coordination_request_get', 'handoff_get', 'event_cursor', 'event_wait', 'nexus_info'}


def _error(code, message, *, possible_effect=False):
    return ConnectionError(code, message, possible_effect=possible_effect, stage='coordination')


def _timeout(value):
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 < value <= 35:
        raise _error('VALIDATION_ERROR', 'The MCP timeout must be finite, greater than zero and at most 35 seconds.')
    return value


class _CanonicalRefusal(ConnectionError):
    """A validated canonical error envelope confirms the refusal."""


def _nested(error, kind):
    if isinstance(error, kind):
        return error
    for child in getattr(error, 'exceptions', ()):
        match = _nested(child, kind)
        if match is not None:
            return match
    return None


class ParticipantMCP:
    def __init__(self, origin, key, agent_id, *, timeout=15):
        self.timeout = _timeout(timeout)
        try:
            self.origin, self._key = server_origin(origin), participant_key(key)
        except ConnectionError as error:
            raise _error(error.code, 'The selected participant connection is invalid.') from None
        if (type(agent_id) is not str or not 1 <= len(agent_id) <= 160 or
                not agent_id.isprintable() or agent_id.strip() != agent_id):
            raise _error('VALIDATION_ERROR', 'A canonical participant agent ID is required.')
        self.agent_id = agent_id

    def discover(self):
        return self._run(None, None, self.timeout)

    def call(self, tool, arguments, *, timeout=None):
        if type(tool) is not str or tool not in TOOLS:
            raise _error('VALIDATION_ERROR', 'This tool is outside the coordination client surface.')
        try:
            if type(arguments) is not dict:
                raise ValueError()
            encoded = json.dumps(arguments, ensure_ascii=False, allow_nan=False).encode('utf-8')
            if len(encoded) > 1048576:
                raise ValueError()
            # Snapshot caller-owned input before entering asynchronous transport.
            arguments = json.loads(encoded)
        except (ValueError, TypeError, UnicodeError, RecursionError):
            raise _error('VALIDATION_ERROR', 'Coordination arguments must be a bounded JSON object.') from None
        return self._run(tool, arguments, self.timeout if timeout is None else _timeout(timeout))

    def _run(self, tool, arguments, timeout):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:
            raise _error('MCP_SYNC_CONTEXT_UNAVAILABLE', 'Call the synchronous participant client outside an active event loop.')
        return asyncio.run(self._request(tool, arguments, timeout))

    def _envelope(self, result):
        value = result.structuredContent
        if value is None:
            if len(result.content) != 1 or result.content[0].type != 'text':
                raise _error('MCP_RESPONSE_UNCONFIRMED', 'The Server did not return a canonical coordination envelope.')
            try:
                value = json.loads(result.content[0].text)
            except (ValueError, TypeError):
                raise _error('MCP_RESPONSE_UNCONFIRMED', 'The Server returned an invalid coordination envelope.') from None
        if type(value) is not dict or type(value.get('ok')) is not bool or self._key in json.dumps(value):
            raise _error('MCP_RESPONSE_UNCONFIRMED', 'The Server returned an unsafe or malformed coordination envelope.')
        if value['ok']:
            if result.isError or type(value.get('data')) is not dict or value.get('error') is not None:
                raise _error('MCP_RESPONSE_UNCONFIRMED', 'The Server did not confirm a valid coordination result.')
            return value['data']
        error = value.get('error')
        if (type(error) is not dict or error.get('code') not in ERROR_CODES or
                type(error.get('message')) is not str or value.get('data') is not None):
            raise _error('MCP_RESPONSE_UNCONFIRMED', 'The Server returned an invalid coordination refusal.')
        raise _CanonicalRefusal(error['code'], 'The Server refused the coordination request.', stage='coordination')

    async def _request(self, tool, arguments, timeout):
        try:
            from mcp import ClientSession
            from mcp.client.streamable_http import streamable_http_client
            from mcp.types import Implementation
        except ImportError:
            raise _error('MCP_CLIENT_UPGRADE_REQUIRED', 'Install a supported MCP SDK before using coordination.') from None

        token = diagnostic._checking.set(True)
        private = diagnostic._PrivateSDKLogs()
        loggers = [logging.getLogger(name) for name in list(logging.Logger.manager.loggerDict)
                   if name == 'mcp' or name.startswith('mcp.')]
        for logger in loggers:
            logger.addFilter(private)
        transport = None
        productive_started = False
        try:
            transport = diagnostic._OriginTransport(self.origin)

            async def query():
                nonlocal productive_started
                async with httpx.AsyncClient(transport=transport, trust_env=False, timeout=timeout,
                        follow_redirects=False, headers={'Authorization': 'Bearer ' + self._key,
                            'X-Nexus-Agent-Hint': self.agent_id, 'Accept-Encoding': 'identity'}) as http:
                    async with streamable_http_client(self.origin + '/mcp', http_client=http) as (reader, writer, _):
                        async with ClientSession(reader, writer, read_timeout_seconds=timedelta(seconds=timeout),
                                client_info=Implementation(name='okto-nexus-coordination', version='1')) as session:
                            await session.initialize()
                            if tool is not None:
                                productive_started = tool in PRODUCTIVE
                                return self._envelope(await session.call_tool(tool, arguments))
                            schemas, cursor = {}, None
                            for _ in range(4):
                                listed = await session.list_tools(cursor=cursor)
                                for item in listed.tools:
                                    if item.name in schemas or type(item.inputSchema) is not dict:
                                        raise _error('MCP_RESPONSE_UNCONFIRMED', 'The Server returned an ambiguous tool catalogue.')
                                    schemas[item.name] = item.inputSchema
                                if len(schemas) > 512:
                                    raise _error('MCP_RESPONSE_LIMIT', 'The tool catalogue exceeds the coordination limit.')
                                cursor = listed.nextCursor
                                if not cursor:
                                    break
                            else:
                                raise _error('MCP_RESPONSE_LIMIT', 'The tool catalogue exceeded the page budget.')
                            if self._key in json.dumps(schemas):
                                raise _error('MCP_RESPONSE_UNCONFIRMED', 'The Server returned an unsafe tool catalogue.')
                            if 'nexus_info' not in schemas:
                                raise _error('SERVER_UPGRADE_REQUIRED', 'The Server does not advertise coordination discovery.')
                            return dict(info=self._envelope(await session.call_tool('nexus_info', {})), schemas=schemas)

            result = await asyncio.wait_for(query(), timeout)
            if transport.refusal is not None:
                raise transport.refusal
            return result
        except Exception as error:
            refusal = _nested(error, _CanonicalRefusal)
            if refusal is not None:
                raise _error(refusal.code, refusal.message,
                    possible_effect=productive_started and refusal.code in {'DB_ERROR', 'INTERNAL_ERROR'}) from None
            known = (transport.refusal if transport else None) or _nested(error, ConnectionError)
            if known is not None:
                raise _error(known.code, 'The MCP response could not be confirmed within the coordination limits.',
                             possible_effect=productive_started) from None
            if _nested(error, httpx.HTTPStatusError) is not None:
                status = _nested(error, httpx.HTTPStatusError).response.status_code
                if status in (401, 403):
                    raise _error('MCP_AUTH_REFUSED', 'The MCP endpoint refused the selected identity.',
                                 possible_effect=productive_started) from None
            raise _error('OUTCOME_UNKNOWN' if productive_started else 'MCP_RESPONSE_UNCONFIRMED',
                'The MCP response is unavailable. Recover the same saved request before another submission.'
                if productive_started else 'The MCP read could not be confirmed.',
                possible_effect=productive_started) from None
        finally:
            for logger in loggers:
                logger.removeFilter(private)
            diagnostic._checking.reset(token)

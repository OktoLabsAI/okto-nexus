"""Authenticated self discovery/opening through actual HTTP/MCP and owner proxy."""
import asyncio
import json
import httpx

import pytest
from test_pr34_remediation import runtime as runtime_fixture
from test_pr34_remediation import tool

from okto_nexus.application.auth import AgentKeyAuthService
from okto_nexus.domain.base import iso_plus

runtime = runtime_fixture


def worker_key(runtime):
    deps = runtime[0]
    with deps.connection_factory.unit_of_work() as uow:
        return AgentKeyAuthService(deps.repos.agents, deps.clock).issue_key(uow, agent_id="worker")


def grant(runtime, actor="worker", endpoint="endpoint-pi"):
    deps, client, _, _, operator, _ = runtime
    result = client.post('/api/v1/harness/grants', headers={'x-api-key': operator}, json={
        'actor_agent_id': actor, 'endpoint_id': endpoint, 'actions': ['open', 'discover'],
        'expires_at': iso_plus(deps.clock.now_iso(), 600)})
    assert result.status_code == 200
    return result.json()['data']['grant_id']


def available(runtime, key):
    result = tool(runtime[1], key, 'harness_list', {'view': 'connections', 'maintenance': {'action': 'available'}})
    assert result['ok'], result
    return result['data']

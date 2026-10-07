"""P04: one production composition, real HTTP/MCP, synthetic external peer."""
from concurrent.futures import ThreadPoolExecutor

import pytest

from okto_nexus.domain.base import iso_plus
from okto_nexus.domain.runtime_context import RuntimeRequestContext
from okto_nexus.errors import OktoNexusError
from okto_nexus.adapters.inbound.mcp.tools.harness import build_access_service
from test_pr34_remediation import open_rest, tool, wait_sent
from test_pr34_remediation import runtime as runtime_fixture

runtime = runtime_fixture


def issue(runtime, actions, **extra):
    deps, client, _, _, operator, _ = runtime
    result = client.post("/api/v1/harness/grants", headers={"x-api-key": operator}, json={
        "actor_agent_id": "caller", "endpoint_id": "endpoint-pi", "actions": actions,
        "expires_at": iso_plus(deps.clock.now_iso(), 3600), **extra})
    assert result.status_code == 200, result.text
    return result.json()["data"]








def test_p04_internal_missing_authentication_cannot_impersonate_operator(runtime):
    deps, _, _, peers, _, _ = runtime
    with pytest.raises(OktoNexusError):
        build_access_service(deps).authorize(RuntimeRequestContext("operator", "payload"))
    assert peers == []

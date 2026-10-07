"""Safe runtime discovery through authenticated production HTTP/MCP."""
import json
import asyncio
import sys

import pytest

from test_pr34_remediation import runtime as runtime_fixture, tool, open_rest
from test_runtime_grants import issue
from test_runtime_commands import wait_close_result
from okto_nexus.domain.base import iso_plus

runtime = runtime_fixture


def discover(runtime, key=None, **parameters):
    return tool(runtime[1], key or runtime[5], "harness_list", {"view": "bindings", "maintenance": parameters})












def test_discovery_internal_payload_identity_cannot_authenticate(runtime):
    from okto_nexus.application.runtime_discovery import RuntimeDiscoveryService
    from okto_nexus.adapters.inbound.mcp.tools.harness import build_access_service
    from okto_nexus.domain.runtime_context import RuntimeRequestContext
    from okto_nexus.errors import OktoNexusError
    service = RuntimeDiscoveryService(access=build_access_service(runtime[0]))
    for context in (RuntimeRequestContext("operator", "payload"),
                    RuntimeRequestContext("caller", "agent_key", credential_binding="obsolete")):
        with pytest.raises(OktoNexusError, match="not authorized"):
            service.list(context)




def test_discovery_preserves_partial_attach_capabilities_without_opening_peer(runtime):
    deps, _, _, peers, _, _ = runtime
    deps.config.feature_harness_attach = True
    for adapter in ("codex", "claude_code.attach"):
        issue(runtime, ["discover"], endpoint_id="endpoint-" + adapter)
    result = discover(runtime)
    assert result["ok"], result
    bindings = {item["adapter_id"]: item for item in result["data"]["agents"][0]["endpoints"]}
    assert bindings["codex"]["declared_capabilities"]["correlated_results"]
    partial = bindings["claude_code.attach"]["declared_capabilities"]
    assert partial["conversation"]
    assert not any(partial[key] for key in ("events", "managed_work", "interrupt", "correlated_results", "native_deduplication"))
    assert peers == []
    deps.config.feature_harness_attach = False
    assert [e["adapter_id"] for e in discover(runtime)["data"]["agents"][0]["endpoints"]] == ["codex"]

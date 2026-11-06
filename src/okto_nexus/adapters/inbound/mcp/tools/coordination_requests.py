"""Canonical metadata recovery for the same authenticated coordination request."""
from typing import Annotated, Any

from pydantic import Field

from .....application.coordination_requests import CoordinationRequestService
from .....envelope import tool_envelope
from ...http.identity_ctx import runtime_request_context


def register(server: Any, deps: Any) -> None:
    service = CoordinationRequestService(factory=deps.connection_factory,
        repo=deps.repos.coordination_requests, agents=deps.repos.agents,
        workspaces=deps.repos.workspaces, clock=deps.clock, context_provider=runtime_request_context)

    @server.tool()
    @tool_envelope
    def coordination_request_get(
        workspace_id: Annotated[str, Field(description="Existing logical workspace ID; managed sessions use their bound workspace.")],
        operation: Annotated[str, Field(description="message_create or handoff_create.")],
        client_request_id: Annotated[str, Field(description="The exact request ID persisted before submission.")],
    ) -> dict:
        """Read your own creation/approval reference; no heartbeat/work. Expired or missing receipts need review. Docs: okto-nexus://reference/tool-docs/messages."""
        return service.get(workspace_id=workspace_id, operation=operation, client_request_id=client_request_id)

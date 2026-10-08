"""Native questions addressed to the authenticated interlocutor."""
from typing import Annotated, Any

from pydantic import Field

from .....domain.execution_principal import current_execution_principal
from .....domain.runtime_context import RuntimeRequestContext
from .....envelope import tool_envelope
from ...http.identity_ctx import runtime_request_context


def _context():
    principal = current_execution_principal.get()
    if principal is not None:
        return RuntimeRequestContext(principal.scope['agent_id'], 'session_capability')
    return runtime_request_context()


def register(server, deps):
    if deps.native_decisions is None:
        return

    @server.tool()
    @tool_envelope
    def runtime_input_list(
        workspace_id: Annotated[str | None, Field(description='Optional canonical workspace ID. Managed sessions are always limited to their bound workspace.')] = None,
    ) -> dict[str, Any]:
        """List native questions addressed to YOU, with response contracts and immutable references. Use runtime_input_respond to answer or decline; never answer for someone else."""
        items = deps.native_decisions.pending_inputs(context=_context(), workspace_id=workspace_id)
        return {'items': [item['request_payload']['kwargs'] for item in items]}

    @server.tool()
    @tool_envelope
    def runtime_input_respond(
        request: Annotated[dict[str, Any], Field(description='Copy approval_key, expected_revision, request_hash and cas_token from runtime_input_list. Add a unique client_intent_id, decision (approve or deny), and response when approving. Do not include display, recipient_agent_id or expires_at.')],
    ) -> dict[str, Any]:
        """Answer YOUR native question using its response contract. To decline, set decision=deny and omit response. Cannot approve execution permissions; recording a decision does not prove native delivery."""
        value, reused = deps.native_decisions.confirm(context=_context(), request=request)
        return {'decision': value, 'reused': reused}

"""Recover the current receipt of a previously accepted input without replay."""

from ..adapters.outbound.sqlite.session_interaction import _scope_params
from ..domain.runtime_context import RuntimeRequestContext
from ..domain.session_interaction import (
    InputAuthor,
    InputDeliveryState,
    InputScope,
    QueuedReceipt,
)
from ..errors import ErrorCode, OktoNexusError
from .execution_session_views import read_execution_session


def _unavailable() -> OktoNexusError:
    return OktoNexusError(ErrorCode.NOT_FOUND, "The input receipt was not found in this scope.")


def read_session_input_receipt(
    factory, *, access, resolve_human, scope: InputScope, author: InputAuthor,
    client_intent_id: str | None = None, input_id: str | None = None,
) -> QueuedReceipt:
    """Resolve an opaque, server-issued author reference and read one exact receipt.

    The requested generation identifies the retained input. The session may be
    at a later generation as long as its canonical scope is still visible.
    """
    if not resolve_human(author.authority_ref):
        raise _unavailable()
    if (client_intent_id is None) == (input_id is None):
        raise ValueError("Supply one input receipt identity.")

    context = RuntimeRequestContext("operator", "operator_session", trusted_local_operator=True)
    params = _scope_params(scope)
    with factory.unit_of_work(write=False) as uow:
        try:
            session = read_execution_session(
                factory, server_id=scope.session.server_id, executor_id=scope.session.executor_id,
                session_id=scope.session.session_id, context=context, access=access, _uow=uow,
            )
        except OktoNexusError as error:
            if error.code in (ErrorCode.NOT_FOUND, ErrorCode.PERMISSION_DENIED, ErrorCode.VALIDATION_ERROR):
                raise _unavailable() from None
            raise

        current_scope = session["scope"]
        if (current_scope["session_owner_generation"] < scope.generation.value
                or any(current_scope[key] != value for key, value in params.items() if key != "owner_generation")):
            raise _unavailable()

        row = uow.connection.execute("""
            SELECT i.input_id, i.enqueue_sequence, i.input_revision, q.revision AS queue_revision,
                i.status, i.operation_id, i.possible_effect,
                (c.confirmed_effect_revision IS NOT NULL) AS reorientation,
                (c.confirmed_effect_revision IS NOT NULL AND d.dispatch_state='DISPATCHED'
                    AND r.stage='SUBMITTED') AS steer_submitted
            FROM session_interaction_inputs i
            JOIN session_interaction_queues q USING (server_id, executor_id, session_id)
            JOIN execution_sessions s USING (server_id, executor_id, session_id)
            JOIN execution_bindings b ON b.server_id=s.server_id AND b.executor_id=s.executor_id AND b.binding_id=s.binding_id
            JOIN execution_workspace_bindings w ON w.server_id=s.server_id AND w.executor_id=s.executor_id
                AND w.workspace_binding_id=s.workspace_binding_id AND w.workspace_id=s.workspace_id
            JOIN agent_endpoints e ON e.endpoint_id=b.endpoint_id
            LEFT JOIN session_interaction_controls c ON c.server_id=i.server_id AND c.executor_id=i.executor_id
                AND c.session_id=i.session_id AND c.operation_id=i.operation_id AND c.owner_generation=i.owner_generation
            LEFT JOIN execution_dispatch_outbox d ON d.server_id=i.server_id AND d.executor_id=i.executor_id
                AND d.operation_id=i.operation_id
            LEFT JOIN execution_receipts r ON r.server_id=d.server_id AND r.executor_id=d.executor_id
                AND r.operation_id=d.operation_id AND r.receipt_revision=d.last_receipt_revision
            WHERE i.server_id=:server_id AND i.executor_id=:executor_id AND i.session_id=:session_id
              AND i.owner_generation=:owner_generation AND i.binding_id=:binding_id AND i.workspace_id=:workspace_id
              AND i.workspace_binding_id=:workspace_binding_id AND i.agent_id=:agent_id
              AND i.authority_ref=:authority_ref AND i.surface=:surface
              AND (i.client_intent_id=:client_intent_id OR i.input_id=:input_id)
              AND s.binding_id=i.binding_id AND s.workspace_id=i.workspace_id
              AND s.workspace_binding_id=i.workspace_binding_id AND b.workspace_binding_id=i.workspace_binding_id
              AND e.agent_id=i.agent_id AND e.workspace_id=i.workspace_id
        """, {**params, "authority_ref": author.authority_ref, "surface": author.surface,
               "client_intent_id": client_intent_id, "input_id": input_id}).fetchone()
        if row is None:
            raise _unavailable()
        return QueuedReceipt(
            row["input_id"], row["enqueue_sequence"], row["input_revision"], row["queue_revision"],
            InputDeliveryState(row["status"]), row["operation_id"], bool(row["possible_effect"]),
            steer_submitted=bool(row["steer_submitted"]), reorientation=bool(row["reorientation"]),
        )

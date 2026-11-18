"""Read one exact session's queue without changing its state."""

from dataclasses import dataclass

from ..adapters.outbound.sqlite.session_interaction import _scope_params
from ..domain.runtime_context import RuntimeRequestContext
from ..domain.session_interaction import (
    MAX_SQLITE_INTEGER,
    InputAuthor,
    InputDeliveryState,
    InputScope,
    may_cancel,
)
from ..errors import ErrorCode, OktoNexusError
from .execution_session_views import read_execution_session

MAX_QUEUE_PAGE = 50


@dataclass(frozen=True, slots=True)
class InputQueueCursor:
    scope: InputScope
    after_sequence: int


@dataclass(frozen=True, slots=True)
class InputQueueItem:
    input_id: str
    sequence: int
    input_revision: int
    status: InputDeliveryState
    operation_id: str | None
    possible_effect: bool
    can_cancel: bool


@dataclass(frozen=True, slots=True)
class InputQueuePage:
    queue_revision: int
    paused: bool
    items: tuple[InputQueueItem, ...]
    next_cursor: InputQueueCursor | None
    pause_capability_revision: str | None = None


def _unavailable() -> OktoNexusError:
    return OktoNexusError(ErrorCode.NOT_FOUND, "The input queue was not found in this scope.")


def read_session_input_queue(
    factory, *, access, resolve_human, scope: InputScope, author: InputAuthor | None,
    cursor: InputQueueCursor | None = None, limit: int = 25, pending_only: bool = False,
    pause_revision_for=None,
) -> InputQueuePage:
    """Return metadata in FIFO order within one authorized database snapshot.

    Each page carries the current queue revision. The stable sequence cursor
    can advance across revisions but cannot cross session scopes. ``can_cancel``
    is queue eligibility. A cancellation still checks live authority and CAS.
    """
    if type(limit) is not int or not 1 <= limit <= MAX_QUEUE_PAGE:
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Invalid input queue page limit.")
    if cursor is not None and (
        type(cursor) is not InputQueueCursor or cursor.scope != scope
        or type(cursor.after_sequence) is not int or not 1 <= cursor.after_sequence <= MAX_SQLITE_INTEGER
    ):
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "The input queue cursor does not match this scope.")
    # A newly signed-in viewer may have no durable author reference yet.
    # The caller still verifies their login and the read cannot acquire ownership.
    if not resolve_human(author.authority_ref if author else None):
        raise _unavailable()

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
        if (current_scope["session_owner_generation"] != scope.generation.value
                or any(current_scope[key] != value for key, value in params.items() if key != "owner_generation")):
            raise _unavailable()

        queue = uow.connection.execute("""
            SELECT q.revision, q.paused_owner_generation
            FROM execution_sessions s
            JOIN execution_bindings b ON b.server_id=s.server_id AND b.executor_id=s.executor_id AND b.binding_id=s.binding_id
            JOIN execution_workspace_bindings w ON w.server_id=s.server_id AND w.executor_id=s.executor_id
                AND w.workspace_binding_id=s.workspace_binding_id AND w.workspace_id=s.workspace_id
            JOIN agent_endpoints e ON e.endpoint_id=b.endpoint_id
            LEFT JOIN session_interaction_queues q ON q.server_id=s.server_id AND q.executor_id=s.executor_id
                AND q.session_id=s.session_id
            WHERE s.server_id=:server_id AND s.executor_id=:executor_id AND s.session_id=:session_id
              AND s.owner_generation=:owner_generation AND s.binding_id=:binding_id AND s.workspace_id=:workspace_id
              AND s.workspace_binding_id=:workspace_binding_id AND b.workspace_binding_id=:workspace_binding_id
              AND e.agent_id=:agent_id AND e.workspace_id=:workspace_id
        """, params).fetchone()
        if queue is None:
            raise _unavailable()
        revision = queue["revision"] or 0
        paused = queue["paused_owner_generation"] is not None
        pause_revision = (pause_revision_for(uow, scope, not paused)
                          if pause_revision_for is not None and revision < MAX_SQLITE_INTEGER else None)
        if queue["revision"] is None:
            return InputQueuePage(0, False, (), None, pause_revision)

        rows = uow.connection.execute("""
            SELECT input_id, enqueue_sequence, input_revision, status, operation_id, possible_effect,
                (authority_ref=:authority_ref AND surface=:surface) AS own_input
            FROM session_interaction_inputs
            WHERE server_id=:server_id AND executor_id=:executor_id AND session_id=:session_id
              AND owner_generation=:owner_generation AND binding_id=:binding_id AND workspace_id=:workspace_id
              AND workspace_binding_id=:workspace_binding_id AND agent_id=:agent_id AND enqueue_sequence>:after_sequence
              AND (:pending_only=0 OR status NOT IN ('ACCEPTED_NATIVE', 'EXPIRED', 'CANCELLED'))
            ORDER BY enqueue_sequence LIMIT :fetch_limit
        """, {**params, "authority_ref": author.authority_ref if author else None,
               "surface": author.surface if author else None,
               "after_sequence": cursor.after_sequence if cursor else 0, "fetch_limit": limit + 1,
               "pending_only": pending_only}).fetchall()

        items = []
        for row in rows[:limit]:
            status = InputDeliveryState(row["status"])
            possible_effect = bool(row["possible_effect"])
            can_cancel = (bool(row["own_input"]) and may_cancel(status) and row["operation_id"] is None
                          and not possible_effect and MAX_SQLITE_INTEGER not in (revision, row["input_revision"]))
            items.append(InputQueueItem(row["input_id"], row["enqueue_sequence"], row["input_revision"],
                                        status, row["operation_id"], possible_effect, can_cancel))
        following = InputQueueCursor(scope, items[-1].sequence) if len(rows) > limit else None
        return InputQueuePage(revision, paused, tuple(items), following, pause_revision)

"""Bind managed work to the existing canonical handoff and claim epoch."""

from nexus_connector_core.protocol import canonical_json

from ..domain.execution_principal import current_execution_principal
from .execution_tools import denied


def remember_claim(uow, handoff):
    principal = current_execution_principal.get()
    if principal is None:
        return
    scope = dict(principal.scope)
    uow.connection.execute(
        'INSERT INTO execution_tool_claims(handoff_id,claim_epoch,server_id,executor_id,session_id,scope_json) '
        'VALUES (?,?,?,?,?,?)', (handoff.handoff_id, handoff.claim_epoch,
        scope['server_id'], scope['executor_id'], scope['session_id'], canonical_json(scope).decode()))


def require_claim(uow, *, handoff_id, claim_epoch):
    principal = current_execution_principal.get()
    if principal is None:
        return
    row = uow.connection.execute(
        'SELECT scope_json FROM execution_tool_claims WHERE handoff_id=? AND claim_epoch=?',
        (handoff_id, claim_epoch)).fetchone()
    if row is None or row['scope_json'] != canonical_json(dict(principal.scope)).decode():
        raise denied('This claim belongs to a different session or execution generation.')

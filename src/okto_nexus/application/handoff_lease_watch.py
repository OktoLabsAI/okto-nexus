"""Read helpers for the handoff lease watch (#92).

The helpers read the connection of the caller's unit of work. They never write.
Progress is any message from the claimant to the creator after the lease start.
System notices and read receipts do not count as progress.
"""
from __future__ import annotations

import json
from typing import Any

from ..domain.base import iso_plus, iso_to_epoch

# Silence and expiry notices and containment notices are sent in the name of the
# claimant. Read receipts ("message.read_receipt") are also sent in its name. The
# server writes all of them, so they are not progress. Plain text and agent JSON are.
_NOT_PROGRESS = ("m.message_id NOT LIKE 'msg\\_claimant\\_contained\\_%' ESCAPE '\\' "
                 "AND COALESCE(CASE WHEN json_valid(m.body) THEN json_extract(m.body,'$.kind') END,'') "
                 "NOT LIKE 'handoff.%' "
                 "AND COALESCE(CASE WHEN json_valid(m.body) THEN json_extract(m.body,'$.kind') END,'') "
                 "NOT LIKE 'message.%'")


def lease_start(lease_expires_at: str, ttl_seconds: int) -> str:
    """Return the start of the lease in canonical form."""
    return iso_plus(lease_expires_at, -int(ttl_seconds))


def last_progress_at(conn, *, claimant: str, creator: str, since: str) -> str | None:
    """Return the time of the last claimant message to the creator after ``since``."""
    row = conn.execute(
        "SELECT MAX(m.created_at) FROM messages m JOIN message_deliveries d USING(message_id) "
        "WHERE m.from_agent_id=? AND d.recipient_agent_id=? AND m.created_at>=? AND " + _NOT_PROGRESS,
        (claimant, creator, since)).fetchone()
    return row[0] if row else None


def claimant_session(conn, *, workspace_id: str, agent_id: str) -> dict[str, Any] | None:
    """Return the state of the newest runtime session of ``agent_id`` or None.

    ``last_turn_end_at`` is the time of the last final turn receipt.
    ``last_error_code`` is the error code of that receipt.
    """
    op = conn.execute(
        "SELECT server_id,executor_id,session_id FROM execution_operations "
        "WHERE subject_agent_id=? AND workspace_id=? ORDER BY created_at DESC LIMIT 1",
        (agent_id, workspace_id)).fetchone()
    if op is None:
        return None
    session = conn.execute(
        "SELECT lifecycle_state FROM execution_sessions WHERE server_id=? AND executor_id=? AND session_id=?",
        (op['server_id'], op['executor_id'], op['session_id'])).fetchone()
    turn = conn.execute(
        "SELECT r.received_at,r.error_code FROM execution_operations o JOIN execution_receipts r "
        "ON r.server_id=o.server_id AND r.executor_id=o.executor_id AND r.operation_id=o.operation_id "
        "WHERE o.server_id=? AND o.executor_id=? AND o.session_id=? AND o.action='turn.submit' "
        "AND r.stage IN ('SUCCEEDED','FAILED','CANCELLED') ORDER BY r.received_at DESC LIMIT 1",
        (op['server_id'], op['executor_id'], op['session_id'])).fetchone()
    return {'state': session['lifecycle_state'] if session else None,
            'last_turn_end_at': turn['received_at'] if turn else None,
            'last_error_code': turn['error_code'] if turn else None}


def earliest_due(conn, horizon: str) -> str | None:
    """Return the earliest claimed lease end when it is at or before ``horizon``.

    One probe of the partial index of migration 156. It returns None when no
    claimed handoff exists or none is due.
    """
    row = conn.execute("SELECT MIN(lease_expires_at) FROM handoffs WHERE status='CLAIMED'").fetchone()
    value = row[0] if row else None
    return value if value is not None and value <= horizon else None


def silence_marked(conn, handoff_id: str, claim_epoch: int) -> bool:
    return conn.execute('SELECT 1 FROM handoff_silence_notices WHERE handoff_id=? AND claim_epoch=?',
                        (handoff_id, claim_epoch)).fetchone() is not None


def contained(conn, *, claimant: str, handoff_id: str, since: str) -> bool:
    """Return True when a containment notice exists for this claim."""
    return conn.execute(
        "SELECT 1 FROM messages WHERE from_agent_id=? AND created_at>=? "
        "AND message_id LIKE 'msg\\_claimant\\_contained\\_%' ESCAPE '\\' AND subject=? LIMIT 1",
        (claimant, since, f'handoff {handoff_id} claimant session contained')).fetchone() is not None


def minutes(a: str, b: str) -> int:
    """Return whole minutes from ``a`` to ``b``; never negative."""
    return max(0, int((iso_to_epoch(b) - iso_to_epoch(a)) // 60))

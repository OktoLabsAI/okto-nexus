"""Read the correlated Codex token lower bound from an owned campaign journal."""

from contextlib import closing
from dataclasses import dataclass
import json
from pathlib import Path
import sqlite3


USAGE_NOTIFICATION = 'thread/tokenUsage/updated'


class UnconfirmedUsage(ValueError):
    """The journal cannot justify accounting for the requested turn."""


@dataclass(frozen=True)
class TurnUsage:
    turn_id: str
    tokens: int | None
    terminal_outcome: str | None


def _total(raw):
    fields = ('totalTokens', 'inputTokens', 'cachedInputTokens', 'outputTokens', 'reasoningOutputTokens')
    value = json.loads(raw)
    if not isinstance(value, dict) or any(type(value.get(key)) is not int or value[key] < 0 for key in fields):
        raise UnconfirmedUsage('INVALID_USAGE_COUNTER')
    total, incoming, cached, outgoing, reasoning = (value[key] for key in fields)
    if total != incoming + outgoing or cached > incoming or reasoning > outgoing:
        raise UnconfirmedUsage('INCONSISTENT_USAGE_COUNTER')
    return total


def read_turn_usage(journal: Path, scope: tuple[str, str, str, str], *, thread_id: str,
                    operation_id: str) -> TurnUsage | None:
    """Return accounting only after a usage report names the requested turn."""
    turn = read_turn_state(journal, scope, thread_id=thread_id, operation_id=operation_id)
    return turn if turn is not None and turn.tokens is not None else None


def read_turn_state(journal: Path, scope: tuple[str, str, str, str], *, thread_id: str,
                    operation_id: str) -> TurnUsage | None:
    """Return the exact started turn even when its first usage report is pending.

    Read just the event metadata for the supplied namespace and stream epoch.
    Each cumulative increment belongs to the exact turn that reported it,
    including increments for a reorientation within the same turn.
    """
    if len(scope) != 4 or not all(isinstance(value, str) and value for value in (*scope, thread_id, operation_id)):
        raise UnconfirmedUsage('EXACT_USAGE_SCOPE_REQUIRED')
    with closing(sqlite3.connect(journal.resolve(strict=True).as_uri() + '?mode=ro', uri=True, timeout=1)) as db:
        db.execute('PRAGMA query_only=ON')
        db.execute('BEGIN')
        stream = db.execute('''SELECT next_sequence,compacted_sequence FROM event_streams
            WHERE server_id=? AND executor_id=? AND session_id=? AND stream_epoch=?''', scope).fetchone()
        if stream is None:
            return None
        next_sequence, compacted = stream
        if compacted != 0 or not 1 <= next_sequence <= 50_001:
            raise UnconfirmedUsage('JOURNAL_COVERAGE_GAP')
        rows = db.execute('''SELECT sequence,json_extract(body,'$.operation_id'),
            json_extract(body,'$.native_type'),
            json_extract(body,'$.payload.delivery_phase'),json_extract(body,'$.payload.delivery_outcome'),
            json_extract(body,'$.payload.thread_id'),json_extract(body,'$.payload.turn_id'),
            json_type(body,'$.payload.tokenUsage'),json_type(body,'$.payload.tokenUsage.total'),
            json_extract(body,'$.payload.tokenUsage.total')
            FROM events WHERE server_id=? AND executor_id=? AND session_id=? AND stream_epoch=?
            ORDER BY sequence LIMIT 50001''', scope).fetchall()
    if len(rows) != next_sequence - 1 or any(seq != index for index, (seq, *_) in enumerate(rows, 1)):
        raise UnconfirmedUsage('JOURNAL_COVERAGE_GAP')
    owners, turns, totals, terminal = {}, {}, {}, {}
    previous_total = 0
    for _, owner, native_type, phase, outcome, thread, turn, usage_type, total_type, usage in rows:
        if phase == 'started':
            if (thread != thread_id or not isinstance(turn, str) or not turn
                    or not isinstance(owner, str) or not owner or owner in turns or turn in owners):
                raise UnconfirmedUsage('TURN_IDENTITY_CHANGED')
            turns[owner], owners[turn] = turn, owner
        elif phase == 'terminal':
            if (thread != thread_id or not isinstance(turn, str) or owners.get(turn) != owner or not owner
                    or outcome not in ('success', 'failed', 'interrupted') or turn in terminal):
                raise UnconfirmedUsage('TERMINAL_OUTCOME_UNCORRELATED')
            terminal[turn] = outcome
        if native_type != USAGE_NOTIFICATION:
            if usage_type is not None:
                raise UnconfirmedUsage('UNEXPECTED_USAGE_NOTIFICATION')
            continue
        if total_type != 'object':
            raise UnconfirmedUsage('INVALID_USAGE_COUNTER')
        if thread != thread_id or turn not in owners or owner not in (None, owners[turn]):
            raise UnconfirmedUsage('USAGE_TURN_UNCORRELATED')
        total = _total(usage)
        if total < previous_total:
            raise UnconfirmedUsage('USAGE_COUNTER_REGRESSED')
        totals[turn] = totals.get(turn, 0) + total - previous_total
        previous_total = total
    target = turns.get(operation_id)
    if target is None:
        return None
    return TurnUsage(target, totals.get(target), terminal.get(target))

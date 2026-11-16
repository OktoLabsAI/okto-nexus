"""Bounded metadata-only RO Codex journal accounting for two NEW local calls."""
from pathlib import Path
from contextlib import closing
import json
import sqlite3


def require(value, reason):
    if not value:
        raise ValueError(reason)


def owned(root, path):
    root, path = Path(root).absolute(), Path(path).absolute()
    require(path.is_relative_to(root), 'OUTSIDE_OWN_ROOT')
    # Reject lexical junctions/symlinks before resolution, including ancestors.
    for part in (path, *path.parents):
        if part.exists():
            st = part.lstat()
            require(not part.is_symlink() and not getattr(st, 'st_file_attributes', 0) & 0x400,
                    'REPARSE_PATH_REFUSED')
    require(path.resolve().is_relative_to(root.resolve()), 'OUTSIDE_OWN_ROOT')
    return path


def summarize(rows, *, watermark, count, minimum, maximum, compacted):
    require(type(watermark) is int and 0 <= watermark <= 50000, 'WATERMARK_LIMIT')
    require(compacted == 0 and count == watermark and
            (watermark == 0 or (minimum == 1 and maximum == watermark)), 'JOURNAL_COVERAGE_GAP')
    threads, turns = {}, {}
    for row in rows:
        kind = row['native_type']
        thread, turn = row['thread_id'], row['turn_id']
        require(isinstance(thread, str) and thread and isinstance(turn, str) and turn,
                'NATIVE_SCOPE_UNKNOWN')
        key = (thread, turn)
        state = turns.setdefault(key, {'started': False, 'terminal': False, 'usage': False})
        if kind == 'turn/started':
            require(row['phase'] == 'started' and not state['terminal'], 'TURN_ORDER_CHANGED')
            state['started'] = True
        elif kind == 'turn/completed':
            require(row['phase'] == 'terminal' and row['outcome'] in ('success', 'failed', 'interrupted'),
                    'TURN_TERMINAL_UNKNOWN')
            state['terminal'] = True
        else:
            data = json.loads(row['usage']) if isinstance(row['usage'], str) else row['usage']
            names = ('totalTokens', 'inputTokens', 'cachedInputTokens', 'outputTokens', 'reasoningOutputTokens')
            require(isinstance(data, dict) and all(type(data.get(n)) is int and data[n] >= 0 for n in names),
                    'USAGE_SHAPE_UNKNOWN')
            require(data['cachedInputTokens'] <= data['inputTokens'] and
                    data['reasoningOutputTokens'] <= data['outputTokens'], 'USAGE_SUBSET_INVALID')
            old = threads.get(thread)
            require(old is None or all(data[n] >= old[n] for n in names), 'USAGE_REGRESSION')
            threads[thread] = {n: data[n] for n in names}
            state['usage'] = True
    # Fresh isolated call permits exactly one native thread/turn, never aggregate old sessions.
    require(len(turns) <= 1 and len(threads) <= 1, 'UNEXPECTED_NATIVE_CALL')
    complete = bool(turns) and bool(threads) and all(all(t.values()) for t in turns.values())
    return {'observed_total': sum(t['totalTokens'] for t in threads.values()),
            'usage_seen': bool(threads), 'terminal_usage_covered': complete,
            'cursor': watermark, 'native_turns': len(turns), 'components': list(threads.values()),
            'cache_is_input_subset': True, 'reasoning_is_output_subset': True,
            'billing_final': False}


def journal_snapshot(root, path, scope):
    path = owned(root, path)
    require(path.is_file(), 'JOURNAL_NOT_YET_AVAILABLE')
    require(len(scope) == 4 and all(isinstance(s, str) and s for s in scope), 'JOURNAL_SCOPE_REQUIRED')
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=1)) as db:
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA query_only=ON')
        db.execute('BEGIN')
        row = db.execute('SELECT next_sequence-1 AS watermark,compacted_sequence FROM event_streams '
                         'WHERE server_id=? AND executor_id=? AND session_id=? AND stream_epoch=?', scope).fetchone()
        require(row is not None, 'STREAM_NOT_YET_AVAILABLE')
        counts = db.execute('SELECT COUNT(*) AS n,MIN(sequence) AS lo,MAX(sequence) AS hi FROM events '
                            'WHERE server_id=? AND executor_id=? AND session_id=? AND stream_epoch=?', scope).fetchone()
        require(counts['n'] <= 50000, 'EVENT_LIMIT')
        # SQL selects only usage and correlation metadata; never event text, commands or secrets.
        events = db.execute("""SELECT sequence,
            json_extract(body,'$.native_type') AS native_type,
            json_extract(body,'$.payload.thread_id') AS thread_id,
            json_extract(body,'$.payload.turn_id') AS turn_id,
            json_extract(body,'$.payload.delivery_phase') AS phase,
            json_extract(body,'$.payload.delivery_outcome') AS outcome,
            json_extract(body,'$.payload.tokenUsage.total') AS usage
            FROM events WHERE server_id=? AND executor_id=? AND session_id=? AND stream_epoch=?
            AND json_extract(body,'$.native_type') IN ('turn/started','turn/completed','thread/tokenUsage/updated')
            ORDER BY sequence LIMIT 50001""", scope).fetchall()
        return summarize(events, watermark=row['watermark'], count=counts['n'], minimum=counts['lo'],
                         maximum=counts['hi'], compacted=row['compacted_sequence'])

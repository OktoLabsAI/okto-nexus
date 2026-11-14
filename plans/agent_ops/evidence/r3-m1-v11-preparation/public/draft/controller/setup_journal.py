"""Read-only monitor for one standalone Nexus setup journal in an owned home.

Never presents this namespace as canonical Server session history. No raw text
or event payload is returned. Attribution is serial ownership, not a test_id
mapping that the product does not expose.
"""
import json
from pathlib import Path
import re
import sqlite3
import time
from independent_journal import ReadOnly,JournalUnknown


class SetupUnknown(ValueError):
    pass


def require(value, reason):
    if not value:
        raise SetupUnknown(reason)


def safe_path(path, owner):
    path, owner = Path(path), Path(owner).resolve()
    require(path.resolve().is_relative_to(owner), 'SETUP_PATH_OUTSIDE_OWNER')
    for item in (path, *path.parents):
        if item == owner.parent:
            break
        require(not item.is_symlink() and not item.is_junction(), 'SETUP_PATH_LINK')
    return path.resolve()


def arm(owner_home, campaign_root, previous=()):
    home = safe_path(owner_home, campaign_root)
    require(home.is_dir(), 'OWNED_HOME_REQUIRED')
    root = safe_path(home/'connection-tests', home)
    allowed = set()
    for old in previous:
        require(settled(old) and old['home']==str(home) and old['journal'], 'PREVIOUS_SETUP_NOT_CLOSED')
        journal = safe_path(old['journal'],home)
        require(list((journal.stat().st_dev,journal.stat().st_ino))==old['journal_identity'], 'PREVIOUS_JOURNAL_CHANGED')
        allowed.add(journal.parent)
    require(not root.exists() or root.is_dir() and set(root.iterdir())==allowed, 'SETUP_ROOT_NOT_OWNED')
    return {'home': str(home), 'root': str(root), 'home_identity': list((home.stat().st_dev, home.stat().st_ino)),
            'prior_journals': [str(p/'journal.db') for p in sorted(allowed)],
            'journal': None, 'journal_identity': None, 'cursor': 0, 'high_water': 0,
            'thread': None, 'turn': None, 'started': False, 'terminal': False, 'usage_seen': False,
            'caught_up': False, 'result_stage': None, 'close_stage': None, 'owned_slot_released':False}


def poll(record, known_journals=(), pending_new=False, *, io=None):
    owned=io is None
    if owned:io=ReadOnly(record['home'])
    started=io.clock();before=len(io.initializations)
    try:
        value=_poll(record,known_journals,pending_new,io=io)
        initialization=sum(item['elapsed_ms']/1000 for item in io.initializations[before:])
        io.check_aggregate()
        if io.clock()-started-initialization>=io.budget:
            error=JournalUnknown('SETUP_READ_BUDGET_EXCEEDED')
            error.m1_reader_diagnostic={'phase':'snapshot_read','budget_ms':io.budget*1000,
                'elapsed_ms':(io.clock()-started-initialization)*1000}
            io.failed=True;io._release()
            raise error
        return value
    finally:
        if owned:io.close()


def _poll(record, known_journals=(), pending_new=False, *, io):
    home = Path(record['home'])
    require(list((home.stat().st_dev, home.stat().st_ino)) == record['home_identity'], 'OWNER_CHANGED')
    root = safe_path(record['root'], home)
    if not root.exists():
        return record
    children = list(root.iterdir())
    known = {Path(p).parent for p in known_journals} | {Path(p).parent for p in record['prior_journals']}
    unknown = set(children)-known
    require(len(unknown) <= (1 if record['journal'] is None or pending_new else 0), 'MULTIPLE_SETUP_JOURNALS')
    if record['journal'] is not None:
        directory = Path(record['journal']).parent
        require(directory in children, 'SETUP_JOURNAL_MISSING')
    else:
        children = sorted(unknown)
        if not children: return record
        directory = children[0]
    if not children:
        return record
    directory = safe_path(directory, home)
    require(directory.is_dir() and re.fullmatch('[0-9a-f]{32}', directory.name), 'SETUP_DIRECTORY_UNKNOWN')
    path = safe_path(directory/'journal.db', home)
    if not path.exists():
        return record
    identity = list((path.stat().st_dev, path.stat().st_ino))
    if record['journal'] is None:
        record['journal'], record['journal_identity'] = str(path), identity
    require(record['journal'] == str(path) and record['journal_identity'] == identity, 'SETUP_JOURNAL_REPLACED')
    with io.open(path) as db:
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {'events','event_streams','operations_v2'} <= tables:
            return record  # newly created DB may still be initializing; deadline still applies
        streams = db.execute('SELECT server_id,executor_id,session_id,stream_epoch,next_sequence,compacted_sequence FROM event_streams').fetchall()
        require(len(streams) <= 1, 'SETUP_MULTIPLE_STREAMS')
        if not streams:
            return record
        source = streams[0]
        require(source[:4] == ('connection-test', 'local', 'session', 'epoch'), 'SETUP_NAMESPACE_UNEXPECTED')
        watermark = source[4]-1
        require(source[5] <= record['cursor'] <= watermark, 'SETUP_EVENT_GAP')
        # Project only usage and correlation metadata inside SQLite. No model
        # output, prompt, tool argument, approval body or auth payload is read.
        rows = db.execute("SELECT sequence,json_extract(body,'$.native_type'),json_extract(body,'$.operation_id'),"
            "json_extract(body,'$.payload.thread_id'),json_extract(body,'$.payload.turn_id'),"
            "json_extract(body,'$.payload.tokenUsage.total.totalTokens'),"
            "json_type(body,'$.payload.tokenUsage.total.totalTokens'),"
            "json_extract(body,'$.payload.delivery_phase'),json_extract(body,'$.payload.delivery_outcome') "
            'FROM events WHERE sequence>? AND sequence<=? ORDER BY sequence LIMIT 1000',
            (record['cursor'], watermark)).fetchall()
        receipt = db.execute("SELECT stage FROM operations_v2 WHERE server_id='connection-test' AND executor_id='local' AND operation_id='turn' AND session_id='session'").fetchone()
        close = db.execute("SELECT stage FROM operations_v2 WHERE server_id='connection-test' AND executor_id='local' AND operation_id='close' AND session_id='session'").fetchone()
        slot = db.execute("SELECT released FROM owned_slot_reservations WHERE server_id='connection-test' AND executor_id='local' AND operation_id='open' AND session_id='session'").fetchone()
        for sequence, method, operation, thread, turn, total, total_type, phase, outcome in rows:
            require(sequence == record['cursor']+1, 'SETUP_EVENT_GAP')
            if method in ('turn/started','turn/completed','thread/tokenUsage/updated'):
                require(type(thread) is str and thread and type(turn) is str and turn, 'SETUP_CORRELATION_MISSING')
                require(record['thread'] in (None, thread) and record['turn'] in (None, turn), 'SETUP_MULTIPLE_TURNS')
                record['thread'], record['turn'] = thread, turn
                if method == 'thread/tokenUsage/updated':
                    require(operation in (None, 'turn') and total_type=='integer' and type(total) is int and record['high_water'] <= total <= 2**63-1,
                            'SETUP_USAGE_INVALID')
                    record['high_water'], record['usage_seen'] = total, True
                else:
                    require(operation == 'turn', 'SETUP_OPERATION_UNEXPECTED')
                    if method == 'turn/started':
                        require(phase == 'started' and not record['terminal'], 'SETUP_START_INVALID')
                        record['started'] = True
                    else:
                        require(phase == 'terminal' and outcome in ('success','failed','interrupted'), 'SETUP_TERMINAL_INVALID')
                        record['terminal'] = True
            record['cursor'] = sequence
        require(rows or record['cursor'] == watermark, 'SETUP_EVENT_GAP')
        record['caught_up'] = record['cursor'] == watermark
        record['result_stage'] = receipt[0] if receipt else None
        record['close_stage'] = close[0] if close else None
        record['owned_slot_released'] = slot is not None and slot[0]==1
    return record


def settled(record):
    return (record['started'] and record['terminal'] and record['usage_seen'] and record['caught_up']
            and record['result_stage'] in ('SUCCEEDED','FAILED','CANCELLED')
            # Installed close_runtime._run_policy_close commits SUBMITTED for
            # the standalone (non-R4) context after physical stop and release.
            and record['close_stage'] in ('SUBMITTED','SUCCEEDED') and record['owned_slot_released'])

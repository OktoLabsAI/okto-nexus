"""Allowlisted metadata only. No credential stores, payloads or productive APIs."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import sqlite3
import time

AGENTS = ('m1v12-local', 'm1-sonnet-remote')
MAX_ROWS = 2048
SERVER = {
    'execution_operations': 'server_id executor_id operation_id subject_agent_id binding_id workspace_id session_id action admission_state created_at parent_operation_id',
    'execution_receipts': 'server_id executor_id operation_id receipt_revision stage possible_effect retry_safe error_code received_at',
    'execution_sessions': 'server_id executor_id session_id binding_id workspace_id open_operation_id owner_generation lifecycle_state stream_epoch lease_state containment_reason contained_at',
    'execution_leases': 'server_id executor_id session_id lease_serial grant_id authorization_revision configuration_revision owner_generation credential_epoch valid_until_server status binding_revision source_grant_revision issued_at applied_at',
    'runtime_execution_grants': 'grant_id represented_agent_id workspace_id endpoint_id expires_at revoked_at revision max_executions used_executions no_expiry unlimited_actions',
    'execution_tool_claims': 'handoff_id claim_epoch server_id executor_id session_id',
    'execution_event_watermarks': 'server_id executor_id session_id stream_epoch committed_contiguous projected_through gap_state',
    'execution_native_actions': 'server_id executor_id session_id action_id action handoff_id claim_epoch created_at',
}
CORE = {
    'operations_v2': 'server_id executor_id operation_id session_id stage possible_effect retry_safe error_code',
    'operation_actions': 'server_id executor_id operation_id action terminal_event_expected',
    'session_claims': 'server_id executor_id session_id operation_id reconciliation_pending release_id',
    'owned_slot_reservations': 'server_id executor_id session_id operation_id released',
    'session_lease_state': 'server_id executor_id session_id connection_generation owner_generation authorization_revision configuration_revision revoked',
    'event_streams': 'server_id executor_id session_id stream_epoch next_sequence acked_sequence compacted_sequence',
}
SLOTS = {
    'owned_slot_reservations': CORE['owned_slot_reservations'],
    'execution_capacity_reservations': 'reservation_id server_id executor_id attempt_id session_id state revision deadline opening_started',
    'execution_turn_slots': 'server_id executor_id session_id operation_id active',
}

def require(value, code):
    if not value:
        raise RuntimeError(code)

def stamp():
    return datetime.now(timezone.utc).isoformat()

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()

def projected_database(path, kind):
    path = Path(path)
    require(path.is_file(), 'DATABASE_MISSING')
    started = time.monotonic()
    conn = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=1)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute('PRAGMA query_only=ON')
        conn.set_progress_handler(lambda: int(time.monotonic() - started > 5), 500)
        conn.execute('BEGIN')
        tables = SERVER if kind == 'server' else CORE if kind == 'core' else SLOTS
        answer = {}
        for table, selected in tables.items():
            columns = selected.split()
            where, params = '', ()
            if kind == 'server':
                scoped = 'SELECT operation_id FROM execution_operations WHERE subject_agent_id IN (?,?)'
                sessions = 'SELECT DISTINCT session_id FROM execution_operations WHERE subject_agent_id IN (?,?) AND session_id IS NOT NULL'
                if table == 'execution_operations':
                    where = ' WHERE subject_agent_id IN (?,?)'
                elif table == 'runtime_execution_grants':
                    where = ' WHERE represented_agent_id IN (?,?)'
                elif table == 'execution_receipts':
                    where = ' WHERE operation_id IN (' + scoped + ')'
                else:
                    where = ' WHERE session_id IN (' + sessions + ')'
                params = AGENTS
            query = 'SELECT ' + ','.join(columns) + ' FROM ' + table + where
            query += ' ORDER BY ' + ','.join(str(i + 1) for i in range(len(columns))) + ' LIMIT ' + str(MAX_ROWS + 1)
            rows = [dict(row) for row in conn.execute(query, params)]
            require(len(rows) <= MAX_ROWS, 'PROJECTION_ROW_BOUND_EXCEEDED')
            require(all(not isinstance(v, (bytes, bytearray)) and (not isinstance(v, str) or len(v) <= 512)
                        for row in rows for v in row.values()), 'PROJECTION_VALUE_BOUND_EXCEEDED')
            answer[table] = {'count': len(rows), 'sha256': hashlib.sha256(canonical(rows)).hexdigest(), 'rows': rows}
        require(time.monotonic() - started <= 5, 'PROJECTION_TIME_BOUND_EXCEEDED')
        return {'path': str(path), 'kind': kind, 'tables': answer, 'observed_at': stamp()}
    finally:
        try:
            conn.rollback()
        finally:
            conn.close()

def capture(plan):
    root = Path(plan['campaign_root']).resolve()
    local = root / 'nexus-home/core-runtime'
    journals = sorted(local.glob('session-*.db'))
    require(0 < len(journals) <= 32, 'LOCAL_JOURNAL_SET_UNCONFIRMED')
    choices = [(root / 'nexus-home/nexus.db', 'server'),
               (root / 'connector-state/executor-journal.db', 'core'),
               (root / 'connector-state/owned-slots.db', 'slots'),
               (local / 'owned-slots.db', 'slots'), *[(p, 'core') for p in journals]]
    result = {'started_at': stamp(), 'status': 'READ_ONLY_KNOWN_HISTORY', 'databases': {},
              'cross_database_atomicity_claimed': False, 'new_provider_calls': 0, 'productive_requests': 0,
              'credential_stores_read': False, 'payloads_read': False}
    for path, kind in choices:
        require(path.resolve().is_relative_to(root), 'PATH_OUTSIDE_CAMPAIGN')
        for part in [path, *path.parents]:
            require(not (getattr(part.lstat(), 'st_file_attributes', 0) & 0x400), 'REPARSE_PATH_REFUSED')
            if part == root:
                break
        result['databases'][path.relative_to(root).as_posix()] = projected_database(path, kind)
    server = result['databases']['nexus-home/nexus.db']['tables']
    require(server['execution_operations']['count'] > 0 and server['runtime_execution_grants']['count'] > 0,
            'NONEMPTY_HISTORY_REQUIRED')
    result['finished_at'] = stamp()
    return result

def compare(before, after):
    old, new = before['databases'], after['databases']
    changes = []
    for name in sorted(set(old) | set(new)):
        if name not in old or name not in new:
            changes.append({'database': name, 'change': 'DATABASE_SET_CHANGED'})
            continue
        a, b = old[name]['tables'], new[name]['tables']
        for table in sorted(set(a) | set(b)):
            if table not in a or table not in b or a[table]['rows'] != b[table]['rows']:
                changes.append({'database': name, 'table': table, 'change': 'METADATA_CHANGED'})
    return {'status': 'HISTORY_UNCHANGED' if not changes else 'CHANGES_REQUIRE_CANONICAL_RECONCILIATION',
            'changes': changes, 'same_operations_receipts_grants_claims_slots_and_streams': not changes,
            'productive_replay_inferred_safe': False, 'active_operation_survival_claimed': False,
            'all_work_settled_inferred': False}

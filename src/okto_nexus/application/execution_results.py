"""Bounded output projection from authenticated, contiguous Core events."""

OUTPUT_LIMIT = 1024 * 1024


def project_execution_result(conn, *, event, received_at):
    operation_id = event.get('operation_id')
    if operation_id is None:
        return
    key = (event['server_id'], event['executor_id'], operation_id)
    operation = conn.execute(
        'SELECT action,session_id FROM execution_operations WHERE server_id=? AND executor_id=? AND operation_id=?',
        key).fetchone()
    if not operation or operation['action'] not in ('turn.submit', 'turn.steer'):
        return
    if operation['session_id'] != event['session_id']:
        raise ValueError('Result operation is outside its session.')
    payload = event['payload']
    terminal = event['category'] == 'turn_state' and payload.get('delivery_phase') == 'terminal'
    output = payload.get('output_text')
    if not terminal and not isinstance(output, str):
        return
    row = conn.execute('SELECT * FROM execution_results WHERE server_id=? AND executor_id=? AND operation_id=?', key).fetchone()
    if row and row['terminal_sequence'] is not None:
        # Late observations cannot replace a committed terminal result.
        return
    if row and row['stream_epoch'] != event['stream_epoch']:
        raise ValueError('Result output belongs to another stream epoch.')
    text = row['output_text'] if row else ''
    truncated = bool(row['output_truncated']) if row else False
    count = row['output_event_count'] if row else 0
    if isinstance(output, str):
        if event['category'] == 'text_snapshot':
            text, truncated = '', False
        raw = output.encode('utf-8')
        available = OUTPUT_LIMIT - len(text.encode('utf-8'))
        truncated = truncated or len(raw) > available
        text += raw[:available].decode('utf-8', errors='ignore')
        count += 1
    conn.execute('INSERT INTO execution_results(server_id,executor_id,operation_id,session_id,stream_epoch,'
        'terminal_sequence,output_text,output_truncated,output_event_count,delivery_outcome,captured_at) '
        'VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(server_id,executor_id,operation_id) DO UPDATE SET '
        'terminal_sequence=excluded.terminal_sequence,output_text=excluded.output_text,'
        'output_truncated=excluded.output_truncated,output_event_count=excluded.output_event_count,'
        'delivery_outcome=excluded.delivery_outcome,captured_at=excluded.captured_at',
        (*key, event['session_id'], event['stream_epoch'], event['sequence'] if terminal else None,
         text, int(truncated), count, payload.get('delivery_outcome') if terminal else None, received_at))
    if terminal:
        project_domain_result(conn, server_id=key[0], executor_id=key[1], operation_id=key[2])


def project_domain_result(conn, *, server_id, executor_id, operation_id):
    """Join terminal output and receipt in either arrival order, exactly once."""
    import hashlib
    import json
    key = (server_id, executor_id, operation_id)
    row = conn.execute('SELECT r.*,m.domain_operation_id FROM execution_results r '
        'JOIN execution_domain_deliveries m USING(server_id,executor_id,operation_id) '
        'JOIN delivery_outbox o ON o.operation_id=m.domain_operation_id '
        'WHERE r.server_id=? AND r.executor_id=? AND r.operation_id=? '
        'AND r.terminal_sequence IS NOT NULL AND o.canonical_terminal_operation_id=r.operation_id', key).fetchone()
    if row is None:
        return
    receipt = conn.execute('SELECT stage FROM execution_receipts WHERE server_id=? AND executor_id=? AND operation_id=? '
        'ORDER BY receipt_revision DESC LIMIT 1', key).fetchone()
    if not receipt or receipt[0] != {'success': 'SUCCEEDED', 'failed': 'FAILED', 'interrupted': 'CANCELLED'}.get(row['delivery_outcome']):
        return
    identity = 'result_r4_' + hashlib.sha256(json.dumps(key, separators=(',', ':')).encode()).hexdigest()
    conn.execute('INSERT INTO runtime_results(result_id,payload,captured_at,operation_id,output_text,output_truncated,'
        'output_event_count,delivery_outcome,canonical_server_id,canonical_executor_id,canonical_operation_id) '
        'VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT DO NOTHING',
        (identity, json.dumps(dict(stream_epoch=row['stream_epoch'], terminal_sequence=row['terminal_sequence'])),
         row['captured_at'], row['domain_operation_id'], row['output_text'], row['output_truncated'],
         row['output_event_count'], row['delivery_outcome'], *key))


def canonical_result_matches(conn, row):
    """Revalidate publication provenance without inventing a harness event."""
    if not row.get('canonical_server_id'):
        return row['event_id'] is not None and row['terminal_event_id'] == row['event_id']
    source = conn.execute('SELECT r.* FROM execution_results r JOIN execution_domain_deliveries m '
        'USING(server_id,executor_id,operation_id) JOIN delivery_outbox o ON o.operation_id=m.domain_operation_id '
        'WHERE r.server_id=? AND r.executor_id=? AND r.operation_id=? AND m.domain_operation_id=? '
        'AND r.terminal_sequence IS NOT NULL AND o.canonical_terminal_operation_id=r.operation_id',
        (row['canonical_server_id'], row['canonical_executor_id'], row['canonical_operation_id'], row['operation_id'])).fetchone()
    return source is not None and all(source[k] == row[k] for k in (
        'output_text', 'output_truncated', 'output_event_count', 'delivery_outcome'))


def read_execution_result(conn, *, server_id, executor_id, operation_id):
    row = conn.execute('SELECT session_id,stream_epoch,terminal_sequence,output_text,output_truncated,'
        'output_event_count,delivery_outcome,captured_at FROM execution_results '
        'WHERE server_id=? AND executor_id=? AND operation_id=? AND terminal_sequence IS NOT NULL',
        (server_id, executor_id, operation_id)).fetchone()
    return dict(row) if row else None

"""Troubleshooting sees pre-open faults without leaking native execution payloads."""
import json
import hashlib

from fastapi.testclient import TestClient
from test_open_bootstrap import opening

from okto_nexus.application.execution_log import diagnostic_text, read_execution_log


def seed_fault(deps):
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE execution_dispatch_outbox SET last_error=?", (json.dumps({
            'code': 'CONNECTION_REFUSED', 'message': 'Cannot connect; api_key=secret-value',
            'stage': 'connect', 'prompt': 'PRIVATE PROMPT', 'env': {'TOKEN': 'PRIVATE TOKEN'}}),))
        row = uow.connection.execute('SELECT * FROM execution_operations LIMIT 1').fetchone()
        for revision in range(1, 4):
            uow.connection.execute('INSERT INTO execution_receipts(server_id,executor_id,operation_id,receipt_revision,intent_hash,stage,possible_effect,retry_safe,error_code,received_at) VALUES(?,?,?,?,?,?,?,?,?,?)',
                (row['server_id'], row['executor_id'], row['operation_id'], revision, row['intent_hash'],
                 'FAILED', 0, 0, 'PROVIDER_AUTH_REQUIRED', f'2001-01-0{revision}T12:00:00Z'))
        return dict(row)


def test_log_fault_filters_pagination_and_safe_projection(opening):
    deps = opening[0]
    operation = seed_fault(deps)
    query = dict(severity='error', agent_id=operation['subject_agent_id'], workspace_id=operation['workspace_id'])
    first = read_execution_log(deps.connection_factory, **query, limit=2)
    second = read_execution_log(deps.connection_factory, **query, limit=2, offset=first['next_offset'])
    assert first['has_more'] and not second['has_more']
    items = first['items'] + second['items']
    assert len({item['id'] for item in items}) == 4
    assert {item['source'] for item in items} == {'dispatch snapshot', 'receipt'}
    assert 'PRIVATE' not in json.dumps(items) and 'secret-value' not in json.dumps(items)
    assert '[redacted]' in json.dumps(items)
    dates = read_execution_log(deps.connection_factory, **query,
        since='2001-01-02T09:00:00-03:00', until='2001-01-02T09:00:00-03:00')
    assert len(dates['items']) == 1
    assert read_execution_log(deps.connection_factory, workspace_id='other')['items'] == []
    assert read_execution_log(deps.connection_factory, adapter_id='other')['items'] == []


def test_log_operator_gate_and_invalid_filters(opening):
    deps, app = opening[:2]
    seed_fault(deps)
    client = TestClient(app)
    try:
        url = '/api/v1/harness/execution-log'
        headers = {'Authorization': 'Bearer ' + app.state.test_agent_keys['operator']}
        response = client.get(url, headers=headers)
        assert response.status_code == 200, response.text
        assert response.headers['cache-control'] == 'no-store'
        assert response.json()['data']['items']
        for params in ({'severity': 'debug'}, {'offset': -1}, {'limit': 201},
                       {'since': 'yesterday'}, {'since': '2001-01-01'},
                       {'since': '2002-01-01T00:00:00Z', 'until': '2001-01-01T00:00:00Z'}):
            assert client.get(url, headers=headers, params=params).status_code in (400, 422)
        response = client.get(url, headers={'Authorization': 'Bearer ' + app.state.test_agent_keys['subject']})
        assert response.status_code == 403
    finally:
        client.close()


def test_log_committed_runtime_events_only(opening):
    deps = opening[0]
    with deps.connection_factory.unit_of_work() as uow:
        session = dict(uow.connection.execute('SELECT * FROM execution_sessions LIMIT 1').fetchone())
        scope = (session['server_id'], session['executor_id'], session['session_id'], 'log-test')
        uow.connection.execute('INSERT INTO execution_event_watermarks(server_id,executor_id,session_id,stream_epoch,committed_contiguous) VALUES(?,?,?,?,?)', (*scope, 2))
        for sequence, kind in enumerate(('error', 'text_delta', 'error'), 1):
            payload = json.dumps({'native_type': 'process_exit', 'payload': {'exit_code': 1, 'raw': 'PRIVATE NATIVE FRAME', 'stderr_tail': 'PRIVATE STDERR'}})
            uow.connection.execute('INSERT INTO execution_event_ingress(server_id,executor_id,session_id,stream_epoch,sequence,event_hash,event_type,payload_json,received_at) VALUES(?,?,?,?,?,?,?,?,?)',
                (*scope, sequence, 'sha256:' + hashlib.sha256(payload.encode()).hexdigest(), kind, payload, '2001-01-01T00:00:00Z'))
    items = read_execution_log(deps.connection_factory, severity='error')['items']
    assert len(items) == 1
    assert items[0]['code'] == 'process_exit'
    assert items[0]['details'] == {'exit_code': '1'}
    assert 'PRIVATE' not in json.dumps(items)


def test_diagnostic_text_redacts_credentials():
    assert diagnostic_text('Bearer abc.def secret=xyz sk-abc123') == 'Bearer [redacted] secret=[redacted] [redacted]'
    assert diagnostic_text({'input': 'private'}) is None
    assert len(diagnostic_text('x' * 10000)) == 2000

"""One-DB E16 composition: canonical domain writes, historical capture facts."""
import json
import os
import subprocess
from datetime import datetime, timedelta


def composed_delivery_case(tmp_path):
    from fastapi.testclient import TestClient
    from test_verification import _ok, _park, make_env

    from okto_nexus.adapters.inbound.http.app import build_app
    deps, tools, project_root = make_env(tmp_path)
    deps.config.feature_attention = True
    handoff = _park(tools, project_root, acceptance_criteria=['One delivery with three files'])
    with deps.connection_factory.unit_of_work(write=False) as uow:
        stored = dict(uow.connection.execute('SELECT * FROM handoffs WHERE handoff_id=?', (handoff,)).fetchone())
    workspace, epoch = stored['workspace_id'], stored['claim_epoch']
    now = deps.clock.now_iso()
    old = (datetime.fromisoformat(now) - timedelta(days=2)).isoformat(timespec='microseconds').replace('+00:00', 'Z')
    # These are migrated historical reader inputs, not runtime admission or
    # authority. CLOSED/DISCONNECTED, expired grant, empty actions, no leases.
    with deps.connection_factory.unit_of_work() as uow:
        c = uow.connection
        if not c.execute('SELECT 1 FROM execution_installation').fetchone():
            c.execute("INSERT INTO execution_installation VALUES(1,'backend-history-server','backend-history-executor',1,?)", (old,))
        server = c.execute('SELECT server_id FROM execution_installation WHERE singleton=1').fetchone()[0]
        executor = 'backend-history-executor'
        c.execute("INSERT INTO execution_executors(server_id,executor_id,kind,control_state,generation) VALUES(?,?,'embedded','DISCONNECTED',1)", (server, executor))
        c.execute("INSERT INTO agent_endpoints(endpoint_id,agent_id,workspace_id,adapter_id,protocol,enabled,activation_state,created_at,updated_at) VALUES('backend-history-endpoint','beta',?,'fixture','nxl-r4',0,'approved',?,?)", (workspace, old, old))
        c.execute("INSERT INTO execution_workspace_bindings(server_id,workspace_binding_id,executor_id,workspace_id,realization_handle,revision,status) VALUES(?,'backend-history-wxb',?,?,'history',1,'ACTIVE')", (server, executor, workspace))
        c.execute("INSERT INTO execution_bindings(server_id,binding_id,executor_id,endpoint_id,workspace_binding_id,candidate_ref,inventory_revision,realization_ref,realization_revision,binding_revision) VALUES(?,'backend-history-binding',?,'backend-history-endpoint','backend-history-wxb','history','history','history',1,1)", (server, executor))
        for op, action in [('backend-history-open', 'runtime.open')] + [(f'backend-history-turn-{i}', 'turn.submit') for i in range(3)]:
            c.execute("INSERT INTO execution_operations(server_id,executor_id,operation_id,subject_agent_id,actor_agent_id,binding_id,workspace_id,workspace_binding_id,session_id,action,intent_hash,semantic_payload,expected_revisions_json,admission_state,created_at) VALUES(?,?,?,'beta','alpha','backend-history-binding',?,'backend-history-wxb','backend-history-session',?,'history','{}','{}','RESOLVED_TERMINAL',?)", (server, executor, op, workspace, action, old))
        c.execute("INSERT INTO execution_sessions(server_id,executor_id,session_id,binding_id,workspace_id,workspace_binding_id,open_operation_id,owner_generation,lifecycle_state,lease_state) VALUES(?,?,'backend-history-session','backend-history-binding',?,'backend-history-wxb','backend-history-open',1,'CLOSED','CLOSED')", (server, executor, workspace))
        c.execute("INSERT INTO messages(message_id,workspace_id,from_agent_id,body,created_at) VALUES('backend-history-message',?,'alpha','Historical metadata only',?)", (workspace, old))
        c.execute("INSERT INTO message_deliveries(delivery_id,message_id,recipient_agent_id,status,created_at) VALUES('backend-history-delivery','backend-history-message','beta','read',?)", (old,))
        c.execute("INSERT INTO delivery_outbox(operation_id,delivery_id,message_id,workspace_id,actor_agent_id,credential_binding,recipient_agent_id,endpoint_id,endpoint_revision,envelope,request_hash,authorization_revision,root_operation_id,status,created_at,updated_at) VALUES('backend-history-domain','backend-history-delivery','backend-history-message',?,'alpha','historical','beta','backend-history-endpoint',1,'{}','historical','historical','backend-history-domain','ACCEPTED',?,?)", (workspace, old, old))
        c.execute("INSERT INTO runtime_execution_grants(grant_id,issuer_agent_id,actor_agent_id,credential_binding,represented_agent_id,workspace_id,endpoint_id,actions,expires_at,max_executions,created_at) VALUES('backend-expired-history','alpha','alpha','historical','beta',?,'backend-history-endpoint','[]',?,1,?)", (workspace, old, old))
        c.execute("INSERT INTO runtime_handoff_bindings(handoff_id,claim_epoch,operation_id,grant_id,grant_revision,actor_agent_id,idempotency_key,request_hash,created_at) VALUES(?,?,'backend-history-domain','backend-expired-history',1,'alpha','backend-history-correlation','historical',?)", (handoff, epoch, old))
        for i in range(3):
            operation, artifact = f'backend-history-turn-{i}', f'backend-file-{i}'
            c.execute("INSERT INTO execution_receipts(server_id,executor_id,operation_id,receipt_revision,intent_hash,stage,possible_effect,retry_safe,received_at) VALUES(?,?,?,1,'history','SUCCEEDED',1,0,?)", (server, executor, operation, old))
            c.execute('INSERT INTO execution_domain_deliveries VALUES(?,?,?,?)', (server, executor, operation, 'backend-history-domain'))
            c.execute("INSERT INTO execution_event_ingress VALUES(?,?,'backend-history-session','history',?,?,'turn_state','{}',?)", (server, executor, i + 1, f'backend-history-event-{i}', old))
            c.execute("INSERT INTO execution_results(server_id,executor_id,operation_id,session_id,stream_epoch,terminal_sequence,output_text,output_truncated,output_event_count,delivery_outcome,captured_at) VALUES(?,?,?,'backend-history-session','history',?,'Historical three-file output',0,1,'success',?)", (server, executor, operation, i + 1, old))
            c.execute("INSERT INTO artifacts(artifact_id,workspace_id,artifact_type,name,path,created_at) VALUES(?,?,'file',?,'NEVER-PUBLIC-HISTORY-PATH',?)", (artifact, workspace, artifact + '.txt', old))
            c.execute("INSERT INTO runtime_results(result_id,payload,captured_at,operation_id,canonical_server_id,canonical_executor_id,canonical_operation_id,output_artifact_id) VALUES(?,'{}',?,'backend-history-domain',?,?,?,?)", (f'backend-history-result-{i}', old, server, executor, operation, artifact))
    for _ in range(3):
        _park(tools, project_root)  # Newer canonical deliveries put selected item off page1.
    app = build_app(deps)
    client = TestClient(app, client=('127.0.0.1', 50000), base_url='http://localhost')

    def get(path, **query):
        response = client.get('/api/v1/home/' + path, params={'workspace_id': workspace, 'presentation_version': 2, **query})
        assert response.status_code == 200, response.text
        return response.json()['data']

    def deliveries(**query):
        return get('harness-board/results', **query)

    def selected():
        return next(item for item in deliveries(limit=100)['items'] if item.get('result', {}).get('source_ref', {}).get('id') == handoff)

    def protected():
        with deps.connection_factory.unit_of_work(write=False) as uow:
            return {name: [tuple(row) for row in uow.connection.execute('SELECT * FROM ' + name + ' ORDER BY rowid')]
                for name in ('message_deliveries', 'runtime_execution_grants', 'execution_operations',
                    'execution_receipts', 'execution_results', 'execution_dispatch_outbox')}

    try:
        before = protected()
        first = deliveries(limit=1)
        initial = selected()
        result = initial['result']
        assert result['source_ref']['id'] == handoff and result['created_at'] == old
        assert result['view_state'] == 'unseen' and result['delivery_semantics']['verification'] == 'pending'
        assert result['id'] not in {item['result']['id'] for item in first['items']}
        assert [a['artifact_id'] for a in result['artifacts']] == [f'backend-file-{i}' for i in range(3)]
        assert 'NEVER-PUBLIC-HISTORY-PATH' not in json.dumps(initial)
        cursor, ids = first['next_cursor'], [item['id'] for item in first['items']]
        while cursor:
            more = deliveries(limit=1, cursor=cursor)
            ids.extend(item['id'] for item in more['items'])
            cursor = more['next_cursor']
            assert len(ids) <= 10, 'Finite fixture pagination'
        assert ids.count(initial['id']) == 1
        _ok(tools['handoff_verify'](project_root=project_root, handoff_id=handoff,
            agent_id='alpha', verdict='pass', claim_epoch=epoch))
        verified = selected()
        assert verified['id'] == initial['id'] and verified['result']['id'] == result['id']
        assert verified['result']['artifacts'] == result['artifacts']
        assert verified['result']['delivery_semantics']['verification'] == 'approved'
        assert verified['result']['delivery_semantics']['verification_evidence_ref']
        assert verified['result']['delivery_semantics']['semantic_revision'] != result['delivery_semantics']['semantic_revision']
        after_verification = protected()
        assert {name: rows for name, rows in after_verification.items() if name != 'message_deliveries'} == {
            name: rows for name, rows in before.items() if name != 'message_deliveries'}
        old_deliveries = {row[0]: row for row in before['message_deliveries']}
        current_deliveries = {row[0]: row for row in after_verification['message_deliveries']}
        assert all(current_deliveries[key] == value for key, value in old_deliveries.items())
        # A canonical verification may publish a new coordination notice. It
        # must not ACK existing inbox deliveries; later GET/seen changes none.
        contract = tmp_path / 'presentation-input.json'
        contract.write_text(json.dumps({'before': result, 'after': verified['result']}) + '\n', encoding='utf-8')
        # This presentation subprocess consumes THIS test's actual API data.
        # It imports only copied pinned TypeScript through the existing compiler.
        node = subprocess.run([os.environ['HST_BACKEND_NODE'], os.environ['HST_BACKEND_PRESENTATION'], str(contract)],
            stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding='utf-8', timeout=15, check=False)
        assert node.returncode == 0, node.stdout + node.stderr
        assert json.loads(node.stdout)['same_delivery_verified'] is True
        all_before = deliveries(limit=100)['items']
        other_states = {item['id']: item['result']['view_state'] for item in all_before if item['id'] != initial['id']}
        occurrence = verified['result']['attention']
        assert occurrence is not None
        seen = client.post('/api/v1/attention/' + occurrence['attention_id'] + '/seen', json={
            'source_revision': occurrence['source_revision'], 'preference_revision': occurrence['seen_state']['revision'], 'seen': True})
        assert seen.status_code == 200, seen.text
        after = deliveries(limit=100)['items']
        assert initial['id'] not in {item['id'] for item in after}  # old, selected and now seen
        assert {item['id']: item['result']['view_state'] for item in after} == other_states
        target = client.get('/api/v1/home/target', params={'workspace_id': workspace,
            'target': json.dumps(result['detail_target'])})
        assert target.status_code == 200 and target.json()['data']['available']
        assert protected() == after_verification
    finally:
        client.close()
        deps.connection_factory.close()

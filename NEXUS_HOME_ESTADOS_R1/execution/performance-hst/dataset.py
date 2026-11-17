"""Synthetic benchmark read facts. Never evidence of native execution/authority."""
import hashlib
import json


WORKSPACE = 'hst-perf'


def seed(scenario, connections, history_events):
    """Caller owns a newly created finite fixture and its DB transaction.

    The schema/foreign keys are retained; semantic hashes/receipts of these copied
    rows are explicitly synthetic and must never be submitted as native work.
    """
    copy = scenario.fixtures_copy
    with scenario.factory.unit_of_work() as uow:
        c, now = uow.connection, scenario.clock.now_iso()

        def first(table, where='', args=()):
            row = c.execute('SELECT * FROM ' + table + (' WHERE ' + where if where else '') + ' LIMIT 1', args).fetchone()
            if row is None:
                raise RuntimeError('Required synthetic benchmark template missing: ' + table)
            return row

        source_agent = first('agents', 'agent_id=?', ('subject',))
        source_endpoint = first('agent_endpoints', 'endpoint_id=?', ('ep',))
        source_binding = first('execution_bindings', 'binding_id=?', ('binding',))
        source_wxb = first('execution_workspace_bindings', 'workspace_binding_id=?', ('wxb',))
        source_realization = first('execution_realizations', 'realization_ref=?', (source_binding['realization_ref'],))
        source_session = first('execution_sessions', 'session_id=?', (scenario.sessions[0],))
        source_opening = first('execution_operations', 'operation_id=?', (source_session['open_operation_id'],))
        source_turn = first('execution_operations', "action='turn.submit'")
        source_lease = first('execution_leases', 'session_id=? AND status=?', (scenario.sessions[0], 'ACTIVE'))
        source_grant = first('runtime_execution_grants', 'grant_id=?', (source_lease['grant_id'],))
        source_revisions = first('execution_agent_revisions', 'agent_id=?', ('subject',))
        copy(c, 'workspaces', first('workspaces', 'workspace_id=?', ('ws',)),
             workspace_id=WORKSPACE, display_name='Synthetic performance project')
        shared = dict(server_id=source_binding['server_id'], executor_id=source_binding['executor_id'])
        ingress_specs = []
        for i in range(connections):
            agent, endpoint, binding, wxb, realization, session, grant = (
                f'hst-perf-{kind}-{i:03}' for kind in ('agent', 'endpoint', 'binding', 'wxb', 'realization', 'session', 'grant'))
            opening_id, epoch = session + '-open', session + '-epoch'
            credential = 'synthetic-benchmark-only-' + str(i)
            copy(c, 'agents', source_agent, agent_id=agent, api_key_hash=credential,
                 metadata=json.dumps({'display_name': 'Synthetic collaborator ' + str(i)}))
            copy(c, 'execution_agent_revisions', source_revisions, agent_id=agent)
            copy(c, 'agent_endpoints', source_endpoint, endpoint_id=endpoint, workspace_id=WORKSPACE, agent_id=agent)
            copy(c, 'execution_workspace_bindings', source_wxb, workspace_binding_id=wxb, workspace_id=WORKSPACE)
            copy(c, 'execution_realizations', source_realization, realization_ref=realization,
                 local_realization_ref=realization + '-local', subject_agent_id=agent, workspace_binding_id=wxb)
            copy(c, 'execution_bindings', source_binding, binding_id=binding, endpoint_id=endpoint,
                 workspace_binding_id=wxb, realization_ref=realization)
            copy(c, 'runtime_execution_grants', source_grant, grant_id=grant, actor_agent_id=agent,
                 represented_agent_id=agent, credential_binding=credential, workspace_id=WORKSPACE,
                 endpoint_id=endpoint, used_executions=0)
            scope = dict(json.loads(source_opening['expected_revisions_json']), binding_id=binding,
                agent_id=agent, workspace_id=WORKSPACE, workspace_binding_id=wxb, session_id=session)
            scope_text = json.dumps(scope, sort_keys=True, separators=(',', ':'))
            association = dict(binding_id=binding, workspace_binding_id=wxb, workspace_id=WORKSPACE,
                session_id=session, subject_agent_id=agent, expected_revisions_json=scope_text)
            copy(c, 'execution_operations', source_opening, operation_id=opening_id, **association)
            copy(c, 'execution_sessions', source_session, session_id=session, binding_id=binding,
                workspace_id=WORKSPACE, workspace_binding_id=wxb, open_operation_id=opening_id, stream_epoch=epoch)
            request = json.loads(source_lease['request_json'])
            request['scope'] = scope
            copy(c, 'execution_leases', source_lease, session_id=session, lease_id=session + '-lease',
                request_id=session + '-lease-request', grant_id=grant, scope_json=scope_text,
                request_json=json.dumps(request, sort_keys=True, separators=(',', ':')))
            # Metadata receipt facts only: this builder never invokes the native
            # receipt receiver or claims these copied semantics were executed.
            c.execute('INSERT INTO execution_receipts(server_id,executor_id,operation_id,receipt_revision,intent_hash,'
                'stage,possible_effect,retry_safe,native_id,received_at) VALUES(?,?,?,1,?,?,1,0,?,?)',
                (*shared.values(), opening_id, source_opening['intent_hash'], 'SUBMITTED', session + '-synthetic-native', now))
            for j in range(10):
                oid = f'hst-perf-turn-{i:03}-{j:02}'
                pattern = i % 4
                stage = 'SUCCEEDED' if pattern == 0 or j < 9 else 'RUNNING' if pattern == 1 else 'SUBMITTED' if pattern == 2 else 'OUTCOME_UNKNOWN'
                admission = 'RESOLVED_TERMINAL' if stage == 'SUCCEEDED' else 'ACCEPTED'
                copy(c, 'execution_operations', source_turn, operation_id=oid, admission_state=admission, **association)
                c.execute('INSERT INTO execution_receipts(server_id,executor_id,operation_id,receipt_revision,intent_hash,'
                    'stage,possible_effect,retry_safe,native_id,received_at) VALUES(?,?,?,1,?,?,1,0,?,?)',
                    (*shared.values(), oid, source_turn['intent_hash'], stage, session + '-synthetic-native', now))
            ingress_specs.append((session, epoch, f'hst-perf-turn-{i:03}-09'))
        # Native history is bounded metadata, not transcript output. A complete
        # synthetic watermark avoids reading the history to compute a badge.
        for index, (session, epoch, operation) in enumerate(ingress_specs):
            total = history_events // connections + int(index < history_events % connections)
            if not total:
                continue

            def events():
                for sequence in range(1, total + 1):
                    event = dict(**shared, session_id=session, stream_epoch=epoch, sequence=sequence,
                        operation_id=operation, category='turn_state', payload={'delivery_phase': 'progress', 'benchmark_synthetic': True})
                    raw = json.dumps(event, sort_keys=True, separators=(',', ':'))
                    yield (*shared.values(), session, epoch, sequence, 'sha256:' + hashlib.sha256(raw.encode()).hexdigest(),
                           'turn_state', raw, now)
            c.executemany('INSERT INTO execution_event_ingress(server_id,executor_id,session_id,stream_epoch,sequence,'
                'event_hash,event_type,payload_json,received_at) VALUES(?,?,?,?,?,?,?,?,?)', events())
            c.execute('INSERT INTO execution_event_watermarks(server_id,executor_id,session_id,stream_epoch,'
                'committed_contiguous,projected_through,gap_state) VALUES(?,?,?,?,?,?,?)',
                (*shared.values(), session, epoch, total, total, 'none'))
        violations = [tuple(row) for row in c.execute('PRAGMA foreign_key_check')]
        if violations:
            raise RuntimeError('Synthetic benchmark foreign-key validation failed.')
        return dict(connections=connections, activities=connections * 10, added_native_events=history_events,
            workspace_id=WORKSPACE, foreign_key_violations=0,
            provenance='SQL synthetic read facts; no native or admission/authority qualification')

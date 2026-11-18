"""PREPARED J01/J02: canonical inert requests/results; historical correlation."""
import hashlib
import json
import sqlite3
from urllib.parse import urlencode

from backend_batch_owner import canonical_case


def save(owner, name, value):
    path = owner.control / name
    assert not path.exists()
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def prepare(owner):
    """No lease/authority SQL: all five sessions/turns are real admissions."""
    from okto_nexus.domain.base import iso_plus

    first = owner.binding
    second = owner.second_binding()
    grant = owner.call('POST', '/api/v1/harness/grants', {
        'actor_agent_id': first['agent_id'], 'endpoint_id': first['endpoint_id'],
        'actions': ['execute_work'], 'max_executions': 1,
        'expires_at': iso_plus(owner.deps.clock.now_iso(), 600)})
    deliveries = []
    for binding in (first, second):
        session = owner.open(binding)
        turn = owner.turn(session, binding=binding)
        gate = next(gate for _, recorded, gate in owner.turns if recorded['operation_id'] == turn['operation_id'])
        (owner.control / gate).touch()
        owner.stage(turn, ('SUCCEEDED',))
        deliveries.append(turn)
    questions = []
    for binding in (first, first, second):
        session = owner.open(binding)
        turn = owner.turn(session, binding=binding, question=True)
        assert owner.receipt(turn)['executor_stage'] == 'SUBMITTED'
        questions.append(turn)
    # Historical correlation facts ONLY. Coordination create/claim has no
    # equivalent REST route. This is not a native handoff receipt-chain proof.
    workspace, agent, now = first['workspace_id'], first['agent_id'], owner.deps.clock.now_iso()
    with owner.deps.connection_factory.unit_of_work() as uow:
        c = uow.connection
        c.execute("INSERT INTO handoffs(handoff_id,workspace_id,from_agent_id,target,visibility,status,claimed_by,claim_epoch,created_at,updated_at) "
            "VALUES('counts-shared',?,'operator',?,'eligible','CLAIMED',?,1,?,?)",
            (workspace, json.dumps({'strategy': 'direct', 'agent_id': agent}), agent, now, now))
        c.execute("INSERT INTO messages(message_id,workspace_id,from_agent_id,body,created_at) VALUES('counts-message',?,'operator','Synthetic correlation metadata',?)", (workspace, now))
        c.execute("INSERT INTO message_deliveries(delivery_id,message_id,recipient_agent_id,status,created_at) VALUES('counts-delivery','counts-message',?,'read',?)", (agent, now))
        c.execute("INSERT INTO delivery_outbox(operation_id,delivery_id,message_id,workspace_id,actor_agent_id,credential_binding,recipient_agent_id,endpoint_id,endpoint_revision,envelope,request_hash,authorization_revision,root_operation_id,status,created_at,updated_at) "
            "VALUES('counts-domain','counts-delivery','counts-message',?,?,'synthetic-correlation',?,?,1,'{}','synthetic','synthetic','counts-domain','ACCEPTED',?,?)",
            (workspace, agent, agent, first['endpoint_id'], now, now))
        c.execute("INSERT INTO runtime_handoff_bindings(handoff_id,claim_epoch,operation_id,grant_id,grant_revision,actor_agent_id,idempotency_key,request_hash,created_at) "
            "VALUES('counts-shared',1,'counts-domain',?,1,?,'counts-historical','synthetic',?)", (grant['grant_id'], agent, now))
        for turn in (questions[0], questions[2]):
            c.execute('INSERT INTO execution_domain_deliveries(server_id,executor_id,operation_id,domain_operation_id) VALUES(?,?,?,?)',
                (turn['scope']['server_id'], turn['scope']['executor_id'], turn['operation_id'], 'counts-domain'))
        assert not list(c.execute('PRAGMA foreign_key_check'))
    return {'questions': questions, 'deliveries': deliveries, 'binding_ids': {first['binding_id'], second['binding_id']}}


def signals(board, kind):
    return [item for lane in board['columns'].values() for item in lane['items'] if item['kind'] == kind]


def assert_units(board):
    assert board['inventory']['registered_harnesses'] == {'value': 2, 'total_is_exact': True, 'unit': 'harnesses'}
    assert board['operational_summary']['pending_actions'] == {'value': 3, 'total_is_exact': True}
    assert board['summary']['results'] == {'value': 2, 'total_is_exact': True, 'unit': 'results'}
    assert board['summary']['occurrences'] == {'value': 3, 'total_is_exact': True, 'unit': 'occurrences'}
    assert board['delivery_counts'] == {'canonical': 2, 'reported': 0, 'total_is_exact': True}


def test_j01_exact_units_dedup_shared_work_and_page_independence(tmp_path, monkeypatch):
    with canonical_case(tmp_path, monkeypatch) as owner:
        preconditions = prepare(owner)
        before = digest(owner.snapshot())
        full = owner.board(limit=100, preview=100)
        assert_units(full)
        cards = owner.cards(full)
        assert set(cards) == preconditions['binding_ids'] and len(cards) == 2
        shared = [(card['id'], child) for _, card in cards.values() for child in card['children']
            if child['source_ref']['id'] == 'counts-shared']
        assert len(shared) == 2 and shared[0][0] != shared[1][0]
        assert shared[0][1]['id'] == shared[1][1]['id'] and all(child['shared_reference'] for _, child in shared)
        raw_work = [child['id'] for _, card in cards.values() for child in card['children'] if child['kind'] == 'work']
        unique_work = set(raw_work)
        unique_work.update(child['id'] for child in full['unlinked']['items'] if child['kind'] == 'work')
        assert len(raw_work) > len(set(raw_work))
        assert full['summary']['activities']['value'] == len(unique_work)
        assert full['summary']['activities']['unit'] == 'activities'
        assert full['summary']['activities']['value'] != 2 + 3 + 2
        root = owner.board(limit=1, preview=1)
        assert_units(root)
        walked = {}
        for column in ('needs_you', 'results'):
            section = root['columns'][column]
            assert section['total'] == 2 and section['has_more'] and section['next_cursor']
            assert len(section['items']) == 1
            ids = [section['items'][0]['id']]
            cursor = section['next_cursor']
            while cursor:
                page = owner.call('GET', '/api/v1/home/harness-board/' + column + '?' + urlencode({
                    'workspace_id': owner.binding['workspace_id'], 'presentation_version': 2, 'limit': 1, 'preview': 1, 'cursor': cursor}))
                assert_units(page)
                assert page['revision'] == root['revision'] and page['total'] == 2 and page['total_is_exact']
                ids.extend(item['id'] for item in page['items'])
                cursor = page['next_cursor']
            assert len(ids) == len(set(ids)) == 2
            walked[column] = ids
        actions = set()
        for _, card in cards.values():
            cursor = None
            while True:
                page = owner.call('GET', '/api/v1/home/harness-board/cards/' + card['id'] + '/requests?' + urlencode({
                    'workspace_id': owner.binding['workspace_id'], 'presentation_version': 2, 'limit': 1, **({'cursor': cursor} if cursor else {})}))
                assert_units(page)
                for notification in page['items']:
                    attention = notification['request']['attention_id']
                    assert attention not in actions
                    actions.add(attention)
                cursor = page['next_cursor']
                if cursor is None:
                    break
        assert len(actions) == 3
        assert digest(owner.snapshot()) == before
        save(owner, 'j01-counts.json', {'full': full, 'limited': root, 'walked': walked, 'action_ids': sorted(actions),
            'shared_entry_id': shared[0][1]['id'], 'unique_work_ids': sorted(unique_work), 'snapshot_sha256_before': before,
            'snapshot_sha256_after': digest(owner.snapshot()), 'limits': 'Canonical inert requests/terminal results; historical shared correlation only; no timing'})


def test_j02_actual_sqlite_operations_reader_failure_keeps_other_positives(tmp_path, monkeypatch):
    from okto_nexus.adapters.outbound.sqlite import home_entries

    with canonical_case(tmp_path, monkeypatch) as owner:
        prepare(owner)
        baseline = owner.board()
        assert_units(baseline)
        assert baseline['operational_summary']['connected'] == {'value': 2, 'total_is_exact': True}
        before = digest(owner.snapshot())
        queries = owner.app.state.home_entries.queries
        original = queries._rows
        fault = {'denials': 0, 'caught_sqlite_codes': []}

        def operation_reader(uow, sql, params, check_budget=None):
            if sql is not home_entries.HARNESS_BLOCKING_V2:
                return original(uow, sql, params, check_budget)

            def authorize(action, table, column, database, source):
                if action == sqlite3.SQLITE_READ and table == 'execution_operations':
                    fault['denials'] += 1
                    return sqlite3.SQLITE_DENY
                return sqlite3.SQLITE_OK

            uow.connection.set_authorizer(authorize)
            try:
                return original(uow, sql, params, check_budget)
            except sqlite3.DatabaseError as error:
                fault['caught_sqlite_codes'].append(error.sqlite_errorcode)
                raise
            finally:
                uow.connection.set_authorizer(None)

        with monkeypatch.context() as patch:
            patch.setattr(queries, '_rows', operation_reader)
            partial = owner.board()
        assert fault['denials'] > 0 and fault['caught_sqlite_codes'] == [sqlite3.SQLITE_AUTH]
        assert partial['status'] == 'partial' and partial['coverage']['blocking'] == 'unknown'
        assert partial['source_status']['work'] == partial['source_status']['results'] == partial['source_status']['attention'] == 'ready'
        for key in ('idle', 'working', 'connected', 'blocked_harnesses'):
            assert partial['operational_summary'][key] == {'value': None, 'total_is_exact': False}
        assert partial['operational_summary']['pending_actions'] == {'value': 3, 'total_is_exact': True}
        assert partial['summary']['results'] == {'value': 2, 'total_is_exact': True, 'unit': 'results'}
        assert len(signals(partial, 'delivery')) == 2
        assert {item['request']['attention_id'] for item in signals(partial, 'request')} == {
            item['request']['attention_id'] for item in owner.requests(baseline)}
        assert all(card['operational_status']['connection'] == 'connected' for _, card in owner.cards(partial).values())
        assert not any(card['operational_status']['activity'] in ('idle', 'working') for _, card in owner.cards(partial).values())
        recovered = owner.board()
        assert_units(recovered)
        assert recovered['operational_summary']['connected'] == baseline['operational_summary']['connected']
        assert digest(owner.snapshot()) == before
        save(owner, 'j02-partial-coverage.json', {'baseline': baseline, 'partial': partial, 'recovered': recovered,
            'actual_sqlite_fault': fault, 'snapshot_sha256_before': before, 'snapshot_sha256_after': digest(owner.snapshot()),
            'limits': 'Read-only authorizer denial on operations dependency query, not a rewritten DTO or source producer failure; no timing'})

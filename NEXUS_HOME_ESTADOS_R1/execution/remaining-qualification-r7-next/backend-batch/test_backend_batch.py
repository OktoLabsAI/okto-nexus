"""PREPARED ONLY: seven functional cases, no latency/provider qualification.

Live state cases use real Core and canonical operator admissions to an inert
protocol peer. Correlation/artifact history fixtures are labelled separately;
they never write live authority, leases, RUNNING receipts or watermarks.
"""
import json
import sqlite3

from backend_batch_owner import canonical_case


def binding_key(card):
    return tuple(card['connection'][key] for key in ('server_id', 'executor_id', 'binding_id',
        'workspace_id', 'workspace_binding_id', 'agent_id'))


def own_requests(owner, board, turn):
    return [item for item in owner.requests(board) if item['request'].get('operation_id') == turn['operation_id']]


def assert_current(owner, card, session):
    status = card['operational_status']
    assert status['freshness'] == 'current' and status['connection'] == 'connected'
    response = owner.call('GET', '/api/v1/runtime-management/runtime/sessions/' + session
        + '?executor_id=' + card['connection']['executor_id'])
    assert response['lifecycle_state'] == 'READY'
    # Do not turn Core process_state UNKNOWN into a fabricated ALIVE claim.


def history_shared_work(owner):
    """Correlation read-facts only; all live authority/progress stays canonical."""
    from okto_nexus.domain.base import iso_plus
    binding = owner.binding
    grant = owner.call('POST', '/api/v1/harness/grants', {'actor_agent_id': binding['agent_id'],
        'endpoint_id': binding['endpoint_id'], 'actions': ['execute_work'], 'max_executions': 1,
        'expires_at': iso_plus(owner.deps.clock.now_iso(), 600)})
    # This helper must be called before any session admission. A grant is
    # canonical, not a synthetic revision/authority mutation.
    return grant


def attach_history_shared_work(owner, turns, grant):
    binding = owner.binding
    workspace, agent, now = binding['workspace_id'], binding['agent_id'], owner.deps.clock.now_iso()
    with owner.deps.connection_factory.unit_of_work() as uow:
        c = uow.connection
        c.execute("INSERT INTO handoffs(handoff_id,workspace_id,from_agent_id,target,visibility,status,claimed_by,claim_epoch,created_at,updated_at) "
            "VALUES('backend-shared',?,'operator',?,'eligible','CLAIMED',?,1,?,?)",
            (workspace, json.dumps({'strategy': 'direct', 'agent_id': agent}), agent, now, now))
        c.execute("INSERT INTO messages(message_id,workspace_id,from_agent_id,body,created_at) VALUES('backend-history-message',?,'operator','Historical correlation metadata',?)", (workspace, now))
        c.execute("INSERT INTO message_deliveries(delivery_id,message_id,recipient_agent_id,status,created_at) VALUES('backend-history-delivery','backend-history-message',?,'read',?)", (agent, now))
        c.execute("INSERT INTO delivery_outbox(operation_id,delivery_id,message_id,workspace_id,actor_agent_id,credential_binding,recipient_agent_id,endpoint_id,endpoint_revision,envelope,request_hash,authorization_revision,root_operation_id,status,created_at,updated_at) "
            "VALUES('backend-history-domain','backend-history-delivery','backend-history-message',?,?,'historical-read-fact',?,?,1,'{}','historical','historical','backend-history-domain','ACCEPTED',?,?)",
            (workspace, agent, agent, binding['endpoint_id'], now, now))
        c.execute("INSERT INTO runtime_handoff_bindings(handoff_id,claim_epoch,operation_id,grant_id,grant_revision,actor_agent_id,idempotency_key,request_hash,created_at) "
            "VALUES('backend-shared',1,'backend-history-domain',?,1,?,'backend-history-only','historical',?)", (grant['grant_id'], agent, now))
        for turn in turns:
            c.execute('INSERT INTO execution_domain_deliveries(server_id,executor_id,operation_id,domain_operation_id) VALUES(?,?,?,?)',
                (turn['scope']['server_id'], turn['scope']['executor_id'], turn['operation_id'], 'backend-history-domain'))


def test_shared_owner_bindings_keep_distinct_current_state(tmp_path, monkeypatch):
    """A04/B12 only: historical correlation; canonical A block/B progress."""
    with canonical_case(tmp_path, monkeypatch) as owner:
        other = owner.second_binding()
        grant = history_shared_work(owner)
        a, b = owner.open(), owner.open(other)
        blocked = owner.turn(a, question=True)
        working = owner.turn(b, binding=other, actor='subject')
        assert owner.receipt(working)['executor_stage'] == 'SUBMITTED'
        attach_history_shared_work(owner, (blocked, working), grant)
        before = owner.snapshot()
        for filters in ({}, {'agent_id': 'subject'}):
            board = owner.board(**filters)
            cards = owner.cards(board)
            assert owner.binding['binding_id'] in cards and other['binding_id'] in cards, filters
            ac, bc = cards[owner.binding['binding_id']], cards[other['binding_id']]
            assert ac[0] == 'needs_you' and ac[1]['blocks_harness'] is True
            assert bc[0] == 'active' and bc[1]['blocks_harness'] is False
            assert bc[1]['operational_status']['activity'] == 'working'
            assert bc[1]['operational_status']['running_sessions']['value'] == 1
            assert ac[1]['connection']['agent_id'] == bc[1]['connection']['agent_id']
            assert binding_key(ac[1]) != binding_key(bc[1])
            assert_current(owner, ac[1], a)
            assert_current(owner, bc[1], b)
            assert len(own_requests(owner, board, blocked)) == 1
            assert not bc[1]['requests_preview']
            assert not [event for event in bc[1]['events_preview'] if event['kind'] == 'attention']
            shared = [(card['id'], entry) for _, card in cards.values() for entry in card['children']
                if entry['source_ref']['id'] == 'backend-shared']
            assert len(shared) == 2 and shared[0][1]['id'] == shared[1][1]['id']
        assert owner.snapshot() == before


def test_hidden_productive_sibling_same_binding_prevents_false_full_block(tmp_path, monkeypatch):
    """A06: prove a real public state filter hides B, not another binding."""
    from urllib.parse import urlencode
    with canonical_case(tmp_path, monkeypatch) as owner:
        a, b = owner.open(), owner.open()
        blocked = owner.turn(a, question=True)
        working = owner.turn(b, actor='subject')
        assert owner.receipt(working)['executor_stage'] == 'SUBMITTED'
        before = owner.snapshot()
        scope = {'workspace_id': owner.binding['workspace_id'], 'state': 'awaiting_operator', 'limit': 100}
        public = owner.call('GET', '/api/v1/home/work?' + urlencode(scope))
        visible_operations = {ref['operation_id'] for item in public['items'] for ref in item.get('runtime_refs', [])}
        assert blocked['operation_id'] in visible_operations
        assert working['operation_id'] not in visible_operations  # Required hidden-sibling Given.
        unfiltered = owner.cards(owner.board())[owner.binding['binding_id']][1]
        board = owner.board(state='awaiting_operator')
        column, card = owner.cards(board)[owner.binding['binding_id']]
        assert len(owner.cards(board)) == 1  # One connection, two exact sessions.
        assert column == 'active' and card['blocks_harness'] is False
        assert card['operational_status']['activity'] == 'working'
        assert card['operational_status']['running_sessions']['value'] == 1
        assert card['operational_status']['blocking'] == 'partial'
        assert card['operational_status'] == unfiltered['operational_status']
        assert_current(owner, card, b)
        child_operations = {(child.get('target') or {}).get('operation_id') for child in card['children']}
        assert blocked['operation_id'] in child_operations
        assert working['operation_id'] not in child_operations
        assert len(own_requests(owner, board, blocked)) == 1
        assert board['columns']['needs_you']['items'][0]['kind'] == 'request'
        assert owner.snapshot() == before


def test_current_core_work_survives_external_unavailable_only(tmp_path, monkeypatch):
    """B08: unavailable, not disabled; actual SUBMITTED + committed started."""
    with canonical_case(tmp_path, monkeypatch) as owner:
        session = owner.open()
        turn = owner.turn(session)
        assert owner.receipt(turn)['executor_stage'] == 'SUBMITTED'
        initial = owner.cards(owner.board())[owner.binding['binding_id']][1]
        assert initial['operational_status']['activity'] == 'working'
        before = owner.snapshot()
        def unavailable(*args, **kwargs):
            raise sqlite3.OperationalError('Own external source unavailable')
        monkeypatch.setattr(owner.app.state.home_entries.queries, 'external', unavailable)
        board = owner.board()
        card = owner.cards(board)[owner.binding['binding_id']][1]
        assert board['status'] == 'partial' and board['source_status']['external'] == 'unavailable'
        assert all(value == 'ready' for name, value in board['source_status'].items() if name != 'external')
        assert card['operational_status']['activity'] == 'working'
        assert_current(owner, card, session)
        target = next(event['target'] for event in card['events_preview'] if (event['entry'].get('target') or {}).get('operation_id') == turn['operation_id'])
        from urllib.parse import urlencode
        resolved = owner.call('GET', '/api/v1/home/target?' + urlencode({'target': json.dumps(target),
            'workspace_id': owner.binding['workspace_id']}))
        assert resolved['available'] and resolved['target'] == target
        assert owner.snapshot() == before


def test_explicit_nonblocking_input_keeps_working_and_one_independent_action(tmp_path, monkeypatch):
    """C01: real requestUserInput false; no assumption from a sibling question."""
    with canonical_case(tmp_path, monkeypatch) as owner:
        session = owner.open()
        turn = owner.turn(session, question=True, blocking=False)
        before = owner.snapshot()
        board = owner.board()
        column, card = owner.cards(board)[owner.binding['binding_id']]
        assert column == 'active' and card['blocks_harness'] is False
        assert card['operational_status']['activity'] == 'working'
        assert card['operational_status']['pending_actions']['value'] == 1
        requests = own_requests(owner, board, turn)
        assert len(requests) == 1 and requests[0]['kind'] == 'request'
        assert requests[0]['blocks_session'] is False and requests[0]['blocks_harness'] is False
        assert [ref['connection']['binding_id'] for ref in requests[0]['harness_refs']] == [owner.binding['binding_id']]
        assert board['columns']['needs_you']['items'] == requests
        assert owner.snapshot() == before


def test_idle_sibling_cannot_make_a_full_block_independent(tmp_path, monkeypatch):
    """C05: two real ready sessions, only one productive blocked turn."""
    with canonical_case(tmp_path, monkeypatch) as owner:
        a, idle = owner.open(), owner.open()
        turn = owner.turn(a, question=True)
        before = owner.snapshot()
        board = owner.board()
        column, card = owner.cards(board)[owner.binding['binding_id']]
        assert column == 'needs_you' and card['blocks_harness'] is True
        status = card['operational_status']
        assert status['activity'] == 'waiting_user' and status['blocking'] == 'full'
        assert status['running_sessions']['value'] == 0 and status['blocked_sessions']['value'] == 1
        assert_current(owner, card, idle)
        assert len(own_requests(owner, board, turn)) == 1
        assert owner.snapshot() == before


def test_admitted_queued_sibling_has_no_independence_proof(tmp_path, monkeypatch):
    """C06 negative only; no independent-admissibility producer is invented."""
    with canonical_case(tmp_path, monkeypatch) as owner:
        a, b = owner.open(), owner.open()
        blocked = owner.turn(a, question=True)
        with owner.hold_dispatch():
            queued = owner.turn(b, queued=True)
            before = owner.snapshot()
            with owner.deps.connection_factory.unit_of_work(write=False) as uow:
                receipt = uow.connection.execute('SELECT stage FROM execution_receipts WHERE operation_id=?',
                    (queued['operation_id'],)).fetchall()
                dispatch = uow.connection.execute('SELECT dispatch_state FROM execution_dispatch_outbox WHERE operation_id=?',
                    (queued['operation_id'],)).fetchone()[0]
                assert not receipt and dispatch in ('PENDING', 'RESERVED')
                assert not uow.connection.execute("SELECT 1 FROM execution_event_ingress WHERE json_extract(payload_json,'$.operation_id')=?",
                    (queued['operation_id'],)).fetchone()
            board = owner.board()
            card = owner.cards(board)[owner.binding['binding_id']][1]
            assert card['operational_status']['activity'] == 'unknown' and card['blocks_harness'] is None
            assert card['operational_status']['running_sessions']['value'] == 0
            assert len(own_requests(owner, board, blocked)) == 1
            assert owner.snapshot() == before
        owner.stage(queued, ('SUBMITTED',))
        owner.started(queued)  # Canonical release before cleanup; no stranded reservation.


def test_same_delivery_verification_three_files_seen_and_no_ack(tmp_path):
    """E16: one DB, actual complete/verify/seen, historical artifact read facts."""
    from backend_batch_results import composed_delivery_case
    composed_delivery_case(tmp_path)

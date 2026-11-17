"""Real canonical handoff transitions and migrated SQLite Home projection."""
import json

from test_verification import make_env, _ok, _park, _err

from okto_nexus.adapters.outbound.sqlite.home import SqliteHomeQueries
from okto_nexus.domain.home_delivery_semantics import delivery_reference


def row(deps, handoff_id):
    with deps.connection_factory.unit_of_work(write=False) as uow:
        return dict(uow.connection.execute('SELECT * FROM handoffs WHERE handoff_id=?', (handoff_id,)).fetchone())


def events(deps, handoff_id):
    with deps.connection_factory.unit_of_work(write=False) as uow:
        return [dict(value, payload=json.loads(value['payload'])) for value in uow.connection.execute(
            "SELECT * FROM events WHERE stream='handoff' AND json_extract(payload,'$.handoff_id')=? ORDER BY event_id", (handoff_id,))]


def page(deps, workspace, version=2):
    with deps.connection_factory.unit_of_work(write=False) as uow:
        writes = uow.connection.total_changes
        queries = []
        uow.connection.set_trace_callback(queries.append)
        try:
            value, _ = SqliteHomeQueries().page(uow, section='results', scope={'workspace_id': workspace},
                server_id='test-server', now=deps.clock.now_iso(), limit=50,
                presentation_version=version)
        finally:
            uow.connection.set_trace_callback(None)
        assert uow.connection.total_changes == writes
        assert len(queries) == 1
        assert len(queries) == 1
        return value


def verify(tools, root, handoff_id, verdict, epoch):
    return _ok(tools['handoff_verify'](project_root=root, handoff_id=handoff_id,
        agent_id='alpha', verdict=verdict, claim_epoch=epoch))


def test_pending_and_positive_proof_keep_one_result_id_and_legacy_membership(tmp_path):
    deps, tools, root = make_env(tmp_path)
    try:
        handoff_id = _park(tools, root, acceptance_criteria=['Delivery is useful'])
        stored = row(deps, handoff_id)
        workspace, epoch = stored['workspace_id'], stored['claim_epoch']
        requested = next(event for event in events(deps, handoff_id) if event['type'] == 'handoff.verification_requested')
        ref = requested['payload']['delivery_ref']
        assert requested['payload']['claim_epoch'] == epoch == ref['claim_epoch']
        assert 'result' not in requested['payload']
        assert page(deps, workspace, 1)['items'] == []
        pending = page(deps, workspace)['items']
        assert len(pending) == 1 and pending[0]['delivery_semantics']['verification'] == 'pending'
        verify(tools, root, handoff_id, 'pass', epoch)
        completed = page(deps, workspace)['items']
        assert len(completed) == 1 and completed[0]['id'] == pending[0]['id']
        semantics = completed[0]['delivery_semantics']
        assert semantics['verification'] == 'approved' and semantics['task_state'] == 'completed'
        assert semantics['execution_outcome'] == 'not_applicable' and semantics['scope'] == 'handoff'
        proof = next(event for event in events(deps, handoff_id) if event['type'] == 'handoff.completed')
        assert proof['payload']['delivery_ref'] == ref
        assert semantics['verification_evidence_ref'].startswith('handoff-verification:' + str(proof['event_id']) + ':')
        assert completed[0]['verification_state'] == 'COMPLETED'
        assert page(deps, workspace, 1)['items'][0]['id'] == completed[0]['id']
        assert semantics['semantic_revision'] != pending[0]['delivery_semantics']['semantic_revision']
    finally:
        deps.connection_factory.close()


def test_rejected_delivery_uses_old_epoch_and_never_verifies_next_delivery(tmp_path):
    deps, tools, root = make_env(tmp_path)
    try:
        handoff_id = _park(tools, root, acceptance_criteria=['Delivery is useful'])
        initial = row(deps, handoff_id)
        workspace, epoch = initial['workspace_id'], initial['claim_epoch']
        first = page(deps, workspace)['items'][0]
        failed = verify(tools, root, handoff_id, 'fail', epoch)
        assert failed['status'] == 'CLAIMED' and failed['claim_epoch'] == epoch + 1
        event = next(value for value in events(deps, handoff_id) if value['type'] == 'handoff.verification_failed')
        assert event['payload']['claim_epoch'] == event['payload']['delivery_ref']['claim_epoch'] == epoch
        assert event['payload']['current_claim_epoch'] == epoch + 1
        rejected = page(deps, workspace)['items'][0]
        assert rejected['id'] == first['id']
        assert rejected['delivery_semantics']['verification'] == 'rejected'
        assert rejected['delivery_semantics']['historical']
        assert rejected['delivery_semantics']['task_state'] == 'claimed'
        assert page(deps, workspace, 1)['items'] == []
        _ok(tools['handoff_complete'](project_root=root, handoff_id=handoff_id, agent_id='beta',
            result='Different second delivery', claim_epoch=epoch + 1))
        values = page(deps, workspace)['items']
        current = next(value for value in values if value['id'] != first['id'])
        old = next(value for value in values if value['id'] == first['id'])
        assert current['delivery_semantics']['verification'] == 'pending'
        assert old['delivery_semantics']['verification'] == 'rejected'
        assert old['preview'] is None and old['delivery_semantics']['content_state'] == 'unavailable'
        verify(tools, root, handoff_id, 'pass', epoch + 1)
        values = page(deps, workspace)['items']
        assert next(value for value in values if value['id'] == current['id'])['delivery_semantics']['verification'] == 'approved'
        assert next(value for value in values if value['id'] == first['id'])['delivery_semantics']['verification'] == 'rejected'
    finally:
        deps.connection_factory.close()


def test_completed_without_verification_contract_has_no_approved_badge(tmp_path):
    deps, tools, root = make_env(tmp_path)
    try:
        handoff_id = _park(tools, root)
        stored = row(deps, handoff_id)
        value = page(deps, stored['workspace_id'])['items'][0]
        assert value['outcome'] == value['verification_state'] == 'COMPLETED'
        assert value['delivery_semantics']['task_state'] == 'completed'
        assert value['delivery_semantics']['verification'] == 'not_applicable'
        assert value['delivery_semantics']['verification_evidence_ref'] is None
    finally:
        deps.connection_factory.close()


def test_verification_authority_and_old_claim_cannot_emit_a_delivery_proof(tmp_path):
    deps, tools, root = make_env(tmp_path)
    try:
        handoff_id = _park(tools, root, acceptance_criteria=['Delivery is useful'])
        initial = row(deps, handoff_id)
        before_events = events(deps, handoff_id)
        for actor in ('beta', 'gamma'):
            _err(tools['handoff_verify'](project_root=root, handoff_id=handoff_id,
                agent_id=actor, verdict='pass', claim_epoch=initial['claim_epoch']), 'PERMISSION_DENIED')
        _err(tools['handoff_verify'](project_root=root, handoff_id=handoff_id,
            agent_id='alpha', verdict='pass', claim_epoch=initial['claim_epoch'] + 1), 'INVALID_TRANSITION')
        assert row(deps, handoff_id) == initial
        assert events(deps, handoff_id) == before_events
        assert page(deps, initial['workspace_id'])['items'][0]['delivery_semantics']['verification'] == 'pending'
    finally:
        deps.connection_factory.close()


def test_same_claim_is_immutable_and_none_rework_references_the_persisted_delivery(tmp_path, monkeypatch):
    deps, tools, root = make_env(tmp_path)
    try:
        handoff_id = _park(tools, root, acceptance_criteria=['Delivery is useful'])
        initial = row(deps, handoff_id)
        _err(tools['handoff_complete'](project_root=root, handoff_id=handoff_id, agent_id='beta',
            result='A replacement in the same claim', claim_epoch=initial['claim_epoch']), 'INVALID_TRANSITION')
        assert row(deps, handoff_id) == initial
        failed = verify(tools, root, handoff_id, 'fail', initial['claim_epoch'])
        _ok(tools['handoff_complete'](project_root=root, handoff_id=handoff_id, agent_id='beta',
            result=None, claim_epoch=failed['claim_epoch']))
        current = row(deps, handoff_id)
        assert current['result'] == initial['result']
        submitted = [event for event in events(deps, handoff_id) if event['type'] == 'handoff.verification_requested'][-1]
        expected = delivery_reference(current['workspace_id'], handoff_id, current['claim_epoch'], current['result'])
        assert submitted['payload']['delivery_ref'] == expected
        assert expected != delivery_reference(current['workspace_id'], handoff_id, current['claim_epoch'], None)
        verify(tools, root, handoff_id, 'pass', current['claim_epoch'])
        from okto_nexus.domain import home_delivery_semantics
        def forbidden_hash(*args, **kwargs):
            raise AssertionError('A Home GET must not hash the persisted delivery content')
        monkeypatch.setattr(home_delivery_semantics, 'delivery_reference', forbidden_hash)
        values = page(deps, current['workspace_id'])['items']
        assert any(value['delivery_semantics']['verification'] == 'approved' for value in values)
    finally:
        deps.connection_factory.close()

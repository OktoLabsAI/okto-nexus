"""Real SQLite/Attention reads over synthetic canonical fixture facts."""
import importlib
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from okto_nexus.adapters.outbound.sqlite.home_entries import SqliteHomeEntryRelations
from okto_nexus.domain.attention import normalize_filters
from okto_nexus.domain.home import filters
from tests.ui_simplification.test_fixtures import fixtures
from tests.ui_simplification.test_passive_effects import TABLES


@contextmanager
def projected(s, version):
    service = s.app.state.home
    with s.factory.unit_of_work(write=False) as uow:
        server, now, config = service._basis(uow, s.operator, filters({}))
        with service.attention.queries._relation(uow, filters=normalize_filters({'state': 'all'}),
                now=now, config=config, access=service.access, context=s.operator,
                source_scope={'workspace_id': None}) as relation:
            yield SqliteHomeEntryRelations().read(uow, scope={}, server_id=server, now=now,
                attention_relation=relation, presentation_version=version), uow


def test_v2_batch_queries_read_real_schema_and_keep_private_coverage(tmp_path):
    with fixtures.scenario(tmp_path / 'operational') as s:
        with projected(s, 1) as (legacy, _):
            assert legacy.operational_sessions is None
        with projected(s, 2) as (current, uow):
            assert current.operational_source_status == dict.fromkeys(
                ('operational_sessions', 'operational_leases', 'operational_dependencies'), 'ready')
            assert current.operational_sessions is not None
            expected = uow.connection.execute('SELECT COUNT(*) FROM execution_sessions').fetchone()[0]
            assert len(current.operational_sessions) == expected
            assert set(current.source_status) == set(legacy.source_status)
            assert current.harness_blocking is not None
            assert all('owner_generation' in row for row in current.harness_blocking)
            assert current.connections == legacy.connections
            # This native-decision fixture explicitly seeds READY and applies
            # the lease, but never publishes an opening receipt.
            assert not any(f.runtime_ready for f in current.operational_sessions)
            # Current control is scoped metadata, not a real-process claim.
            for fact in current.operational_sessions:
                if fact.control_current:
                    assert fact.lifecycle_state == 'READY' and fact.valid_until is not None
                    assert fact.owner_generation > 0 and not fact.revoked


def test_applied_lease_and_ready_session_without_opening_receipt_is_not_runtime_proof(tmp_path):
    with fixtures.scenario(tmp_path / 'missing-opening') as s:
        with s.factory.unit_of_work() as uow:
            uow.connection.execute("DELETE FROM execution_receipts WHERE operation_id IN "
                "(SELECT operation_id FROM execution_operations WHERE action='runtime.open')")
        with projected(s, 2) as (current, _):
            assert any(f.control_current for f in current.operational_sessions)
            assert not any(f.runtime_ready for f in current.operational_sessions)


def test_http_negotiation_sessions_and_requests_are_canonical_read_only(tmp_path):
    with fixtures.scenario(tmp_path / 'operational-http') as s:
        def snapshot():
            with s.factory.unit_of_work(write=False) as uow:
                return {name: [tuple(row) for row in uow.connection.execute('SELECT * FROM ' + name + ' ORDER BY rowid')]
                        for name in TABLES}
        before = snapshot()
        client = TestClient(s.app, headers={'Authorization': 'Bearer ' + s.app.state.test_agent_keys['operator']})
        try:
            response = client.get('/api/v1/home/harness-board', params={'presentation_version': 2, 'preview': 1})
            assert response.status_code == 200, response.text
            value = response.json()['data']
            assert value['presentation_version'] == 2 and value['operational_summary']
            items = [item for lane in value['columns'].values() for item in lane['items'] if item['kind'] == 'harness']
            assert items
            for item in items:
                assert 'requests_preview' in item and 'sessions_total' in item
                for partition in ('sessions', 'requests'):
                    response = client.get('/api/v1/home/harness-board/cards/' + item['id'] + '/' + partition,
                                          params={'presentation_version': 2})
                    assert response.status_code == 200, response.text
                    page = response.json()['data']
                    assert page['partition'] == 'harness_' + partition and page['card_id'] == item['id']
                    assert page['revision'] == value['revision']
            old = client.get('/api/v1/home/harness-board').json()['data']
            assert 'operational_summary' not in old
            assert client.get('/api/v1/home/harness-board/cards/' + items[0]['id'] + '/requests').status_code == 422
        finally:
            client.close()
        assert snapshot() == before


def test_canonical_embedded_open_receipt_proves_ready_idle_without_claiming_process_alive(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / 'execution_r4'))
    local = importlib.import_module('test_local_realization')
    dispatch = importlib.import_module('test_embedded_dispatch')
    generator = local.local_setup.__wrapped__(tmp_path, monkeypatch, SimpleNamespace(param='codex_app_server'))
    setup = next(generator)
    try:
        _, binding, native = dispatch.connect_local(setup)
        deps, _app, client, headers, *_ = setup
        deps.config.feature_attention = True
        opened = dispatch.admit(setup, binding, 'hst-ready-open', 'runtime.start', new_session=True)
        receipt = dispatch.wait_receipt(setup, opened)
        assert receipt['executor_stage'] in ('SUBMITTED', 'SUCCEEDED') and native.opens == 1
        response = client.get('/api/v1/home/harness-board', params={'presentation_version': 2}, headers=headers['operator'])
        assert response.status_code == 200, response.text
        value = response.json()['data']
        cards = [item for lane in value['columns'].values() for item in lane['items'] if item['kind'] == 'harness']
        item = next(card for card in cards if card['connection']['binding_id'] == binding['binding_id'])
        assert item['operational_status']['connection'] == 'connected'
        assert item['operational_status']['activity'] == 'idle'
        session = client.get('/v1/runtime/sessions/' + opened['scope']['session_id'], headers=headers['subject']).json()
        assert session['process_state'] == session['ownership'] == 'UNKNOWN'
        assert native.opens == 1  # Reading Home did not start/restart anything.
    finally:
        generator.close()


def test_canonical_decision_projects_exact_native_write_reference_without_application_claim(tmp_path):
    with fixtures.scenario(tmp_path / 'decision-ref') as s:
        client = TestClient(s.app, headers={'Authorization': 'Bearer ' + s.app.state.test_agent_keys['operator']})
        try:
            response = client.post('/v1/runtime/approval-decisions', json=s.decision_body)
            assert response.status_code == 202, response.text
            decision = response.json()
            with projected(s, 2) as (current, _):
                row = next(row for row in current.harness_blocking if row['family'] == 'request' and row['state'] == 'DECIDED')
                assert row['decision_scope_matches'] == 1
                assert row['decision_id'] == decision['decision_id']
                assert row['native_operation_id'] == decision['native_operation_id']
                assert row['native_write_stage'] is None  # Outbox registration is not native application.
        finally:
            client.close()


def test_session_selector_labels_share_connection_redaction_and_bounds(tmp_path):
    with fixtures.scenario(tmp_path / 'selector-label') as s:
        with s.factory.unit_of_work() as uow:
            uow.connection.execute('UPDATE workspaces SET display_name=?', ('Bearer hst-private-label\n  ' + 'x' * 250,))
        with projected(s, 2) as (current, _):
            labels = {f.workspace_label for f in current.operational_sessions}
            assert labels and all(label is not None and len(label) <= 160 for label in labels)
            assert all('hst-private-label' not in label and '\n' not in label for label in labels)
            assert labels == {c.workspace_label for c in current.connections}


@pytest.mark.parametrize('changed', ['authorization_revision', 'configuration_revision', 'credential_epoch', 'realization_workspace_binding_id'])
def test_current_agent_and_realization_fences_in_real_sqlite_projection(tmp_path, monkeypatch, changed):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / 'execution_r4'))
    local = importlib.import_module('test_local_realization')
    dispatch = importlib.import_module('test_embedded_dispatch')
    generator = local.local_setup.__wrapped__(tmp_path, monkeypatch, SimpleNamespace(param='codex_app_server'))
    setup = next(generator)
    try:
        _, binding, native = dispatch.connect_local(setup)
        deps, _, client, headers, *_ = setup
        deps.config.feature_attention = True
        opened = dispatch.admit(setup, binding, 'hst-revision-open', 'runtime.start', new_session=True)
        dispatch.wait_receipt(setup, opened)

        def current_card():
            response = client.get('/api/v1/home/harness-board', params={'presentation_version': 2}, headers=headers['operator'])
            assert response.status_code == 200, response.text
            return next(item for lane in response.json()['data']['columns'].values() for item in lane['items']
                        if item['kind'] == 'harness' and item['connection']['binding_id'] == binding['binding_id'])

        assert current_card()['operational_status']['activity'] == 'idle'
        with deps.connection_factory.unit_of_work() as uow:
            c = uow.connection
            if changed == 'realization_workspace_binding_id':
                wxb = c.execute('SELECT * FROM execution_workspace_bindings WHERE workspace_binding_id=?',
                                (binding['workspace_binding_id'],)).fetchone()
                fixtures._copy(c, 'execution_workspace_bindings', wxb, workspace_binding_id='hst-other-wxb')
                c.execute('UPDATE execution_realizations SET workspace_binding_id=? WHERE realization_ref=?',
                          ('hst-other-wxb', binding['realization_ref']))
            else:
                # Deliberately stale the admitted scope in this own negative
                # fixture. No permission/grant is fabricated or expanded.
                c.execute('UPDATE execution_agent_revisions SET ' + changed + '=' + changed + '+1 WHERE agent_id=?',
                          (opened['scope']['agent_id'],))
        after = current_card()
        assert after['operational_status']['activity'] == 'unknown'
        assert after['operational_status']['connection'] == 'unknown'
        assert after['blocks_harness'] is None and after['resume_confirmation_refs'] == []
        assert not after['operational_status']['awaiting_native_confirmation']
        assert native.opens == 1
    finally:
        generator.close()

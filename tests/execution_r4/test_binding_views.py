"""Canonical binding reads survive disconnection and enforce current scope."""

from dataclasses import replace
import json
from pathlib import Path

from jsonschema import Draft202012Validator
import pytest

from test_binding_operator import onboarding, prepare_operator
from test_binding_replacement import prepared_pair


@pytest.fixture
def bound(onboarding):
    deps, client, headers, request = onboarding
    _, body = prepare_operator(client, headers, request)
    response = client.post('/v1/connections/bindings:apply', json=body, headers=headers['operator'])
    assert response.status_code == 200, response.text
    return deps, client, headers, response.json()


def read(client, headers, binding, actor='subject'):
    return client.get('/v1/connections/bindings/' + binding['binding_id'], headers=headers[actor])


def test_binding_read_is_scoped_current_and_has_no_execution_effect(bound, tmp_path):
    deps, client, headers, binding = bound
    schema = json.loads((Path(__file__).parents[2] / 'plans/contratos/http-target.schema.json').read_text(encoding='utf-8'))
    for actor in ('subject', 'operator'):
        response = read(client, headers, binding, actor)
        assert response.status_code == 200, response.text
        assert response.headers['Cache-Control'] == 'no-store'
        assert response.json() == binding
        Draft202012Validator({'$defs': schema['$defs'], '$ref': '#/$defs/BindingView'}).validate(response.json())
        assert str(tmp_path) not in response.text
        assert 'nxt4_' not in response.text and 'secret' not in response.text
    denied = read(client, headers, binding, 'other')
    missing = client.get('/v1/connections/bindings/missing', headers=headers['other'])
    assert denied.status_code == missing.status_code == 404
    assert denied.json() == missing.json()
    path = '/v1/connections/bindings/' + binding['binding_id']
    assert client.get(path).status_code == 401
    assert client.get(path + '?agent_id=subject', headers=headers['other']).status_code == 422
    with deps.connection_factory.unit_of_work(write=False) as uow:
        for table in ('execution_operations', 'execution_dispatch_outbox', 'execution_sessions', 'runtime_execution_grants'):
            assert uow.connection.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0] == 0


@pytest.mark.parametrize(('change', 'expected'), [
    ('offline', 'APPROVED'), ('endpoint', 'DISABLED'), ('agent', 'DISABLED'),
    ('method', 'DISABLED'), ('profile', 'DISABLED'), ('pending', 'PENDING_REVIEW'),
    ('inventory', 'STALE'), ('realization', 'STALE'), ('workspace', 'STALE'),
    ('revoked', 'REVOKED'),
])
def test_binding_read_reports_current_canonical_state(bound, change, expected):
    deps, client, headers, binding = bound
    with deps.connection_factory.unit_of_work() as uow:
        conn = uow.connection
        if change == 'offline':
            conn.execute("UPDATE execution_executors SET control_state='DISCONNECTED' WHERE executor_id=?", (binding['executor_id'],))
        elif change == 'endpoint':
            conn.execute('UPDATE agent_endpoints SET enabled=0 WHERE endpoint_id=?', (binding['endpoint_id'],))
        elif change == 'agent':
            conn.execute("UPDATE agents SET is_active=0 WHERE agent_id='subject'")
        elif change == 'method':
            conn.execute("INSERT INTO agent_connection_methods(agent_id,method,enabled) VALUES ('subject',?,0) "
                         "ON CONFLICT(agent_id,method) DO UPDATE SET enabled=0", (binding['adapter_id'],))
        elif change == 'profile':
            conn.execute('UPDATE runtime_profiles SET enabled=0 WHERE profile_id=(SELECT profile_id FROM agent_endpoints WHERE endpoint_id=?)', (binding['endpoint_id'],))
        elif change == 'pending':
            conn.execute("UPDATE agent_endpoints SET activation_state='pending_review' WHERE endpoint_id=?", (binding['endpoint_id'],))
        elif change == 'inventory':
            conn.execute('UPDATE execution_inventory_current SET inventory_revision=? WHERE executor_id=?', ('sha256:' + 'f' * 64, binding['executor_id']))
        elif change == 'realization':
            conn.execute('UPDATE execution_realizations SET revision=revision+1 WHERE realization_ref=?', (binding['realization_ref'],))
        elif change == 'workspace':
            conn.execute("UPDATE execution_workspace_bindings SET status='STALE' WHERE workspace_binding_id=?", (binding['workspace_binding_id'],))
        else:
            conn.execute("UPDATE execution_executors SET revoked_at='2026-10-01T00:00:00Z' WHERE executor_id=?", (binding['executor_id'],))
    response = read(client, headers, binding, 'operator')
    assert response.status_code == 200, response.text
    assert response.json()['state'] == expected
    if change in ('endpoint', 'method', 'pending', 'agent'):
        assert response.json()['authorization_revision'] > binding['authorization_revision']
    if change == 'profile':
        assert response.json()['configuration_revision'] > binding['configuration_revision']


def test_binding_read_survives_disabled_feature_and_removed_provider(bound, tmp_path):
    deps, client, headers, binding = bound
    (tmp_path / 'remote-only' / 'codex.exe').unlink()
    deps.config = replace(deps.config, feature_harness_integrations=False)
    response = read(client, headers, binding, 'operator')
    assert response.status_code == 200, response.text
    assert response.json() == binding


def test_binding_read_returns_replacement_not_original_apply_reply(onboarding, tmp_path):
    deps, client, headers, old, independent, request = prepared_pair(onboarding, tmp_path)
    _, body = prepare_operator(client, headers, request)
    changed = client.post('/v1/connections/bindings:apply', headers=headers['operator'], json=body)
    assert changed.status_code == 200, changed.text
    current = read(client, headers, old)
    assert current.status_code == 200, current.text
    assert current.json() == changed.json()
    assert current.json()['binding_revision'] == old['binding_revision'] + 1
    assert current.json()['realization_ref'] != old['realization_ref']
    assert read(client, headers, independent).json()['binding_revision'] == independent['binding_revision']

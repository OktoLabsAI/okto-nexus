"""Public session history stays scoped and never infers process exit."""
import json
from pathlib import Path

import jsonschema
import pytest

from test_embedded_dispatch import (
    qualified_contract, connected_local, admit, wait_receipt,
)
from test_local_realization import local_setup


def test_retire_canonical_endpoint_does_not_use_legacy_adapter(connected_local):
    setup, binding, native = connected_local
    deps, app, client, headers, *_ = setup
    with deps.connection_factory.unit_of_work(write=False) as uow:
        revision = uow.connection.execute('SELECT revision FROM agent_endpoints WHERE endpoint_id=?',
            (binding['endpoint_id'],)).fetchone()[0]
    response = client.patch('/api/v1/harness/endpoints/' + binding['endpoint_id'],
        headers={'x-api-key': headers['operator']['Authorization'].removeprefix('Bearer ')},
        json={'expected_revision': revision, 'enabled': False})
    assert response.status_code == 200, response.text
    assert response.json()['data']['enabled'] is False
    with deps.connection_factory.unit_of_work(write=False) as uow:
        row = uow.connection.execute('SELECT enabled,revision FROM agent_endpoints WHERE endpoint_id=?',
            (binding['endpoint_id'],)).fetchone()
        assert tuple(row) == (0, revision + 1)
    assert native.opens == 0


def test_agent_summary_includes_runtime_history_and_filters_workspace(connected_local):
    setup, binding, native = connected_local
    deps, app, client, headers, *_ = setup
    opened = admit(setup, binding, 'summary-open', 'runtime.start', new_session=True)
    wait_receipt(setup, opened)
    auth = {'x-api-key': headers['operator']['Authorization'].removeprefix('Bearer ')}
    path = '/api/v1/agents/subject/runtime-sessions'
    response = client.get(path, headers=auth)
    assert response.status_code == 200, response.text
    summary = response.json()['data']
    assert len(summary['items']) == 1 and not summary['has_more']
    row = summary['items'][0]
    assert row['scope']['session_id'] == opened['session_id']
    assert row['harness'] == binding['adapter_id'] and row['control_available']
    from okto_nexus.application.execution_session_views import agent_session_summary
    from okto_nexus.domain.runtime_context import RuntimeRequestContext
    loopback = RuntimeRequestContext(None, 'http_loopback', trusted_local_operator=True)
    assert agent_session_summary(deps, loopback, 'subject')['items'][0]['scope'] == row['scope']
    assert client.get(path, headers=auth, params={'workspace': 'other'}).json()['data']['items'] == []
    wait_receipt(setup, admit(setup, binding, 'summary-close', 'runtime.close', session_id=opened['session_id']), stages=('SUCCEEDED',))
    assert client.get(path, headers=auth).json()['data']['items'][0]['lifecycle_state'] == 'CLOSED'


def test_session_list_pages_closed_history_and_enforces_scope(connected_local):
    setup, binding, native = connected_local
    deps, app, client, headers, *_ = setup
    ids = []
    for index in range(3):
        opened = admit(setup, binding, f'list-open-{index}', 'runtime.start', new_session=True)
        wait_receipt(setup, opened)
        ids.append(opened['session_id'])
        wait_receipt(setup, admit(setup, binding, f'list-close-{index}', 'runtime.close',
                     session_id=opened['session_id']), stages=('SUCCEEDED',))
    path = '/v1/runtime/sessions'
    query = dict(executor_id=binding['executor_id'], binding_id=binding['binding_id'], agent_id='subject', limit=2)
    first = client.get(path, params=query, headers=headers['operator'])
    assert first.status_code == 200, first.text
    assert first.headers['cache-control'] == 'no-store'
    data = first.json()
    schema = json.loads((Path(__file__).resolve().parents[2] / 'plans/contratos/http-target.schema.json').read_text())
    jsonschema.Draft202012Validator({'$ref': '#/$defs/SessionListView', '$defs': schema['$defs']}).validate(data)
    assert [s['scope']['session_id'] for s in data['sessions']] == sorted(ids)[:2]
    assert data['has_more']
    assert all(s['lifecycle_state'] == 'CLOSED' and s['process_state'] == 'UNKNOWN' for s in data['sessions'])
    second = client.get(path, params={**query, 'after_session_id': data['next_after_session_id']}, headers=headers['subject']).json()
    assert [s['scope']['session_id'] for s in second['sessions']] == sorted(ids)[2:]
    assert not second['has_more']
    assert client.get(path, params=query).status_code == 401
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("INSERT INTO agents(agent_id,created_at) VALUES('foreign',?)", (deps.clock.now_iso(),))
        key = app.state.auth.issue_key(uow, agent_id='foreign')
    assert client.get(path, params=query, headers={'Authorization': 'Bearer ' + key}).json()['sessions'] == []
    for name in ('executor_id', 'binding_id', 'agent_id'):
        assert client.get(path, params={**query, name: 'foreign'}, headers=headers['operator']).json()['sessions'] == []
    for extra in ({'limit': 0}, {'limit': 101}, {'unknown': 'x'}, {'executor_id': ''}, {'after_session_id': 'x' * 161}):
        assert client.get(path, params={**query, **extra}, headers=headers['operator']).status_code == 422
    assert client.get(path, params=[*query.items(), ('limit', 1)], headers=headers['operator']).status_code == 422
    assert native.opens == 3
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM execution_operations').fetchone()[0] == 6


def test_public_session_view_survives_close_without_inventing_process_facts(connected_local):
    setup, binding, native = connected_local
    deps, app, client, headers, *_ = setup
    opened = admit(setup, binding, "view-open", "runtime.start", new_session=True)
    wait_receipt(setup, opened)
    session = opened["scope"]["session_id"]
    path = "/v1/runtime/sessions/" + session
    response = client.get(path, headers=headers["subject"])
    assert response.status_code == 200, response.text
    view = response.json()
    schema = json.loads((Path(__file__).resolve().parents[2] / "plans/contratos/http-target.schema.json").read_text())
    jsonschema.Draft202012Validator({"$ref": "#/$defs/SessionView", "$defs": schema["$defs"]}).validate(view)
    assert view["scope"] == opened["scope"]
    assert view["lifecycle_state"] == "READY"
    assert view["process_state"] == view["ownership"] == "UNKNOWN"
    assert response.headers["cache-control"] == "no-store"
    assert view["last_observed_at"] is not None
    assert view["control_available"]
    assert client.get(path).status_code == 401
    assert client.get(path, headers=headers["operator"]).json() == view
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("INSERT INTO agents(agent_id,created_at) VALUES ('foreign',?)", (deps.clock.now_iso(),))
        foreign_key = app.state.auth.issue_key(uow, agent_id="foreign")
    assert client.get(path, headers={"Authorization": "Bearer " + foreign_key}).status_code == 404
    assert client.get(path + "?executor_id=foreign", headers=headers["subject"]).status_code == 404
    assert client.get(path + "?executor_id=a&executor_id=b", headers=headers["subject"]).status_code == 422
    assert client.get(path + "?unknown=x", headers=headers["subject"]).status_code == 422
    assert client.get(path + "?executor_id=", headers=headers["subject"]).status_code == 422
    closed = admit(setup, binding, "view-close", "runtime.close", session_id=session)
    wait_receipt(setup, closed, stages=("SUCCEEDED",))
    view = client.get(path, headers=headers["subject"]).json()
    assert view["lifecycle_state"] == view["lease_state"] == "CLOSED"
    assert view["process_state"] == "UNKNOWN"
    assert not view["control_available"] and not view["durable_release_pending"]
    assert native.opens == 1
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_operations").fetchone()[0] == 2


@pytest.mark.parametrize("fault", ["offline", "expired", "generation"])
def test_disconnected_session_retains_lifecycle_without_claiming_control(connected_local, fault):
    setup, binding, native = connected_local
    deps, app, client, headers, *_ = setup
    opened = admit(setup, binding, "offline-view", "runtime.start", new_session=True)
    wait_receipt(setup, opened)
    with deps.connection_factory.unit_of_work() as uow:
        if fault == "offline":
            uow.connection.execute("UPDATE execution_executors SET control_state='OFFLINE'")
        elif fault == "expired":
            uow.connection.execute("UPDATE execution_leases SET valid_until_server='2000-01-01T00:00:00Z'")
        else:
            uow.connection.execute("UPDATE execution_leases SET connection_generation=connection_generation+1")
    response = client.get("/v1/runtime/sessions/" + opened["scope"]["session_id"], headers=headers["subject"])
    assert response.status_code == 200, response.text
    view = response.json()
    assert view["lifecycle_state"] == "READY"
    assert view["process_state"] == "UNKNOWN" and not view["control_available"]

    if fault == "expired":
        assert view["lease_state"] == "EXPIRED"


def test_session_id_collision_requires_executor_selection(connected_local):
    from okto_nexus.adapters.outbound.sqlite.execution_identity import register_remote_executor
    setup, binding, native = connected_local
    deps, app, client, headers, *_ = setup
    opened = admit(setup, binding, "collision-open", "runtime.start", new_session=True)
    wait_receipt(setup, opened)
    other = register_remote_executor(deps.connection_factory, actor_agent_id="subject",
        connector_id="another-connector", client_intent_id="another-registration").executor_id
    with deps.connection_factory.unit_of_work() as uow:
        conn = uow.connection
        def copy(table, where, params, **changes):
            row = dict(conn.execute("SELECT * FROM " + table + " WHERE " + where, params).fetchone())
            row.update(changes)
            conn.execute("INSERT INTO " + table + "(" + ",".join(row) + ") VALUES (" +
                ",".join("?" for _ in row) + ")", tuple(row.values()))
        copy("agent_endpoints", "endpoint_id=?", (binding["endpoint_id"],), endpoint_id="second-endpoint")
        copy("execution_workspace_bindings", "executor_id=?", (opened["scope"]["executor_id"],), executor_id=other, workspace_binding_id="second-workspace-binding")
        copy("execution_bindings", "binding_id=?", (binding["binding_id"],),
            executor_id=other, binding_id="second-binding", endpoint_id="second-endpoint", workspace_binding_id="second-workspace-binding")
        scope = {**opened["scope"], "executor_id": other, "binding_id": "second-binding", "workspace_binding_id": "second-workspace-binding"}
        copy("execution_operations", "operation_id=?", (opened["operation_id"],),
            executor_id=other, operation_id="second-open", binding_id="second-binding",
            expected_revisions_json=json.dumps(scope), workspace_binding_id="second-workspace-binding")
        copy("execution_sessions", "session_id=?", (opened["session_id"],),
            executor_id=other, binding_id="second-binding", open_operation_id="second-open", workspace_binding_id="second-workspace-binding")
    path = "/v1/runtime/sessions/" + opened["session_id"]
    for actor in ("subject", "operator"):
        assert client.get(path, headers=headers[actor]).status_code == 409
        selected = client.get(path, params={"executor_id": other}, headers=headers[actor])
        assert selected.status_code == 200, selected.text
        assert selected.json()["scope"]["executor_id"] == other
    assert native.opens == 1

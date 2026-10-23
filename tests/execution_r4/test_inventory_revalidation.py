"""Inventory refresh must not require repeating equivalent agent approvals."""
import copy
from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_local_realization import local_setup
from test_local_launch import admitted_local
from test_local_installation_check import checking  # noqa: F401
from okto_nexus.bootstrap import embedded_inventory
from okto_nexus.application.execution_local_launch import ApprovedLocalLaunch
from okto_nexus.application.execution_inventory_revalidation import selection, accepts_binding


@pytest.mark.parametrize('change', ['added_control', 'removed_control', 'changed_control', 'platform', 'fingerprint', 'source'])
def test_core_control_addition_revalidates_existing_installation(admitted_local, monkeypatch, change):
    import json
    setup, sent, _, _ = admitted_local
    deps, app, client, *_ = setup
    owner = app.state.embedded_inventory_owner
    client.portal.call(owner.refresh)
    with deps.connection_factory.unit_of_work() as uow:
        before = dict(uow.connection.execute('SELECT * FROM execution_bindings').fetchone())
        row = uow.connection.execute('SELECT * FROM execution_inventory_revalidation').fetchone()
        baseline = json.loads(row['baseline_json'])
        controls = baseline['runtime']['control_targeting']
        if change == 'added_control':
            # Retained consent from a Core release that did not implement steer.
            control = next(c for c in controls if c['action'] == 'turn.steer')
            control.update(supported=False, requires_active_run=False, steer_timing=None)
        elif change == 'removed_control':
            controls.append(dict(action='future.control', supported=True))
        elif change == 'changed_control':
            controls[0]['native_turn_id'] = 'changed'
        elif change == 'platform':
            baseline['runtime']['implementation_platforms'] = ['other']
        elif change == 'source':
            baseline['evidence']['source'] = 'trusted_root'
        else:
            baseline['evidence']['content_fingerprint'] = 'sha256:' + '0' * 64
        uow.connection.execute('UPDATE execution_inventory_revalidation SET baseline_json=?',
                               (json.dumps(baseline),))
    candidate = setup[5]
    other = replace(candidate, executable=candidate.executable + '.other', installation_ref=None)
    monkeypatch.setattr(embedded_inventory, 'discover_local_candidates',
        lambda **_: SimpleNamespace(candidates=tuple(c for c in (candidate, other) if not _.get('adapter_ids') or c.adapter_id in _['adapter_ids'])))
    client.portal.call(owner.refresh)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        after = dict(uow.connection.execute('SELECT * FROM execution_bindings').fetchone())
        assert after == before
        assert accepts_binding(uow.connection, after, owner.publication.inventory_revision,
                               owner.key.server_id, owner.key.executor_id) == (change in {'added_control', 'source'})
        assert bool(uow.connection.execute('SELECT compatible FROM execution_inventory_revalidation').fetchone()[0]) == (change in {'added_control', 'source'})
    if change in {'added_control', 'source'}:
        launch = ApprovedLocalLaunch(owner, sent.scope)
        launch.check()


@pytest.mark.parametrize('legacy', [False, True])
def test_equivalent_refresh_preserves_binding_and_running_launch(admitted_local, monkeypatch, legacy):
    setup, sent, _, _ = admitted_local
    deps, app, client, headers, body, candidate, root = setup
    owner = app.state.embedded_inventory_owner
    launch = ApprovedLocalLaunch(owner, sent.scope)
    with deps.connection_factory.unit_of_work() as uow:
        before = dict(uow.connection.execute('SELECT * FROM execution_bindings').fetchone())
        if legacy:
            uow.connection.execute('DELETE FROM execution_inventory_current')
            uow.connection.execute('DELETE FROM execution_inventory_snapshots')
    other = replace(candidate, executable=candidate.executable + '.other', installation_ref=None)
    monkeypatch.setattr(embedded_inventory, 'discover_local_candidates',
        lambda **_: SimpleNamespace(candidates=tuple(c for c in (candidate, other) if not _.get('adapter_ids') or c.adapter_id in _['adapter_ids'])))
    client.portal.call(owner.refresh)
    launch.check()
    with deps.connection_factory.unit_of_work() as uow:
        after = dict(uow.connection.execute('SELECT * FROM execution_bindings').fetchone())
        assert after == before
        assert accepts_binding(uow.connection, after, owner.publication.inventory_revision,
                               owner.key.server_id, owner.key.executor_id)
        validation = uow.connection.execute('SELECT * FROM execution_inventory_revalidation').fetchone()
        assert validation['reason'] == 'installation_unchanged'
    # Retained proof survives publication pruning and repeated refresh.
    client.portal.call(owner.refresh)
    client.portal.call(owner.refresh)
    launch.check()


@pytest.mark.parametrize('change', ['fingerprint', 'trust', 'missing'])
def test_changed_selected_installation_requires_review(admitted_local, monkeypatch, change):
    setup, sent, _, _ = admitted_local
    deps, app, client, headers, body, candidate, root = setup
    owner = app.state.embedded_inventory_owner
    client.portal.call(owner.refresh)  # capture the approved baseline
    changed = (() if change == 'missing' else
               (replace(candidate, **{change: 'untrusted' if change == 'trust' else 'sha256:' + '0'*64}),))
    monkeypatch.setattr(embedded_inventory, 'discover_local_candidates', lambda **_: SimpleNamespace(candidates=tuple(c for c in changed if not _.get('adapter_ids') or c.adapter_id in _['adapter_ids'])))
    client.portal.call(owner.refresh)
    with deps.connection_factory.unit_of_work() as uow:
        binding = uow.connection.execute('SELECT * FROM execution_bindings').fetchone()
        assert not accepts_binding(uow.connection, binding, owner.publication.inventory_revision,
                                   owner.key.server_id, owner.key.executor_id)


def test_core_version_and_unrelated_catalog_changes_are_not_selection_changes(admitted_local):
    setup, _, _, _ = admitted_local
    _, app, client, _, body, _, _ = setup
    owner = app.state.embedded_inventory_owner
    with owner.deps.connection_factory.unit_of_work() as uow:
        import json
        snapshot = json.loads(uow.connection.execute('SELECT canonical_projection FROM execution_inventory_snapshots '
            'ORDER BY publication_sequence DESC LIMIT 1').fetchone()[0])
    upgraded = copy.deepcopy(snapshot)
    upgraded['core_version'] = 'future-version'
    upgraded['catalog']['core_version'] = 'future-version'
    upgraded['availability']['core_version'] = 'future-version'
    upgraded['catalog']['runtimes'].append({'adapter_id': 'unrelated'})
    assert selection(snapshot, body['adapter_id'], body['candidate_ref']) == selection(upgraded, body['adapter_id'], body['candidate_ref'])


def test_harness_version_update_preserves_existing_binding_and_launch(admitted_local, monkeypatch):
    setup, sent, _, _ = admitted_local
    deps, app, client, _, _, candidate, _ = setup
    owner = app.state.embedded_inventory_owner
    client.portal.call(owner.refresh)
    changed = replace(candidate, version='0.999.0')
    monkeypatch.setattr(embedded_inventory, 'discover_local_candidates',
        lambda **_: SimpleNamespace(candidates=tuple(c for c in (changed,) if not _.get('adapter_ids') or c.adapter_id in _['adapter_ids'])))
    with deps.connection_factory.unit_of_work(write=False) as uow:
        before = dict(uow.connection.execute('SELECT * FROM execution_bindings').fetchone())
    client.portal.call(owner.refresh)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        after = dict(uow.connection.execute('SELECT * FROM execution_bindings').fetchone())
        assert before == after
        assert accepts_binding(uow.connection, after, owner.publication.inventory_revision,
            owner.key.server_id, owner.key.executor_id)
        assert uow.connection.execute('SELECT reason FROM execution_inventory_revalidation').fetchone()[0] == 'installation_updated'
    launch = ApprovedLocalLaunch(owner, sent.scope)
    assert launch.candidate.version == '0.999.0'
    launch.check()


def test_one_publication_revalidates_one_hundred_bindings(admitted_local, monkeypatch):
    setup, _, _, _ = admitted_local
    deps, app, client, _, _, candidate, _ = setup
    owner = app.state.embedded_inventory_owner
    with deps.connection_factory.unit_of_work() as uow:
        conn = uow.connection
        binding = dict(conn.execute('SELECT * FROM execution_bindings').fetchone())
        endpoint = dict(conn.execute('SELECT * FROM agent_endpoints WHERE endpoint_id=?', (binding['endpoint_id'],)).fetchone())
        for number in range(99):
            ep = dict(endpoint, endpoint_id=f'bulk_endpoint_{number}')
            b = dict(binding, endpoint_id=ep['endpoint_id'], binding_id=f'bulk_binding_{number}')
            for table, values in [('agent_endpoints', ep), ('execution_bindings', b)]:
                conn.execute(f'INSERT INTO {table} (' + ','.join(values) + ') VALUES (' + ','.join('?' for _ in values) + ')', tuple(values.values()))
    other = replace(candidate, executable=candidate.executable + '.other', installation_ref=None)
    monkeypatch.setattr(embedded_inventory, 'discover_local_candidates', lambda **_: SimpleNamespace(candidates=tuple(c for c in (candidate, other) if not _.get('adapter_ids') or c.adapter_id in _['adapter_ids'])))
    client.portal.call(owner.refresh)
    with deps.connection_factory.unit_of_work() as uow:
        bindings = uow.connection.execute('SELECT * FROM execution_bindings').fetchall()
        assert len(bindings) == 100
        assert all(accepts_binding(uow.connection, b, owner.publication.inventory_revision,
                   owner.key.server_id, owner.key.executor_id) for b in bindings)
    from okto_nexus.application.execution_log import read_execution_log
    logs = read_execution_log(deps.connection_factory, limit=200)
    assert sum(row['code'] == 'INVENTORY_REVALIDATED' for row in logs['items']) == 100


@pytest.mark.parametrize('scenario', ['updated', 'unchanged', 'failed', 'other_path', 'disabled', 'source_changed', 'source_and_version_changed'])
def test_updated_binary_is_observed_without_repeating_operator_setup(admitted_local, monkeypatch, scenario):
    from pathlib import Path
    from nexus_connector_core.discovery import fingerprint
    from okto_nexus.application import execution_local_observations as observations

    setup, sent, _, _ = admitted_local
    deps, app, client, _, _, candidate, _ = setup
    owner = app.state.embedded_inventory_owner
    client.portal.call(owner.refresh)
    binary = Path(candidate.executable)
    if scenario == 'other_path':
        binary = binary.with_name('other.exe')
    if scenario not in {'unchanged', 'source_changed'}:
        binary.write_bytes(b'Updated harness release')
    changed = replace(candidate, executable=str(binary), fingerprint=fingerprint(binary), trust='untrusted')
    if scenario.startswith('source_'):
        changed = replace(changed, source='trusted_root')
    accepted = scenario in {'updated', 'unchanged', 'source_changed', 'source_and_version_changed'}
    monkeypatch.setattr(embedded_inventory, 'discover_local_candidates',
        lambda **_: SimpleNamespace(candidates=tuple(c for c in (changed,) if not _.get('adapter_ids') or c.adapter_id in _['adapter_ids'])))
    calls = []
    async def probe(selected):
        calls.append(selected)
        if scenario == 'failed':
            raise OSError('Version process failed')
        return replace(selected, version='0.999.0')
    monkeypatch.setattr(observations, 'probe_version', probe)
    if scenario == 'disabled':
        with deps.connection_factory.unit_of_work() as uow:
            uow.connection.execute('UPDATE agent_endpoints SET enabled=0')
    client.portal.call(owner.refresh)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        rows = uow.connection.execute('SELECT * FROM execution_local_observations').fetchall()
        assert len(rows) == (1 if accepted else 0)
        binding = uow.connection.execute('SELECT * FROM execution_bindings').fetchone()
        assert accepts_binding(uow.connection, binding, owner.publication.inventory_revision,
            owner.key.server_id, owner.key.executor_id) == accepted
    assert len(calls) == (0 if scenario in {'other_path', 'disabled'} else 1)
    if accepted:
        launch = ApprovedLocalLaunch(owner, sent.scope)
        assert launch.candidate.version == '0.999.0'
        launch.check()
        client.portal.call(owner.refresh)
        assert len(calls) == 1
        if scenario == 'unchanged':
            revision = owner.publication.inventory_revision
            with deps.connection_factory.unit_of_work() as uow:
                uow.connection.execute('DELETE FROM execution_local_observations')
            client.portal.call(owner.refresh)
            assert len(calls) == 2
            assert owner.publication.inventory_revision == revision
            launch.check()
            client.portal.call(owner.refresh)
            assert len(calls) == 2
    elif scenario == 'failed':
        async def recovered(selected):
            return replace(selected, version='0.999.0')
        monkeypatch.setattr(observations, 'probe_version', recovered)
        client.portal.call(owner.refresh)
        with deps.connection_factory.unit_of_work(write=False) as uow:
            assert accepts_binding(uow.connection, binding, owner.publication.inventory_revision,
                owner.key.server_id, owner.key.executor_id)


@pytest.fixture
def stale_binding(checking, monkeypatch):
    """A binding made on an unchecked installation. A later version check makes it need review."""
    import nexus_connector_core.availability as availability
    monkeypatch.setattr(availability, 'qualified_build', lambda *a, **k: True)
    from test_connection_setup import request_for, finish
    from okto_nexus.application.execution_local_realizations import directory_identity
    from okto_nexus.domain.runtime_context import RuntimeRequestContext
    deps, app, client, headers, body, route, source, _ = checking
    # Qualify the build, so a checked installation is ready for runtime.
    source = replace(source, architecture='x86_64')
    monkeypatch.setattr(embedded_inventory, 'discover_local_candidates', lambda **_: SimpleNamespace(
        candidates=(source,) if not _.get('adapter_ids') or source.adapter_id in _['adapter_ids'] else ()))
    owner = app.state.embedded_inventory_owner
    client.portal.call(owner.refresh)
    snapshot = client.get(f'/v1/runtime/executors/{owner.key.executor_id}/inventory', headers=headers['operator']).json()['snapshot']
    body = dict(body, candidate_ref=snapshot['evidence'][0]['candidate_ref'], inventory_revision=snapshot['inventory_revision'])
    setup = (deps, app, client, headers, body, source, deps.config.home_dir.parent)
    context, request = request_for(setup)
    request['configuration']['workspace_root'] = str(setup[6])
    setup[6].mkdir(exist_ok=True)
    binding = finish(setup, context, request, verified={
        'root': directory_identity(request['configuration']['workspace_root']), 'home': None})['binding']
    assert client.post(route, json=body, headers=headers['operator']).status_code == 200
    state = lambda: client.get('/v1/connections/bindings/' + binding['binding_id'], headers=headers['operator']).json()['state']
    assert state() == 'STALE'
    return setup, binding, state


def test_operator_revalidates_all_stale_bindings_in_one_call(stale_binding, monkeypatch):
    setup, binding, state = stale_binding
    deps, app, client, headers, *_ = setup
    path = '/v1/connections/bindings:revalidate'
    assert client.post(path, headers=headers['subject']).status_code == 403
    assert client.post(path).status_code == 401
    assert state() == 'STALE'
    response = client.post(path, headers=headers['operator'])
    assert response.status_code == 200, response.text
    assert response.json()['revalidated'] == 1
    assert [(item['binding_id'], item['outcome']) for item in response.json()['bindings']] == [(binding['binding_id'], 'revalidated')]
    assert state() == 'APPROVED'
    owner = app.state.embedded_inventory_owner
    with deps.connection_factory.unit_of_work(write=False) as uow:
        row = dict(uow.connection.execute('SELECT * FROM execution_bindings').fetchone())
        assert accepts_binding(uow.connection, row, owner.publication.inventory_revision,
                               owner.key.server_id, owner.key.executor_id)
        assert uow.connection.execute('SELECT reason FROM execution_inventory_revalidation').fetchone()[0] == 'operator_revalidated'
    # A second call changes nothing, and a later equal publication keeps the acceptance.
    again = client.post(path, headers=headers['operator']).json()
    assert again['revalidated'] == 0 and again['already_current'] == 1
    client.portal.call(owner.refresh)
    assert state() == 'APPROVED'
    from okto_nexus.application.execution_log import read_execution_log
    logs = read_execution_log(deps.connection_factory, limit=200)
    assert any(item['code'] == 'INVENTORY_REVALIDATED' for item in logs['items'])


def test_revalidate_leaves_a_missing_installation_for_review(stale_binding, monkeypatch):
    setup, binding, state = stale_binding
    deps, app, client, headers, *_ = setup
    monkeypatch.setattr(embedded_inventory, 'discover_local_candidates', lambda **_: SimpleNamespace(candidates=()))
    client.portal.call(app.state.embedded_inventory_owner.refresh)
    response = client.post('/v1/connections/bindings:revalidate', headers=headers['operator'])
    assert response.status_code == 200, response.text
    assert response.json()['revalidated'] == 0 and response.json()['installation_missing'] == 1
    assert state() == 'STALE'


def test_revalidate_is_available_on_the_mcp_admin_path(stale_binding, monkeypatch):
    monkeypatch.syspath_prepend(str(__import__('pathlib').Path(__file__).parents[1]))
    from test_pr34_remediation import tool
    setup, binding, state = stale_binding
    _, _, client, headers, *_ = setup
    client.headers['host'] = '127.0.0.1:8000'
    arguments = dict(view='connections', maintenance=dict(action='revalidate_bindings'))
    denied = tool(client, headers['subject']['Authorization'].removeprefix('Bearer '), 'harness_list', arguments)
    assert not denied['ok'] and denied['error']['code'] == 'PERMISSION_DENIED', denied
    assert state() == 'STALE'
    result = tool(client, headers['operator']['Authorization'].removeprefix('Bearer '), 'harness_list', arguments)
    assert result['ok'] and result['data']['revalidated'] == 1, result
    assert state() == 'APPROVED'

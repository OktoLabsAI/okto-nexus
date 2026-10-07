"""Inventory refresh must not require repeating equivalent agent approvals."""
import copy
from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_local_realization import local_setup
from test_local_launch import admitted_local
from okto_nexus.bootstrap import embedded_inventory
from okto_nexus.application.execution_local_launch import ApprovedLocalLaunch
from okto_nexus.application.execution_inventory_revalidation import selection, accepts_binding


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
        lambda **_: SimpleNamespace(candidates=(candidate, other)))
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
    monkeypatch.setattr(embedded_inventory, 'discover_local_candidates', lambda **_: SimpleNamespace(candidates=changed))
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
        lambda **_: SimpleNamespace(candidates=(changed,)))
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
    monkeypatch.setattr(embedded_inventory, 'discover_local_candidates', lambda **_: SimpleNamespace(candidates=(candidate, other)))
    client.portal.call(owner.refresh)
    with deps.connection_factory.unit_of_work() as uow:
        bindings = uow.connection.execute('SELECT * FROM execution_bindings').fetchall()
        assert len(bindings) == 100
        assert all(accepts_binding(uow.connection, b, owner.publication.inventory_revision,
                   owner.key.server_id, owner.key.executor_id) for b in bindings)
    from okto_nexus.application.execution_log import read_execution_log
    logs = read_execution_log(deps.connection_factory, limit=200)
    assert sum(row['code'] == 'INVENTORY_REVALIDATED' for row in logs['items']) == 100


@pytest.mark.parametrize('scenario', ['updated', 'failed', 'other_path', 'disabled'])
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
    binary.write_bytes(b'Updated harness release')
    changed = replace(candidate, executable=str(binary), fingerprint=fingerprint(binary), trust='untrusted')
    monkeypatch.setattr(embedded_inventory, 'discover_local_candidates',
        lambda **_: SimpleNamespace(candidates=(changed,)))
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
        assert len(rows) == (1 if scenario == 'updated' else 0)
        binding = uow.connection.execute('SELECT * FROM execution_bindings').fetchone()
        assert accepts_binding(uow.connection, binding, owner.publication.inventory_revision,
            owner.key.server_id, owner.key.executor_id) == (scenario == 'updated')
    assert len(calls) == (0 if scenario in {'other_path', 'disabled'} else 1)
    if scenario == 'updated':
        launch = ApprovedLocalLaunch(owner, sent.scope)
        assert launch.candidate.version == '0.999.0'
        launch.check()
        client.portal.call(owner.refresh)
        assert len(calls) == 1

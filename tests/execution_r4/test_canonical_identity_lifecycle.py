"""Public runtime opens preserve registered agent identity across bindings."""
from dataclasses import asdict

import pytest

from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, connected_local, qualified_contract
from test_runtime_contract_migration import mcp


def registered_identities(setup):
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        return [{k: row[k] for k in row.keys() if k != 'last_seen_at'}
            for row in uow.connection.execute('SELECT * FROM agents ORDER BY agent_id')]


@pytest.mark.parametrize('surface', ['rest', 'mcp'])
def test_post_spawn_persistence_failure_reaps_native_without_changing_identity(connected_local, monkeypatch, surface):
    from nexus_connector_core.journal import SQLiteJournal
    from test_agent_recovery_isolation import eventually
    from test_canonical_native_protocol_regressions import install_native
    from test_harness_codex_connector import _FAKE_SERVER_SOURCE
    from test_embedded_dispatch import wait_receipt
    setup, binding, _ = connected_local
    deps, app, client, headers, *_, root = setup
    before = registered_identities(setup)
    peers, _ = install_native(connected_local, _FAKE_SERVER_SOURCE)
    original = SQLiteJournal.record_process_birth
    failed = []
    async def fail_once(journal, *args, **kwargs):
        if not failed:
            assert len(peers) == 1 and peers[0]._transport._proc.poll() is None
            failed.append(peers[0]._transport._proc)
            raise OSError('Cut durable birth persistence after a successful native handshake')
        return await original(journal, *args, **kwargs)
    monkeypatch.setattr(SQLiteJournal, 'record_process_birth', fail_once)
    body = dict(agent_id='subject', kind='codex', endpoint_id=binding['endpoint_id'],
        project_root=str(root), idempotency_key='post-spawn-persistence-failure')
    def invoke():
        if surface == 'rest':
            return client.post('/api/v1/harness/sessions', headers=headers['subject'], json=body).json()
        return mcp(setup, monkeypatch, headers['subject']['Authorization'].removeprefix('Bearer '), 'harness_open', body)
    admitted = invoke()
    assert admitted['ok'], admitted
    wait_receipt(setup, admitted['data'], stages=('OUTCOME_UNKNOWN',))
    eventually(lambda: bool(failed))
    assert failed[0].wait(timeout=15) is not None
    def recovered():
        with deps.connection_factory.unit_of_work(write=False) as uow:
            row = uow.connection.execute("SELECT state FROM execution_agent_recovery WHERE agent_id='subject'").fetchone()
            return row is not None and row[0] == 'READY'
    eventually(recovered, seconds=30)
    assert registered_identities(setup) == before
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert not uow.connection.execute("SELECT 1 FROM execution_sessions WHERE lifecycle_state='READY'").fetchone()
        assert not uow.connection.execute('PRAGMA foreign_key_check').fetchall()
    repeated = invoke()
    assert repeated['ok'] and repeated['data']['operation_id'] == admitted['data']['operation_id'], repeated
    assert len(peers) == len(failed) == 1
    assert app.state.embedded_dispatch_owner.failure is None


def second_binding(setup, monkeypatch, *, name='second', adapter_id='pi_rpc', workspace_root=None):
    from types import SimpleNamespace
    from nexus_connector_core import InstallationCandidate
    from nexus_connector_core.discovery import fingerprint
    from okto_nexus.bootstrap import embedded_inventory
    from test_binding_operator import prepare_operator
    from test_local_realization import publish
    from test_unbounded_local_grants import issue

    _, app, client, headers, original, candidate, root = setup
    binary = root.parent / (name + '-installation.exe')
    binary.write_bytes(b'Second approved native installation')
    other = InstallationCandidate(adapter_id, str(binary), fingerprint(binary), 'explicit', 'selected')
    existing = embedded_inventory.discover_local_candidates().candidates
    monkeypatch.setattr(embedded_inventory, 'discover_local_candidates',
        lambda **_: SimpleNamespace(candidates=(*existing, other)))
    owner = app.state.embedded_inventory_owner
    client.portal.call(owner.refresh)
    inventory = client.get(f'/v1/runtime/executors/{owner.key.executor_id}/inventory', headers=headers['operator']).json()['snapshot']
    selected = next(e for e in inventory['evidence'] if e['adapter_id'] == adapter_id
                    and e['candidate_ref'] != original['candidate_ref'])
    body = {**original, 'client_intent_id': name + '-realization', 'adapter_id': adapter_id,
            'candidate_ref': selected['candidate_ref'], 'inventory_revision': inventory['inventory_revision']}
    if workspace_root is not None:
        from okto_nexus.domain.ids import resolve_workspace_id
        root = workspace_root
        body.update(workspace_root=str(root), workspace_id=resolve_workspace_id(str(root)),
                    workspace_label=name)
        with setup[0].connection_factory.unit_of_work() as uow:
            setup[0].repos.workspaces.upsert(uow, workspace_id=body['workspace_id'],
                root_realpath=str(root), last_seen_at=setup[0].clock.now_iso())
    prepared = publish((setup[0], app, client, headers, body, other, root), changes={'secret_bindings': {}})
    assert prepared.status_code == 201, prepared.text
    view = prepared.json()
    _, request = prepare_operator(client, headers, dict(client_intent_id=name + '-binding', agent_id_hint='subject',
        executor_id=view['executor_id'], adapter_id=adapter_id, candidate_ref=body['candidate_ref'],
        inventory_revision=body['inventory_revision'], realization_ref=view['realization_ref'],
        workspace_id=view['workspace_id'], alias=name + '-local'))
    request['client_intent_id'] = name + '-apply'
    applied = client.post('/v1/connections/bindings:apply', headers=headers['operator'], json=request)
    assert applied.status_code == 200, applied.text
    binding = applied.json()
    grant = issue(setup, binding)
    assert grant.status_code == 200, grant.text
    return binding


@pytest.mark.parametrize('surface', ['rest', 'mcp'])
def test_unknown_identity_cannot_register_or_open_a_native_peer(connected_local, monkeypatch, surface):
    setup, binding, native = connected_local
    deps, _, client, headers, *_, root = setup
    with deps.connection_factory.unit_of_work(write=False) as uow:
        before = asdict(deps.repos.agents.get(uow, 'subject'))
    body = dict(agent_id='missing-identity', kind='codex', project_root=str(root),
        endpoint_id=binding['endpoint_id'], idempotency_key='unknown-open')
    if surface == 'rest':
        result = client.post('/api/v1/harness/sessions', headers=headers['operator'], json=body).json()
    else:
        result = mcp(setup, monkeypatch, headers['operator']['Authorization'].removeprefix('Bearer '), 'harness_open', body)
    # Canonical opens bind the original agent credential before looking up a
    # payload identity; unknown identities are not an operator bootstrap route.
    assert not result['ok'] and result['error']['code'] == 'PERMISSION_DENIED', result
    assert native.opens == 0
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert deps.repos.agents.get(uow, 'missing-identity') is None
        assert asdict(deps.repos.agents.get(uow, 'subject')) == before
        assert uow.connection.execute('SELECT COUNT(*) FROM execution_operations').fetchone()[0] == 0
        assert uow.connection.execute('SELECT COUNT(*) FROM harness_sessions').fetchone()[0] == 0


@pytest.mark.parametrize('same_request', [False, True])
def test_concurrent_bindings_preserve_one_registered_agent(connected_local, monkeypatch, same_request):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from test_embedded_dispatch import wait_receipt, admit
    setup, first, native = connected_local
    second = first if same_request else second_binding(setup, monkeypatch)
    deps, _, client, headers, *_, root = setup
    with deps.connection_factory.unit_of_work(write=False) as uow:
        before = asdict(deps.repos.agents.get(uow, 'subject'))
    gate = Barrier(2)
    def open_one(index):
        binding = (first, second)[index]
        body = dict(agent_id='subject', kind='codex' if index == 0 or same_request else 'pi',
            project_root=str(root), endpoint_id=binding['endpoint_id'],
            idempotency_key='concurrent-identity-' + str(0 if same_request else index))
        gate.wait(10)
        return client.post('/api/v1/harness/sessions', headers=headers['subject'], json=body).json()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(open_one, [0, 1]))
    assert all(r['ok'] for r in results), results
    for result in results:
        wait_receipt(setup, result['data'])
        assert result['data']['scope']['agent_id'] == 'subject'
    expected = 1 if same_request else 2
    assert len({r['data']['operation_id'] for r in results}) == expected
    assert len({r['data']['scope']['session_id'] for r in results}) == expected
    assert native.opens == expected
    with deps.connection_factory.unit_of_work(write=False) as uow:
        after = asdict(deps.repos.agents.get(uow, 'subject'))
        before.pop('last_seen_at')
        after.pop('last_seen_at')
        assert after == before
        assert uow.connection.execute('SELECT COUNT(*) FROM execution_sessions').fetchone()[0] == expected
        assert uow.connection.execute('SELECT COUNT(*) FROM harness_sessions').fetchone()[0] == 0
    for index in range(expected):
        sid = results[index]['data']['scope']['session_id']
        wait_receipt(setup, admit(setup, (first, second)[index], f'identity-close-{index}', 'runtime.close', session_id=sid), stages=('SUCCEEDED',))


@pytest.mark.parametrize('surface', ['rest', 'mcp'])
def test_capability_catalogue_remains_authoritative_across_native_open(connected_local, monkeypatch, surface):
    from test_embedded_dispatch import admit, wait_receipt
    setup, binding, native = connected_local
    deps, _, client, headers, *_, root = setup
    key = headers['subject']['Authorization'].removeprefix('Bearer ')
    def identities():
        with deps.connection_factory.unit_of_work(write=False) as uow:
            return [tuple(r) for r in uow.connection.execute(
                'SELECT agent_id,role,capabilities,metadata,is_active,api_key_hash FROM agents ORDER BY agent_id')]
    created = client.post('/api/v1/capabilities', headers=headers['operator'], json=dict(name='catalogue-fixture'))
    assert created.status_code == 200, created.text
    before = identities()
    invalid = ['catalogue-fixture', 'not-registered']
    rejected = client.patch('/api/v1/agents/subject', headers=headers['operator'], json=dict(capabilities=invalid))
    denied = mcp(setup, monkeypatch, key, 'agent_register', dict(agent_id='subject', capabilities=invalid))
    assert rejected.status_code == 422 and not denied['ok']
    assert rejected.json()['error']['code'] == denied['error']['code'] == 'VALIDATION_ERROR'
    assert identities() == before and native.opens == 0
    assert client.patch('/api/v1/agents/subject', headers=headers['operator'],
        json=dict(capabilities=['catalogue-fixture'])).status_code == 200
    assert mcp(setup, monkeypatch, key, 'agent_register',
        dict(agent_id='subject', capabilities=['catalogue-fixture']))['ok']
    before = identities()
    with deps.connection_factory.unit_of_work(write=False) as uow:
        catalogue = [tuple(r) for r in uow.connection.execute('SELECT * FROM capability_names ORDER BY name')]
    body = dict(agent_id='subject', kind='codex', endpoint_id=binding['endpoint_id'],
        project_root=str(root), idempotency_key='catalogue-open')
    if surface == 'rest':
        response = client.post('/api/v1/harness/sessions', headers=headers['subject'], json=body)
        assert response.status_code == 200, response.text
        opened = response.json()
    else:
        opened = mcp(setup, monkeypatch, key, 'harness_open', body)
    assert opened['ok'], opened
    wait_receipt(setup, opened['data'])
    assert native.opens == 1 and identities() == before
    wait_receipt(setup, admit(setup, binding, 'catalogue-close', 'runtime.close',
        session_id=opened['data']['scope']['session_id']), stages=('SUCCEEDED',))
    assert identities() == before
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert [tuple(r) for r in uow.connection.execute('SELECT * FROM capability_names ORDER BY name')] == catalogue
        assert not uow.connection.execute("SELECT 1 FROM capability_names WHERE name='not-registered'").fetchone()

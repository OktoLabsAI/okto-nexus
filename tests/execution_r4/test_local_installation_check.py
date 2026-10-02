"""Operator checks persist byte-bound facts, never runtime grants."""
import asyncio
from dataclasses import asdict, replace
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from nexus_connector_core import CoreError
from nexus_connector_core.discovery import fingerprint
from okto_nexus.errors import OktoNexusError

from okto_nexus.application import execution_local_observations as observations
from okto_nexus.bootstrap import embedded_inventory
from okto_nexus.bootstrap.execution_authority import build_execution_access
from okto_nexus.domain.runtime_context import RuntimeRequestContext
from test_local_realization import local_setup


@pytest.fixture
def checking(local_setup, monkeypatch):
    deps, app, client, headers, preparation, candidate, _ = local_setup
    source = replace(candidate, trust='untrusted')
    def discover(**_):
        return SimpleNamespace(candidates=(replace(source, fingerprint=fingerprint(Path(source.executable))),))
    monkeypatch.setattr(embedded_inventory, 'discover_local_candidates', discover)
    owner = app.state.embedded_inventory_owner
    client.portal.call(owner.refresh)
    calls = []
    async def probe(selected):
        calls.append(selected)
        assert selected.trust == 'selected'
        return replace(selected, version='0.159.0')
    monkeypatch.setattr(observations, 'probe_version', probe)
    snapshot = client.get(f'/v1/runtime/executors/{owner.key.executor_id}/inventory', headers=headers['operator']).json()['snapshot']
    body = dict(agent_id='subject', adapter_id=source.adapter_id,
                candidate_ref=snapshot['evidence'][0]['candidate_ref'],
                inventory_revision=snapshot['inventory_revision'], approved=True)
    route = f'/v1/runtime/executors/{owner.key.executor_id}/installations:check'
    return deps, app, client, headers, body, route, source, calls


def rows(deps):
    with deps.connection_factory.unit_of_work(write=False) as uow:
        return [dict(row) for row in uow.connection.execute('SELECT * FROM execution_local_observations')]


def test_checked_bytes_survive_passive_refresh_without_another_probe(checking):
    deps, app, client, headers, body, route, source, calls = checking
    from jsonschema import Draft202012Validator
    schema = json.loads((Path(__file__).parents[2] / 'plans/contratos/http-target.schema.json').read_text(encoding='utf-8'))
    Draft202012Validator({'$defs': schema['$defs'], '$ref': '#/$defs/LocalInstallationCheckRequest'}).validate(body)
    response = client.post(route, json=body, headers=headers['operator'])
    assert response.status_code == 200, response.text
    Draft202012Validator({'$defs': schema['$defs'], '$ref': '#/$defs/LocalInstallationCheckView'}).validate(response.json())
    assert response.json()['runtime_authorized'] is False
    assert response.json()['version'] == '0.159.0'
    assert source.executable not in response.text
    saved = rows(deps)
    assert json.loads(saved[0]['source_json']) == asdict(source)
    owner = app.state.embedded_inventory_owner
    assert owner.candidates == (replace(source, trust='selected', version='0.159.0'),)
    owner.candidates = ()  # A new read must use durable observations, not this cache.
    client.portal.call(owner.refresh)
    assert owner.candidates[0].version == '0.159.0' and len(calls) == 1
    with deps.connection_factory.unit_of_work(write=False) as uow:
        for table in ('execution_sessions', 'execution_bindings', 'execution_realizations', 'execution_link_tickets'):
            assert uow.connection.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] == 0
    # The previous revision cannot silently authorize another effect.
    assert client.post(route, json=body, headers=headers['operator']).status_code == 409
    assert len(calls) == 1


def test_observation_is_reused_after_server_restart(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from nexus_connector_core import InstallationCandidate
    from test_embedded_inventory import app_for
    binary = tmp_path / 'codex'
    binary.write_bytes(b'persistent local check candidate')
    source = InstallationCandidate('codex_app_server', str(binary), fingerprint(binary), 'path', 'untrusted')
    monkeypatch.setattr(embedded_inventory, 'discover_local_candidates', lambda **_: SimpleNamespace(candidates=(source,)))
    calls = []
    async def probe(selected):
        calls.append(selected)
        return replace(selected, version='0.159.0')
    monkeypatch.setattr(observations, 'probe_version', probe)
    home = tmp_path / 'home'
    deps, app = app_for(home)
    with deps.connection_factory.unit_of_work() as uow:
        headers = {'Authorization': 'Bearer ' + app.state.auth.issue_key(uow, agent_id='operator')}
    with TestClient(app) as client:
        owner = app.state.embedded_inventory_owner
        route = f'/v1/runtime/executors/{owner.key.executor_id}'
        snapshot = client.get(route + '/inventory', headers=headers).json()['snapshot']
        body = dict(agent_id='operator', adapter_id=source.adapter_id, approved=True,
                    candidate_ref=snapshot['evidence'][0]['candidate_ref'], inventory_revision=snapshot['inventory_revision'])
        assert client.post(route + '/installations:check', json=body, headers=headers).status_code == 200
    _, app = app_for(home)
    with TestClient(app):
        assert app.state.embedded_inventory_owner.candidates == (replace(source, trust='selected', version='0.159.0'),)
        assert len(calls) == 1


@pytest.mark.parametrize('failure', ['subject', 'consent', 'stale', 'binary', 'remote'])
def test_refusals_precede_version_execution(checking, failure):
    deps, _, client, headers, body, route, source, calls = checking
    actor = 'subject' if failure == 'subject' else 'operator'
    if failure == 'consent': body = body | {'approved': False}
    if failure == 'stale': body = body | {'inventory_revision': 'sha256:' + '0' * 64}
    if failure == 'binary': Path(source.executable).write_bytes(b'changed before probe')
    if failure == 'remote': route = '/v1/runtime/executors/remote/installations:check'
    response = client.post(route, json=body, headers=headers[actor])
    assert response.status_code in (403, 409, 422), response.text
    assert not calls and not rows(deps)


@pytest.mark.parametrize('failure', ['binary', 'authority', 'owner', 'containment'])
def test_probe_result_cannot_outlive_its_authority_or_identity(checking, monkeypatch, failure):
    deps, app, client, headers, body, route, source, calls = checking
    async def probe(selected):
        if failure == 'containment':
            raise CoreError('PROCESS_CONTAINMENT_UNAVAILABLE', 'version_probe', message='/private/local/path')
        if failure == 'binary':
            Path(source.executable).write_bytes(b'changed during probe')
        else:
            with deps.connection_factory.unit_of_work() as uow:
                if failure == 'authority':
                    uow.connection.execute("UPDATE agents SET is_active=0 WHERE agent_id='operator'")
                else:
                    uow.connection.execute("UPDATE execution_executors SET generation=generation+1 WHERE kind='embedded'")
        return replace(selected, version='0.159.0')
    monkeypatch.setattr(observations, 'probe_version', probe)
    response = client.post(route, json=body, headers=headers['operator'])
    assert response.status_code in (403, 409), response.text
    assert '/private/local/path' not in response.text and not rows(deps)


@pytest.mark.parametrize('change', ['binary', 'core', 'platform'])
def test_observation_reuse_requires_same_bytes_core_and_platform(checking, change):
    deps, app, client, headers, body, route, source, _ = checking
    assert client.post(route, json=body, headers=headers['operator']).status_code == 200
    if change == 'binary': Path(source.executable).write_bytes(b'new provider bytes')
    else:
        column = 'core_version' if change == 'core' else 'platform'
        with deps.connection_factory.unit_of_work() as uow:
            uow.connection.execute(f"UPDATE execution_local_observations SET {column}='different'")
    client.portal.call(app.state.embedded_inventory_owner.refresh)
    current = app.state.embedded_inventory_owner.candidates[0]
    assert current.version is None and current.trust == 'untrusted'


@pytest.mark.parametrize('shutdown', [False, True])
def test_cancelled_http_observer_keeps_probe_owned_and_fences_concurrent_check(checking, monkeypatch, shutdown):
    deps, app, client, _, body, _, _, _ = checking
    owner = app.state.embedded_inventory_owner
    with deps.connection_factory.unit_of_work(write=False) as uow:
        credential = uow.connection.execute("SELECT api_key_hash FROM agents WHERE agent_id='operator'").fetchone()[0]
    context = RuntimeRequestContext('operator', 'agent_key', credential_binding=credential)
    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()
        async def held(selected):
            entered.set()
            await release.wait()
            return replace(selected, version='0.159.0')
        monkeypatch.setattr(observations, 'probe_version', held)
        args = dict(access=build_execution_access(deps), context=context, request=body)
        waiter = asyncio.create_task(owner.check_installation(**args))
        try:
            await asyncio.wait_for(entered.wait(), 3)
            waiter.cancel()
            with pytest.raises(asyncio.CancelledError): await waiter
            assert not owner._probe_task.done()
            with pytest.raises(OktoNexusError, match='active'):
                await owner.check_installation(**args)
            if shutdown:
                owner.begin_shutdown()
                closing = asyncio.create_task(owner.close())
                await asyncio.sleep(0)
                assert not closing.done()
        finally:
            release.set()
            if shutdown:
                with pytest.raises(OktoNexusError, match='shutting down'):
                    await asyncio.wait_for(owner._probe_task, 5)
                await asyncio.wait_for(closing, 5)
            else:
                await asyncio.wait_for(owner._probe_task, 5)
        assert len(rows(deps)) == (0 if shutdown else 1)
    client.portal.call(scenario)


def test_committed_observation_recovers_after_publication_failure(checking, monkeypatch):
    deps, app, client, headers, body, route, _, calls = checking
    owner = app.state.embedded_inventory_owner
    original = owner._publish
    def fail(*args): raise OSError('injected publication failure')
    monkeypatch.setattr(owner, '_publish', fail)
    assert client.post(route, json=body, headers=headers['operator']).status_code == 500
    assert len(rows(deps)) == len(calls) == 1
    monkeypatch.setattr(owner, '_publish', original)
    client.portal.call(owner.refresh)
    assert owner.candidates[0].version == '0.159.0' and len(calls) == 1


def test_core_probe_uses_private_cwd_and_no_provider_credentials(tmp_path, monkeypatch):
    from nexus_connector_core import InstallationCandidate
    from nexus_connector_core import discovery
    candidate = InstallationCandidate('codex_app_server', str(tmp_path / 'codex'), 'sha256:' + '1'*64, 'explicit', 'selected')
    monkeypatch.setenv('OPENAI_API_KEY', 'must-not-reach-version-process')
    monkeypatch.setenv('CLAUDE_CONFIG_DIR', 'must-not-reach-version-process')
    seen = []
    async def probe(selected, *, cwd, env):
        assert 'OPENAI_API_KEY' not in env and 'HOME' not in env and 'CLAUDE_CONFIG_DIR' not in env
        assert cwd.is_absolute() and cwd.is_dir() and cwd != Path.cwd()
        seen.append(cwd)
        return replace(selected, version='0.159.0')
    monkeypatch.setattr(discovery, 'probe_selected_codex', probe)
    assert asyncio.run(observations.probe_version(candidate)).version == '0.159.0'
    assert not seen[0].exists()

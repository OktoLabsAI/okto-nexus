"""Canonical SQLite bootstrap/recovery; synthetic identities, no provider process."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
import sqlite3
from types import SimpleNamespace

import pytest
from nexus_connector_core.connection_configuration import parse_portable_connection_configuration

from okto_nexus.adapters.outbound.sqlite.connection import ConnectionFactory
from okto_nexus.adapters.outbound.sqlite.execution_identity import ensure_execution_installation
from okto_nexus.adapters.outbound.sqlite.migrations import MigrationRunner
from okto_nexus.application.auth import AgentKeyAuthService
from okto_nexus.application.project_preset import configuration
from okto_nexus.application.remote_setup import RemoteSetupService
from okto_nexus.application.settings import SettingsService
from okto_nexus.bootstrap.dependencies import Deps, build_repos
from okto_nexus.bootstrap.execution_authority import build_execution_access
from okto_nexus.config import NexusConfig
from okto_nexus.domain.runtime_context import RuntimeRequestContext
from okto_nexus.errors import OktoNexusError


class Clock:
    def now_iso(self):
        return datetime.now(timezone.utc).isoformat()


def compose(home):
    config = NexusConfig(home_dir=home, embedding_mode='off', feature_harness_integrations=True)
    factory, clock = ConnectionFactory(config), Clock()
    repos, emitter = build_repos(clock, config)
    deps = Deps(config, factory, clock, repos, emitter)
    service = RemoteSetupService(deps=deps, access=build_execution_access(deps),
        settings=SettingsService(config, clock))
    return SimpleNamespace(deps=deps, factory=factory, config=config, service=service)


@pytest.fixture(scope='module')
def template(tmp_path_factory):
    env = compose(tmp_path_factory.mktemp('remote-template'))
    MigrationRunner(env.factory).apply()
    ensure_execution_installation(env.factory)
    with env.factory.unit_of_work() as uow:
        env.deps.repos.agents.upsert(uow, agent_id='operator', role='Operator')
        AgentKeyAuthService(env.deps.repos.agents, env.deps.clock).issue_key(uow, agent_id='operator')
    env.factory.close()
    return env.config.db_path


@pytest.fixture
def env(template, tmp_path):
    home = tmp_path / 'home'
    home.mkdir()
    with sqlite3.connect(template) as source, sqlite3.connect(home / 'nexus.db') as target:
        source.backup(target)
    result = compose(home)
    with result.factory.unit_of_work(write=False) as uow:
        actor = result.deps.repos.agents.get(uow, 'operator')
    result.context = RuntimeRequestContext('operator', 'agent_key', credential_binding=actor.api_key_hash)
    yield result
    result.factory.close()


def request(*, root='remote-one', agent='project-helper'):
    return dict(draft=dict(format='okto.remote-setup-draft', version=1, setup_run_id=root,
        server_origin='https://example.invalid', connector_id='connector-one', project_label='Project',
        agent_hint=None, workspace_hint=None, start_at_login=False,
        installation=dict(adapter_id='codex_app_server', candidate_ref='nexus-install-v1:' + 'a' * 64,
            inventory_revision=None),
        local_consent=dict(local_consent_id='consent-one', local_root_proof_digest=None, configuration_digest=None),
        configuration=parse_portable_connection_configuration(
            configuration(adapter_id='codex_app_server', project='', label='Project'))),
        identity=dict(mode='create', agent_id=agent, display_name='Project helper'),
        workspace=dict(mode='create', workspace_id=None, display_name='Project'))


def reviewed(env, **kwargs):
    review = env.service.review(env.context, request(**kwargs))['review']
    return dict(setup_run_id=review['draft']['setup_run_id'], review_revision=review['review_revision'])


def snapshot(env):
    with env.factory.unit_of_work(write=False) as uow:
        tables = [r[0] for r in uow.connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        return {name: sorted([tuple(row) for row in uow.connection.execute('SELECT * FROM "' + name + '"')], key=repr) for name in tables}


def test_review_no_productive_effect_and_partial_bootstrap_is_atomic(env):
    before = snapshot(env)
    ref = reviewed(env)
    after_review = snapshot(env)
    assert {key for key in before if before[key] != after_review[key]} == {'remote_setup_runs', 'remote_setup_reviews'}
    result = env.service.bootstrap(env.context, ref)
    assert result['state'] == 'awaiting_host' and result['final_binding'] is None
    assert result['material_status'] == 'issued_once' and result['material']['api_key']
    assert result['current_references'] == 'matching'
    after = snapshot(env)
    for table in ('agent_endpoints', 'runtime_profiles', 'runtime_execution_grants', 'execution_bindings',
            'execution_executors', 'execution_sessions', 'execution_operations', 'execution_leases',
            'execution_dispatch_outbox', 'connection_setup_commits'):
        assert after[table] == before[table]
    assert result['material']['api_key'] not in repr(after)
    assert result['bootstrap']['review_revision'] == ref['review_revision']
    assert result['handoff']['review_revision'] == ref['review_revision']


def test_lost_response_recovers_same_references_never_key_or_rotation(env):
    ref = reviewed(env)
    initial = env.service.bootstrap(env.context, ref)
    before = snapshot(env)
    for method in (env.service.recover, env.service.bootstrap):
        replay = method(env.context, ref)
        assert replay['bootstrap'] == initial['bootstrap']
        assert replay['handoff'] == initial['handoff']
        assert replay['material'] is None and replay['material_status'] == 'unavailable'
        assert snapshot(env) == before


def test_participant_and_revoked_principal_cannot_read_or_bootstrap(env):
    ref = reviewed(env)
    with env.factory.unit_of_work() as uow:
        env.deps.repos.agents.upsert(uow, agent_id='other')
        auth = AgentKeyAuthService(env.deps.repos.agents, env.deps.clock)
        auth.issue_key(uow, agent_id='other')
        other = env.deps.repos.agents.get(uow, 'other')
    context = RuntimeRequestContext('other', 'agent_key', credential_binding=other.api_key_hash)
    before = snapshot(env)
    for method in (env.service.recover, env.service.bootstrap):
        with pytest.raises(OktoNexusError):
            method(context, ref)
    assert snapshot(env) == before
    with env.factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agents SET is_active=0 WHERE agent_id='operator'")
    before = snapshot(env)
    for method in (env.service.recover, env.service.bootstrap):
        with pytest.raises(OktoNexusError):
            method(env.context, ref)
    assert snapshot(env) == before


def test_review_retry_deduplicates_but_changed_body_needs_cas(env):
    body = request()
    initial = env.service.review(env.context, body)
    before = snapshot(env)
    assert env.service.review(env.context, body) == initial
    assert snapshot(env) == before
    body['draft']['configuration']['tool_access'] = 'always'
    with pytest.raises(OktoNexusError):
        env.service.review(env.context, body)
    assert snapshot(env) == before


def test_material_rereview_keeps_bootstrap_and_rotates_only_affected_children(env):
    body = request()
    original = env.service.review(env.context, body)['review']
    ref = dict(setup_run_id='remote-one', review_revision=original['review_revision'])
    boot = env.service.bootstrap(env.context, ref)['bootstrap']
    body['draft']['configuration']['alias'] = 'Revised'
    body['expected_review_revision'] = original['review_revision']
    current = env.service.review(env.context, body)['review']
    assert current['child_requests']['register'] == original['child_requests']['register']
    for phase in ('realize', 'prepare', 'apply'):
        assert current['child_requests'][phase] != original['child_requests'][phase]
    recovered = env.service.recover(env.context, {'setup_run_id': 'remote-one'})
    assert recovered['bootstrap'] == boot
    assert recovered['handoff']['review_revision'] == current['review_revision']
    assert recovered['material'] is None
    assert env.service.review(env.context, {k: v for k, v in body.items() if k != 'expected_review_revision'})['review'] == current
    with env.factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM remote_setup_reviews').fetchone()[0] == 2


@pytest.mark.parametrize('field', ['identity', 'workspace', 'connector'])
def test_committed_root_cannot_adopt_another_scope(env, field):
    body = request()
    ref = reviewed(env)
    env.service.bootstrap(env.context, ref)
    body['expected_review_revision'] = ref['review_revision']
    if field == 'identity':
        body['identity']['agent_id'] = 'other'
    elif field == 'workspace':
        body['workspace']['display_name'] = 'Other project'
    else:
        body['draft']['connector_id'] = 'other'
    before = snapshot(env)
    with pytest.raises(OktoNexusError):
        env.service.review(env.context, body)
    assert snapshot(env) == before


def test_existing_identity_review_persists_real_epoch_and_rejects_rotation(env):
    auth = AgentKeyAuthService(env.deps.repos.agents, env.deps.clock)
    with env.factory.unit_of_work() as uow:
        env.deps.repos.agents.upsert(uow, agent_id='existing')
        auth.issue_key(uow, agent_id='existing')
    body = request(agent='existing')
    body['identity']['mode'] = 'select'
    review = env.service.review(env.context, body)['review']
    assert review['selection']['credential'] == {'mode': 'reuse_existing', 'expected_epoch': 1}
    with env.factory.unit_of_work() as uow:
        assert uow.connection.execute("SELECT credential_epoch FROM execution_agent_revisions WHERE agent_id='existing'").fetchone()[0] == 1
        auth.issue_key(uow, agent_id='existing')
    ref = dict(setup_run_id='remote-one', review_revision=review['review_revision'])
    before = snapshot(env)
    with pytest.raises(OktoNexusError):
        env.service.bootstrap(env.context, ref)
    assert snapshot(env) == before
    body['expected_review_revision'] = review['review_revision']
    updated = env.service.review(env.context, body)['review']
    assert updated['selection']['credential']['expected_epoch'] == 2
    result = env.service.bootstrap(env.context, dict(ref, review_revision=updated['review_revision']))
    assert result['material'] is None and result['material_status'] == 'reuse_existing'


def test_concurrent_same_root_creates_once_and_other_root_never_adopts(env):
    ref = reviewed(env)
    other_ref = reviewed(env, root='remote-two')
    peer = compose(env.config.home_dir)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(service.bootstrap, env.context, ref) for service in (env.service, peer.service)]
            results = [f.result(timeout=30) for f in futures]
        assert results[0]['bootstrap'] == results[1]['bootstrap']
        assert sum(result['material'] is not None for result in results) == 1
        before = snapshot(env)
        with pytest.raises(OktoNexusError):
            peer.service.bootstrap(env.context, other_ref)
        assert snapshot(env) == before
    finally:
        peer.factory.close()


@pytest.mark.parametrize('commit_failure', [False, True])
def test_failure_rolls_back_agent_workspace_epoch_and_checkpoint(env, commit_failure):
    ref = reviewed(env)
    with env.factory.unit_of_work() as uow:
        if commit_failure:
            uow.connection.execute('CREATE TABLE rollback_parent(id TEXT PRIMARY KEY)')
            uow.connection.execute('CREATE TABLE rollback_child(id TEXT REFERENCES rollback_parent(id) DEFERRABLE INITIALLY DEFERRED)')
            uow.connection.execute("CREATE TRIGGER injected_failure AFTER UPDATE OF bootstrap_json ON remote_setup_runs BEGIN INSERT INTO rollback_child VALUES('absent'); END")
        else:
            uow.connection.execute("CREATE TRIGGER injected_failure AFTER UPDATE OF bootstrap_json ON remote_setup_runs BEGIN SELECT RAISE(ABORT,'injected'); END")
    before = snapshot(env)
    with pytest.raises((sqlite3.DatabaseError, OktoNexusError)):
        env.service.bootstrap(env.context, ref)
    assert snapshot(env) == before
    with env.factory.unit_of_work() as uow:
        uow.connection.execute('DROP TRIGGER injected_failure')
    assert env.service.bootstrap(env.context, ref)['material_status'] == 'issued_once'


@pytest.mark.parametrize('change', ['credential', 'permissions', 'workspace'])
def test_recovery_reports_unavailable_or_changed_without_repair(env, change):
    ref = reviewed(env)
    boot = env.service.bootstrap(env.context, ref)['bootstrap']
    with env.factory.unit_of_work() as uow:
        if change == 'credential':
            AgentKeyAuthService(env.deps.repos.agents, env.deps.clock).issue_key(uow, agent_id=boot['agent_id'])
        elif change == 'permissions':
            env.deps.repos.agents.set_permissions(uow, agent_id=boot['agent_id'], permissions={'messages': {'send_direct': False}}, preset_id=None)
        else:
            uow.connection.execute('DELETE FROM workspaces WHERE workspace_id=?', (boot['workspace_id'],))
    before = snapshot(env)
    value = env.service.recover(env.context, ref)
    assert value['current_references'] == ('unavailable' if change == 'workspace' else 'changed')
    assert value['material'] is None and value['bootstrap'] == boot
    assert snapshot(env) == before


def test_materialization_missing_is_readonly_and_never_success(env):
    ref = reviewed(env)
    env.service.bootstrap(env.context, ref)
    before = snapshot(env)
    value = env.service.materialization(env.context, ref)
    assert value['state'] == 'needs_canonical_metadata'
    assert value['missing_fields'] == ['canonical_child_proposal']
    assert value['authority_granted'] is False and value['final_binding'] is None
    assert snapshot(env) == before


@pytest.mark.parametrize('keep', [False, True])
def test_reset_preserves_review_only_with_its_identity_configuration(env, keep):
    from okto_nexus.application.database_reset import clear_operational_history
    ref = reviewed(env)
    env.service.bootstrap(env.context, ref)
    with env.factory.unit_of_work() as uow:
        clear_operational_history(uow.connection, keep_agents=keep)
        assert uow.connection.execute('SELECT COUNT(*) FROM remote_setup_runs').fetchone()[0] == int(keep)
        assert uow.connection.execute('SELECT COUNT(*) FROM remote_setup_reviews').fetchone()[0] == int(keep)


def test_draft_rejects_secret_unknown_and_noninteger_version(env):
    body = request()
    before = snapshot(env)
    for bad in (dict(body['draft'], version=True), dict(body['draft'], password='secret'),
            dict(body['draft'], project_label='nxs_' + 'a' * 48)):
        with pytest.raises(OktoNexusError):
            env.service.review(env.context, dict(body, draft=bad))
    assert snapshot(env) == before


def test_normalized_review_never_accepts_mutated_effects(env):
    from okto_nexus.application.remote_setup_contract import validate_review
    value = env.service.review(env.context, request())['review']
    altered = deepcopy(value)
    altered['effects']['productive_turn'] = True
    with pytest.raises(OktoNexusError):
        validate_review(altered)
    assert validate_review(value) == value

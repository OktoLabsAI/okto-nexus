"""Remote review recovery, canonical epoch fences, and additive upgrade."""
from importlib.resources import files
import json

import pytest

import test_remote_setup_server as server
from okto_nexus.adapters.outbound.sqlite.migrations import MigrationRunner
from okto_nexus.application.auth import AgentKeyAuthService
from okto_nexus.domain.runtime_context import RuntimeRequestContext
from okto_nexus.errors import OktoNexusError


env = server.env
template = server.template


def test_lost_rereview_response_recovers_same_committed_revision_and_children(env):
    body = server.request()
    first = env.service.review(env.context, body)['review']
    ref = dict(setup_run_id='remote-one', review_revision=first['review_revision'])
    original = env.service.bootstrap(env.context, ref)['bootstrap']
    body['expected_review_revision'] = first['review_revision']
    body['draft']['start_at_login'] = True
    next_review = env.service.review(env.context, body)
    before = server.snapshot(env)
    assert env.service.review(env.context, body) == next_review
    assert server.snapshot(env) == before
    recovered = env.service.recover(env.context, {'setup_run_id': 'remote-one'})
    assert recovered['review'] == next_review['review']
    assert recovered['bootstrap'] == original and recovered['material'] is None
    assert recovered['handoff']['child_requests']['realize'] == first['child_requests']['realize']


def test_self_recovery_scope_is_current_key_and_unambiguous_not_root_id(env):
    ref = server.reviewed(env)
    boot = env.service.bootstrap(env.context, ref)['bootstrap']
    with env.factory.unit_of_work(write=False) as uow:
        agent = env.deps.repos.agents.get(uow, boot['agent_id'])
    context = RuntimeRequestContext(agent.agent_id, 'agent_key', credential_binding=agent.api_key_hash)
    before = server.snapshot(env)
    assert env.service.recover(context, ref)['bootstrap'] == boot
    assert server.snapshot(env) == before
    for method in (env.service.bootstrap, env.service.materialization):
        with pytest.raises(OktoNexusError):
            method(context, ref)
    # Seed a second namespace using the actual repository, never borrowing its
    # operator authority. Subject recovery cannot select by an untrusted actor ID.
    with env.factory.unit_of_work() as uow:
        original = env.deps.repos.remote_setup.get(uow, actor='operator', setup_run_id='remote-one')
        env.deps.repos.remote_setup.save_review(uow, actor='other-operator', review=original['review'],
            request_hash=original['request_hash'], expected_revision=None, now=env.deps.clock.now_iso())
        env.deps.repos.remote_setup.save_bootstrap(uow, actor='other-operator', setup_run_id='remote-one',
            revision=ref['review_revision'], receipt=boot, baseline=original['bootstrap_baseline'], now=env.deps.clock.now_iso())
    with pytest.raises(OktoNexusError, match='not found'):
        env.service.recover(context, {'setup_run_id': 'remote-one'})
    # Operator namespace remains exact despite subject ambiguity.
    assert env.service.recover(env.context, ref)['bootstrap'] == boot


def test_readonly_projection_never_collapses_two_real_key_rotations(env):
    auth = AgentKeyAuthService(env.deps.repos.agents, env.deps.clock)
    with env.factory.unit_of_work() as uow:
        env.deps.repos.agents.upsert(uow, agent_id='existing')
        auth.issue_key(uow, agent_id='existing')
    body = server.request(agent='existing')
    body['identity']['mode'] = 'select'
    original = env.service.review(env.context, body)['review']
    with env.factory.unit_of_work() as uow:
        auth.issue_key(uow, agent_id='existing')
    body['expected_review_revision'] = original['review_revision']
    second = env.service.review(env.context, body)['review']
    assert second['selection']['credential']['expected_epoch'] == 2
    with env.factory.unit_of_work() as uow:
        auth.issue_key(uow, agent_id='existing')
    ref = dict(setup_run_id='remote-one', review_revision=second['review_revision'])
    before = server.snapshot(env)
    with pytest.raises(OktoNexusError):
        env.service.bootstrap(env.context, ref)
    assert server.snapshot(env) == before


def test_selected_existing_identity_bootstrap_changes_no_existing_runtime_policy(env):
    auth = AgentKeyAuthService(env.deps.repos.agents, env.deps.clock)
    with env.factory.unit_of_work() as uow:
        env.deps.repos.agents.upsert(uow, agent_id='existing')
        auth.issue_key(uow, agent_id='existing')
        uow.connection.execute("INSERT INTO agent_execution_policies VALUES('existing','local','codex_app_server',17)")
    body = server.request(agent='existing')
    body['identity']['mode'] = 'select'
    review = env.service.review(env.context, body)['review']
    before = server.snapshot(env)
    result = env.service.bootstrap(env.context, dict(setup_run_id='remote-one', review_revision=review['review_revision']))
    assert result['material'] is None
    after = server.snapshot(env)
    for table in ('agent_execution_policies', 'agent_runtime_overrides', 'runtime_execution_grants', 'agents',
                  'agent_endpoints', 'runtime_profiles', 'execution_bindings'):
        assert after[table] == before[table]


def test_completed_root_recovers_persisted_references_after_child_history_retention(env):
    ref = server.reviewed(env)
    boot = env.service.bootstrap(env.context, ref)['bootstrap']
    final = dict(server_id=boot['server_id'], agent_id=boot['agent_id'], workspace_id=boot['workspace_id'],
        executor_id='executor', binding_id='binding', proposal_id='proposal', finish_id='proposal_setup')
    # A canonical Finish hook stores this shape; its real producer is exercised
    # by the TCP test. Here only the retained read/immutability contract is tested.
    with env.factory.unit_of_work() as uow:
        uow.connection.execute('UPDATE remote_setup_runs SET final_binding_json=?', (json.dumps(final),))
    before = server.snapshot(env)
    recovered = env.service.recover(env.context, ref)
    assert recovered['state'] == 'committed' and recovered['final_binding'] == final
    assert server.snapshot(env) == before
    body = server.request()
    body['expected_review_revision'] = ref['review_revision']
    body['draft']['configuration']['alias'] = 'New'
    with pytest.raises(OktoNexusError):
        env.service.review(env.context, body)


@pytest.mark.parametrize('fail_late', [False, True])
def test_upgrade_166_is_additive_idempotent_and_atomic(tmp_path, fail_late):
    old_dir = tmp_path / 'old'
    old_dir.mkdir()
    resources = files('okto_nexus').joinpath('migrations')
    for item in resources.iterdir():
        if item.name.endswith('.sql') and int(item.name.split('_')[0]) <= 166:
            (old_dir / item.name).write_bytes(item.read_bytes())
    env = server.compose(tmp_path / 'home')
    try:
        MigrationRunner(env.factory, old_dir).apply()
        with env.factory.unit_of_work() as uow:
            env.deps.repos.agents.upsert(uow, agent_id='existing', metadata={'keep': 'original'})
        before = server.snapshot(env)
        migration = resources.joinpath('167_remote_setup.sql').read_text(encoding='utf-8')
        new_dir = tmp_path / 'new'
        new_dir.mkdir()
        for path in old_dir.iterdir():
            (new_dir / path.name).write_bytes(path.read_bytes())
        (new_dir / '167_remote_setup.sql').write_text(migration + ('\nSELECT absent_function();\n' if fail_late else ''), encoding='utf-8')
        if fail_late:
            with pytest.raises(OktoNexusError):
                MigrationRunner(env.factory, new_dir).apply()
            assert server.snapshot(env) == before
        else:
            assert MigrationRunner(env.factory, new_dir).apply() == [167]
            after = server.snapshot(env)
            assert after['agents'] == before['agents']
            assert after['remote_setup_runs'] == after['remote_setup_reviews'] == []
            assert MigrationRunner(env.factory, new_dir).apply() == []
            assert server.snapshot(env) == after
    finally:
        env.factory.close()


def test_secret_and_duplicate_json_are_rejected_without_review_effect(env):
    from okto_nexus.application.remote_setup_contract import parse_document
    before = server.snapshot(env)
    for raw in ('{"x":1,"x":2}', '{"x":NaN}', '{"x":"nxs_' + 'z' * 64 + '"}'):
        with pytest.raises(OktoNexusError):
            parse_document(raw)
    assert server.snapshot(env) == before

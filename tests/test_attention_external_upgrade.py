"""Additive 164-to-165 upgrade and explicit summary failure boundaries."""
import shutil

import pytest

from okto_nexus.adapters.outbound.sqlite.connection import ConnectionFactory
from okto_nexus.adapters.outbound.sqlite.migrations import MigrationRunner, _default_migrations_dir
from okto_nexus.errors import OktoNexusError
from test_observation_service import OPERATOR, obs, publish, snapshot  # noqa: F401


def test_upgrade_preserves_existing_observation_and_business_bytes(tmp_config, tmp_path, fake_clock):
    old = tmp_path / 'schema-164'
    old.mkdir()
    for path in _default_migrations_dir().glob('*.sql'):
        if int(path.name.split('_')[0]) <= 164:
            shutil.copyfile(path, old / path.name)
    factory = ConnectionFactory(tmp_config)
    try:
        assert MigrationRunner(factory, migrations_dir=old).apply()[-1] == 164
        env = obs.__wrapped__(factory, tmp_config, fake_clock)
        publish(env, state='blocked', current_completion_ref='historical-completion')
        before = snapshot(env, auxiliary=True)
        before.pop('schema_migrations')
        assert 165 in MigrationRunner(factory).apply()
        after = snapshot(env, auxiliary=True)
        assert {key: after[key] for key in before} == before
        with factory.unit_of_work(write=False) as uow:
            anchor = dict(uow.connection.execute('SELECT * FROM observation_attention_anchors').fetchone())
        assert anchor == dict(observed_instance_id=env.instance['observed_instance_id'],
            generation=env.instance['generation'], blocked_sequence=1,
            blocked_started_at=env.service.read(context=OPERATOR)['items'][0]['last_report']['received_at'])
        assert MigrationRunner(factory).apply() == []
        assert snapshot(env, auxiliary=True) == after
        with pytest.raises(OktoNexusError, match='MIGRATION_ERROR'):
            MigrationRunner(factory, migrations_dir=old).apply()
        assert snapshot(env, auxiliary=True) == after
    finally:
        factory.close()


def test_summary_query_budget_returns_error_and_releases_progress_handler(obs, monkeypatch):
    from okto_nexus.adapters.outbound.sqlite import observations_repo
    ticks = iter([0, 6])
    with obs.factory.unit_of_work(write=False) as uow:
        with monkeypatch.context() as changes:
            changes.setattr(observations_repo.time, 'monotonic', lambda: next(ticks, 6))
            with pytest.raises(OktoNexusError, match='OBSERVATION_QUERY_BUDGET'):
                obs.repos.observations.all_current(uow)
        # A pooled connection must not retain the expired request deadline.
        assert uow.connection.execute('SELECT count(*) FROM observation_instances').fetchone()[0] == 1


def test_summary_never_truncates_preexisting_instances_after_policy_reduction(obs):
    env = obs
    with env.factory.unit_of_work() as uow:
        for index in range(205):
            env.repos.observations.create_instance(uow, source_id=env.source['source_id'],
                expected_revision=env.source['revision'], workspace_id='ws',
                external_instance_ref='aggregate-' + str(index), now=env.clock.now_iso())
    env.config.observation_max_instances = 1
    result = env.service.summary(context=OPERATOR)
    assert result['total_instances'] == 206
    assert result['activity']['unknown'] == result['freshness']['unknown'] == 206
    assert result['agents'][0]['total_instances'] == 206

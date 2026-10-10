import pytest

from test_one_shot_capacity import conn
from okto_nexus.application import one_shot_settings as settings
from okto_nexus.errors import OktoNexusError


def test_global_and_independent_agent_overrides(conn):
    initial = settings.read(conn)
    global_value = settings.save(conn, expected_revision=1,
        settings=initial['settings'] | dict(max_parallel=10, warm_instances=5))
    assert global_value['revision'] == 2
    agent = settings.save(conn, agent_id='agent', expected_revision=0, settings={'max_parallel': 6})
    assert agent['effective']['max_parallel'] == 6 and agent['effective']['warm_instances'] == 5
    inherited = settings.save(conn, agent_id='agent', expected_revision=1, settings={'max_parallel': None})
    assert inherited['effective'] == global_value['effective']


def test_global_change_cannot_break_agent_warm_override(conn):
    base = settings.read(conn)
    settings.save(conn, expected_revision=1, settings=base['settings'] | dict(max_parallel=10))
    settings.save(conn, agent_id='agent', expected_revision=0, settings={'warm_instances': 5})
    with pytest.raises(OktoNexusError):
        settings.save(conn, expected_revision=2, settings=base['settings'] | dict(max_parallel=3))
    assert settings.read(conn)['effective']['max_parallel'] == 10


def test_stale_revision_rejected(conn):
    base = settings.read(conn)
    with pytest.raises(OktoNexusError):
        settings.save(conn, expected_revision=0, settings=base['settings'])


def test_unlimited_override_is_distinct_from_inheritance(conn):
    result = settings.save(conn, agent_id='agent', expected_revision=0,
                           settings={'max_parallel': 0, 'warm_instances': 4})
    assert result['effective']['max_parallel'] == 0
    assert result['effective']['warm_instances'] == 4
    result = settings.save(conn, agent_id='agent', expected_revision=1, settings={})
    assert result['effective']['max_parallel'] == 1


@pytest.mark.parametrize('changes', [{'max_parallel': True}, {'warm_instances': 1}, {'extra': 'value'}])
def test_invalid_override_rejected(conn, changes):
    with pytest.raises(OktoNexusError):
        settings.save(conn, agent_id='agent', expected_revision=0, settings=changes)


def test_missing_agent_cannot_have_policy(conn):
    with pytest.raises(OktoNexusError):
        settings.save(conn, agent_id='missing', expected_revision=0, settings={})


def test_reset_without_agents_keeps_defaults_but_discards_agent_overrides(conn):
    from okto_nexus.application.database_reset import clear_operational_history
    settings.save(conn, agent_id='agent', expected_revision=0, settings={'max_parallel': 5})
    conn.execute('CREATE TABLE runtime_reset_generation(singleton,generation)')
    conn.execute('INSERT INTO runtime_reset_generation VALUES(1,0)')
    clear_operational_history(conn, keep_agents=False)
    assert settings.read(conn)['effective']['max_parallel'] == 1
    assert conn.execute('SELECT scope FROM one_shot_policy_settings').fetchall()[0][0] == 'global'
    assert conn.execute('SELECT count(*) FROM one_shot_policy_settings').fetchone()[0] == 1
    assert not conn.execute('SELECT * FROM agents').fetchall()

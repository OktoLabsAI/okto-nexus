"""One bounded read relation serves consistent counts and an ordered page."""
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from okto_nexus.adapters.outbound.sqlite import attention as query_module
from okto_nexus.application import attention_external
from okto_nexus.domain.attention import normalize_filters
from okto_nexus.errors import OktoNexusError
from test_attention_external import external as _external_fixture
from test_attention_external_query import mixed
from test_observation_service import OPERATOR, obs as _obs_fixture, publish, snapshot

external, obs = _external_fixture, _obs_fixture


@pytest.mark.parametrize('limit', [0, 1, 2, 200])
def test_counts_and_page_share_one_relation_and_preserve_zero_limit(external, monkeypatch, limit):
    env = external
    mixed(env)
    full = env.attention.read(context=OPERATOR, filters=dict(state='all'), limit=200)
    calls = []
    original = attention_external.project
    def project(*args):
        calls.append(1)
        return original(*args)
    monkeypatch.setattr(attention_external, 'project', project)
    statements = []
    with env.factory.unit_of_work(write=False) as uow:
        conn = uow.connection
        before = conn.total_changes
        conn.set_trace_callback(statements.append)
        try:
            value = env.attention.queries.snapshot(uow, filters=normalize_filters(dict(state='all')),
                now=env.clock.now_iso(), config=env.config, access=env.attention.access, context=OPERATOR, limit=limit)
        finally:
            conn.set_trace_callback(None)
        assert conn.total_changes == before
    assert len(calls) == 6
    assert len([sql for sql in statements if sql.lstrip().startswith('WITH source_facts AS')]) == 1
    assert not any(sql.lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE', 'REPLACE', 'CREATE')) for sql in statements)
    assert value['total'] == full['total'] == 7 and value['counts'] == full['counts']
    assert value['items'] == (full['items'][:limit + 1] if limit else [])
    assert value['snapshot_revision'] == full['snapshot_revision']


def test_public_paging_preserves_order_preferences_totals_and_exact_items(external):
    env = external
    mixed(env)
    initial = env.attention.read(context=OPERATOR, filters=dict(state='all'), limit=200)
    completion = next(item for item in initial['items'] if item['kind'] == 'external_completion_unseen')
    env.attention.mark_seen(context=OPERATOR, attention_id=completion['attention_id'],
        source_revision=completion['source_revision'], preference_revision=0)
    expected = env.attention.read(context=OPERATOR, filters=dict(state='all'), limit=200)
    collected, cursor = [], None
    for _ in range(4):
        page = env.attention.read(context=OPERATOR, filters=dict(state='all'), cursor=cursor, limit=2)
        assert page['total'] == expected['total'] and page['counts'] == expected['counts']
        assert page['snapshot_revision'] == expected['snapshot_revision']
        collected.extend(page['items'])
        cursor = page['next_cursor']
    assert cursor is None
    assert collected == expected['items']
    assert len({item['attention_id'] for item in collected}) == len(collected)
    assert any(item['seen_state']['seen'] for item in collected)


def test_cursor_conflict_after_preference_change_is_still_explicit(external):
    env = external
    mixed(env)
    page = env.attention.read(context=OPERATOR, filters=dict(state='all'), limit=1)
    item = page['items'][0]
    assert page['next_cursor']
    env.attention.mark_seen(context=OPERATOR, attention_id=item['attention_id'],
        source_revision=item['source_revision'], preference_revision=0)
    with pytest.raises(OktoNexusError) as error:
        env.attention.read(context=OPERATOR, filters=dict(state='all'), cursor=page['next_cursor'], limit=1)
    assert error.value.code == 'CONFLICT'
    assert error.value.details['reason'] == 'ATTENTION_SNAPSHOT_CHANGED'


def test_duplicate_episode_still_fails_instead_of_returning_page(external, monkeypatch):
    env = external
    publish(env, state='blocked')
    original = attention_external.project
    monkeypatch.setattr(attention_external, 'project', lambda *args: original(*args) * 2)
    with pytest.raises(OktoNexusError) as error:
        env.attention.read(context=OPERATOR, filters=dict(kind='external_blocked'), limit=1)
    assert error.value.code == 'DB_ERROR'


def test_authorization_projection_counts_and_page_use_one_readonly_uow(external, monkeypatch):
    env = external
    publish(env, state='blocked')
    before = snapshot(env, auxiliary=True)
    entered = []
    original = env.factory.unit_of_work
    @contextmanager
    def observed(*args, **kwargs):
        assert kwargs.get('write') is False
        entered.append(1)
        with original(*args, **kwargs) as uow:
            changes = uow.connection.total_changes
            yield uow
            assert uow.connection.total_changes == changes
    with monkeypatch.context() as patch:
        patch.setattr(env.factory, 'unit_of_work', observed)
        assert env.attention.read(context=OPERATOR)['total'] == 1
    assert len(entered) == 1
    assert snapshot(env, auxiliary=True) == before


@pytest.mark.parametrize('filters', [dict(agent_id='bob'), dict(workspace_id='other')])
def test_empty_scope_has_empty_page_and_zero_counts(external, filters):
    env = external
    publish(env, state='blocked')
    result = env.attention.read(context=OPERATOR, filters=filters)
    summary = env.attention.summary(context=OPERATOR, filters=filters)
    assert result['items'] == [] and result['next_cursor'] is None
    assert result['total'] == summary['total'] == 0
    assert result['counts'] == summary['counts']
    assert all(value == 0 for key, value in result['counts'].items() if key != 'priority')
    assert all(value == 0 for value in result['counts']['priority'].values())


def test_revocation_and_preferences_are_reloaded_between_queries(external):
    env = external
    publish(env, state='blocked')
    first = env.attention.read(context=OPERATOR, filters=dict(kind='external_blocked'))['items'][0]
    env.attention.mark_seen(context=OPERATOR, attention_id=first['attention_id'],
        source_revision=first['source_revision'], preference_revision=0)
    second = env.attention.read(context=OPERATOR, filters=dict(kind='external_blocked'))['items'][0]
    assert second['seen_state']['seen'] and second['active']
    env.service.revoke_token(context=OPERATOR, source_id=env.source['source_id'], token_id=env.credential['token_id'])
    assert env.attention.read(context=OPERATOR, filters=dict(kind='external_blocked'))['items'] == []
    unavailable = env.attention.read(context=OPERATOR, filters=dict(kind='external_blocked', state='all'))['items'][0]
    assert unavailable['freshness'] == 'unavailable' and unavailable['active'] is False


def test_deadline_crossed_by_last_callback_refuses_snapshot_and_connection_recovers(external, monkeypatch):
    env = external
    publish(env, state='blocked')
    clock, calls = [0.0], []
    original = attention_external.project
    def late(*args):
        calls.append(1)
        value = original(*args)
        clock[0] = 5.0
        return value
    with monkeypatch.context() as patch:
        patch.setattr(query_module, 'time', SimpleNamespace(monotonic=lambda: clock[0]))
        patch.setattr(attention_external, 'project', late)
        with pytest.raises(OktoNexusError) as error:
            env.attention.read(context=OPERATOR, filters=dict(kind='external_blocked'))
    assert error.value.code == 'ATTENTION_QUERY_BUDGET' and calls == [1]
    assert env.attention.queries.QUERY_SECONDS == 5.0
    assert env.attention.read(context=OPERATOR, filters=dict(kind='external_blocked'))['total'] == 1

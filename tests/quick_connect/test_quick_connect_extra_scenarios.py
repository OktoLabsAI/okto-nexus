"""QC14 canonical regression scenarios; historical external cuts are recorded in execution.

Canonical SQLite/HTTP authorities with synthetic Test/version peers only.
No provider, personal installation or native harness execution.
"""
import json
from urllib.parse import urlencode
from datetime import datetime, timedelta, timezone

import pytest

from test_quick_connect_cli import (  # noqa: F401
    checking as checking, first_connection, invoke, isolated_provider_environment as isolated_provider_environment, local_setup as local_setup,
    quick_cli as quick_cli, terminal as terminal,
)


TABLES = ('connection_setup_commits', 'execution_bindings', 'agent_endpoints',
          'runtime_execution_grants', 'agent_execution_policies', 'agent_runtime_overrides',
          'connection_public_ids', 'connection_project_drafts', 'agents', 'workspaces')


def canonical_snapshot(cli):
    with cli.t.deps.connection_factory.unit_of_work(write=False) as uow:
        return {table: sorted([{key: row[key] for key in row.keys() if not (table == 'agents' and key == 'last_seen_at')}
                              for row in uow.connection.execute('SELECT * FROM ' + table)], key=repr)
                for table in TABLES}


def public_row(cli, name, workspace):
    with cli.t.deps.connection_factory.unit_of_work(write=False) as uow:
        row = uow.connection.execute('SELECT * FROM connection_public_ids WHERE connect_id=? AND workspace_id=?',
                                     (name, workspace)).fetchone()
        assert row is not None
        return dict(row)


def test_e03_second_same_harness_add_without_id_proposes_codex_2(quick_cli, capsys):
    c = quick_cli
    _, _, first = first_connection(c, capsys)
    original_profile = (c.home / 'terminal/profiles/first.json').read_bytes()
    original_public = public_row(c, 'codex', first['workspace_id'])
    before = canonical_snapshot(c)
    base = ['connect', 'codex', 'Logical App', '--profile', 'second-auto', '--new-connection',
            '--workspace-id', first['workspace_id'], '--json']
    review = invoke(c, capsys, [*base, '--plan'])
    assert review['quick_connect']['proposed_connect_id'] == 'codex-2'
    assert canonical_snapshot(c) == before and len(c.t.turns) == 1
    second = invoke(c, capsys, [*base, '--approve', review['review_revision']])
    assert second['quick_connect']['connect_id'] == 'codex-2'
    assert second['workspace_id'] == first['workspace_id']
    assert second['binding_id'] != first['binding_id'] and second['agent_id'] != first['agent_id']
    assert second['quick_connect']['canonical_reference'] != first['quick_connect']['canonical_reference']
    assert (c.home / 'terminal/profiles/first.json').read_bytes() == original_profile
    assert public_row(c, 'codex', first['workspace_id']) == original_public
    after = canonical_snapshot(c)
    for table in ('execution_bindings', 'agent_endpoints', 'runtime_execution_grants'):
        assert all(row in after[table] for row in before[table]), table
    assert len(c.t.turns) == 2


@pytest.mark.parametrize('existing_project', [False, True])
def test_h06_explicit_add_plan_preserves_public_namespace_and_project_drafts(quick_cli, capsys, existing_project):
    c = quick_cli
    workspace = None
    if existing_project:
        _, _, first = first_connection(c, capsys)
        workspace = first['workspace_id']
    before = canonical_snapshot(c)
    turns, probes = tuple(c.t.turns), tuple(c.t.probes)
    base = ['connect', 'codex', 'Logical App', '--profile', 'plan-only', '--new-connection',
            '--id', 'planned-reviewer', '--plan', '--json']
    if workspace:
        base += ['--workspace-id', workspace]
    review = invoke(c, capsys, base)
    assert review['state'] == 'review'
    assert review['quick_connect']['proposed_connect_id'] == 'planned-reviewer'
    assert canonical_snapshot(c) == before
    assert tuple(c.t.turns) == turns and tuple(c.t.probes) == probes
    assert review['quick_connect']['status'] == 'planned'


def test_g13_expired_canonical_grants_are_not_renewed_by_resume(quick_cli, capsys):
    c = quick_cli
    _, _, first = first_connection(c, capsys)
    # Deliberate own-fixture historical read fact: keep a coherent original
    # created/expires interval wholly in the past. This is not an API renewal,
    # permission bypass or claim that an expired grant authorizes execution.
    expired = datetime.now(timezone.utc) - timedelta(days=1)
    created = expired - timedelta(minutes=10)
    with c.t.deps.connection_factory.unit_of_work() as uow:
        endpoint = first['quick_connect']['canonical_reference']['endpoint_id']
        changed = uow.connection.execute('UPDATE runtime_execution_grants SET created_at=?,expires_at=?,no_expiry=0 '
            'WHERE endpoint_id=?', (created.isoformat(), expired.isoformat(), endpoint)).rowcount
        assert changed >= 1
    before = canonical_snapshot(c)
    turns, probes = tuple(c.t.turns), tuple(c.t.probes)
    result = invoke(c, capsys, ['connect', '--profile', 'first', '--json'])
    assert result['state'] == 'configured' and result['binding_id'] == first['binding_id']
    assert result['quick_connect']['operation'] == 'reused'
    assert result['session_state'] == 'not_checked' and result['work_state'] == 'not_submitted'
    assert canonical_snapshot(c) == before
    assert tuple(c.t.turns) == turns and tuple(c.t.probes) == probes
    for grant in before['runtime_execution_grants']:
        assert grant in canonical_snapshot(c)['runtime_execution_grants']


def test_f17_free_id_review_loses_race_before_new_test_identity_or_grant(quick_cli, capsys):
    c = quick_cli
    _, _, first = first_connection(c, capsys)
    first_profile = (c.home / 'terminal/profiles/first.json').read_bytes()
    first_public = public_row(c, 'codex', first['workspace_id'])
    def base(profile):
        return ['connect', 'codex', 'Logical App', '--profile', profile, '--new-connection',
                '--workspace-id', first['workspace_id'], '--id', 'raced-reviewer', '--json']
    losing = invoke(c, capsys, [*base('loser'), '--plan'])
    winner_review = invoke(c, capsys, [*base('winner'), '--plan'])
    assert losing['review_revision'] != winner_review['review_revision']
    winner = invoke(c, capsys, [*base('winner'), '--approve', winner_review['review_revision']])
    assert winner['quick_connect']['connect_id'] == 'raced-reviewer'
    winner_public = public_row(c, 'raced-reviewer', first['workspace_id'])
    assert json.loads(winner_public['canonical_ref_json']) == winner['quick_connect']['canonical_reference']
    old_request = json.loads((c.home / 'terminal/profiles/loser.json').read_text())['request']
    current_proof = c.t.call('GET', '/api/v1/runtime-management/connections/project-context?' + urlencode(dict(
        executor_id=old_request['executor_id'], workspace_id=first['workspace_id'], project_root=str(c.project))))
    assert current_proof['project_revision'] != old_request['public_connection']['project_revision']
    before = canonical_snapshot(c)
    turns = tuple(c.t.turns)
    call_index = len(c.t.calls)
    result = invoke(c, capsys, [*base('loser'), '--approve', losing['review_revision']], expected=3)
    assert result['state'] in ('refused', 'unconfirmed')
    assert (result['code'], result['message']) == ('CONFLICT', 'The selected project or directory changed. Review it again.'), result
    assert canonical_snapshot(c) == before
    assert tuple(c.t.turns) == turns
    assert not any(method == 'POST' and path.endswith(('setup:test', 'setup:finish'))
                   for method, path in c.t.calls[call_index:])
    assert (c.home / 'terminal/profiles/first.json').read_bytes() == first_profile
    assert public_row(c, 'codex', first['workspace_id']) == first_public
    assert public_row(c, 'raced-reviewer', first['workspace_id']) == winner_public
    saved = json.loads((c.home / 'terminal/profiles/loser.json').read_text())
    assert saved['state'] not in ('test_submitted', 'finish', 'done')


# Explicit public exports include pytest fixtures used through injection.
__all__ = ['TABLES', 'canonical_snapshot', 'checking', 'datetime', 'first_connection', 'invoke', 'isolated_provider_environment', 'json', 'local_setup', 'public_row', 'pytest', 'quick_cli', 'terminal', 'test_e03_second_same_harness_add_without_id_proposes_codex_2', 'test_f17_free_id_review_loses_race_before_new_test_identity_or_grant', 'test_g13_expired_canonical_grants_are_not_renewed_by_resume', 'test_h06_explicit_add_plan_preserves_public_namespace_and_project_drafts', 'timedelta', 'timezone', 'urlencode']

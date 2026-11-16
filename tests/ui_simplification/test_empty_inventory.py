"""An empty selected page is never authority for first-connection onboarding."""
import sqlite3

from okto_nexus.adapters.outbound.sqlite import home_entries as sqlite_entries
from okto_nexus.domain.home_entries import EntryRelations
from okto_nexus.domain.home_entry_pages import filters, page
from .test_entry_pages import scenario as scenario, service_for
from .test_fixtures import fixtures


def test_inventory_is_authorized_pre_filter_and_unknown_after_source_failure(request, monkeypatch):
    s = request.getfixturevalue('scenario')
    service = service_for(s)
    scope = {'workspace_id': 'ws', 'quick': 'all'}
    complete = service.read(context=s.operator, filters=scope)
    assert complete['inventory']['connections'] == dict(value=2, total_is_exact=True, unit='connections')
    empty_selection = service.read(context=s.operator, filters=dict(scope, harness='not-installed'))
    assert empty_selection['items'] == [] and empty_selection['total'] == 0
    assert empty_selection['inventory'] == complete['inventory']
    # Workspace scope is applied in the canonical source, not by React.
    with s.factory.unit_of_work() as uow:
        workspace = uow.connection.execute("SELECT * FROM workspaces WHERE workspace_id='ws'").fetchone()
        fixtures._copy(uow.connection, 'workspaces', workspace, workspace_id='wsb',
                       root_realpath=str(s.deps.config.home_dir / 'other-workspace'))
    other = service.read(context=s.operator, filters={'workspace_id': 'wsb', 'quick': 'all'})
    assert other['inventory']['connections']['value'] == 0

    original = service.queries._rows

    def fail_connections(uow, sql, params, check_budget=None):
        if sql == sqlite_entries.CONNECTIONS:
            raise sqlite3.OperationalError('controlled own connection-source failure')
        return original(uow, sql, params, check_budget)

    monkeypatch.setattr(service.queries, '_rows', fail_connections)
    failed = service.read(context=s.operator, filters=scope)
    assert failed['source_status']['connections'] == 'unavailable'
    assert failed['inventory']['connections'] == dict(value=None, total_is_exact=False, unit='connections')


def test_empty_adapters_default_unknown_and_proven_zero_changes_revision():
    now = '2026-11-16T12:00:00.000000Z'
    status = {key: 'ready' for key in ('work', 'results', 'attention', 'connections', 'sessions', 'correlations', 'external')}
    relation = EntryRelations([], [], status)
    unknown = page(relation, scope=filters({}), server_id='server', principal='operator', now=now)
    assert unknown['inventory']['connections']['value'] is None
    relation.connection_count = 0
    empty = page(relation, scope=filters({}), server_id='server', principal='operator', now=now)
    assert empty['inventory']['connections']['value'] == 0
    assert empty['revision'] != unknown['revision']

"""One existing-Home-authorized UoW for entries, groups and exact children.

This implementation materializes O(N+relationships), bounded by source budgets
and a global processing deadline. It does not claim O(page) database work.
"""
from contextlib import ExitStack
import time

from ..domain.attention import normalize_filters
from ..domain.home_entries import EntryRelations
from ..domain import home_entry_pages as pages
from ..domain import home_board
from ..domain import home_harness_board
from ..errors import ErrorCode, OktoNexusError
from ..domain.home import digest
from .home_ports import HomeEntryQueries


class HomeEntriesService:
    QUERY_SECONDS = 5.0

    def __init__(self, home_service, *, queries: HomeEntryQueries):
        self.home = home_service
        self.queries = queries

    def read(self, *, context, principal=None, filters=None, partition='groups', group_id=None, entry_id=None,
             cursor=None, limit=10, preview=3):
        if partition in ('board', 'harness_board', 'harness_children', 'harness_unlinked'):
            if filters and 'quick' in filters:
                pages.invalid('Home board does not accept a quick filter.')
            if partition in ('board', 'harness_board') and group_id is not None and group_id not in home_board.COLUMNS:
                pages.invalid('Invalid Home board column.')
            if entry_id is not None:
                pages.invalid('Home board does not accept an entry parent.')
            filters = dict(filters or {}, quick='all')
        scope = pages.filters(filters)
        started = time.monotonic()

        def check_budget():
            if time.monotonic() - started > self.QUERY_SECONDS:
                raise OktoNexusError('HOME_QUERY_BUDGET', 'Home entries processing budget exceeded; narrow the scope.', {})

        with self.home.factory.unit_of_work(write=False) as uow:
            # Existing policy remains the only authorization boundary. It runs
            # before all source queries, joins, counts and cursor validation.
            server, now, config = self.home._basis(uow, context, scope)
            bounds = uow.connection.execute("SELECT COALESCE((SELECT seq FROM sqlite_sequence WHERE name='events'),0),(SELECT MIN(event_id) FROM events)").fetchone()
            if context.authentication_source == 'operator_session' and (
                    type(principal) is not str or not principal or len(principal) > 160 or not principal.isprintable()):
                raise OktoNexusError(ErrorCode.PERMISSION_DENIED, 'The authenticated human identity is unavailable.', {})
            principal = digest([context.authentication_source, context.actor_agent_id, context.credential_binding,
                principal if context.authentication_source == 'operator_session' else None])
            value = self.home._safe(now, lambda: self._read(uow, scope=scope, server=server,
                now=now, config=config, context=context, principal=principal,
                partition=partition, group_id=group_id, entry_id=entry_id, cursor=cursor,
                limit=limit, preview=preview, check_budget=check_budget))
            if 'version' not in value:
                value.update(version=1, scope=scope, server_id=server, generated_at=now,
                    snapshot_id=None, revision=None, partition=partition, group_id=group_id,
                    entry_id=entry_id, source_status={'entries': value['status']},
                    inventory=dict(connections=dict(value=None, total_is_exact=False, unit='connections')),
                    coverage={'result_tracking': 'unknown'},
                    summary={key: dict(value=None, total_is_exact=False,
                        unit='results' if key == 'unseen_results' else key)
                        for key in ('activities', 'external_instances', 'occurrences', 'sessions', 'results', 'unseen_results')},
                    server_attention=dict(status='unavailable', items=[], total=None,
                        total_is_exact=False, has_more=False))
                value['source_status'] = {key: 'unavailable' for key in
                    ('work', 'results', 'attention', 'connections', 'sessions', 'correlations', 'external')}
            value.update(event_cursor=int(bounds[0]), event_low_watermark=bounds[1])
            if partition == 'board' and 'entry_revision' not in value:
                value = home_board.unavailable(value, group_id)
            if partition.startswith('harness_') and 'entry_revision' not in value:
                value = home_harness_board.unavailable(value,
                    partition='children' if partition == 'harness_children' else 'unlinked' if partition == 'harness_unlinked' else 'column' if group_id else 'root',
                    column=group_id if partition == 'harness_board' else None,
                    card_id=group_id if partition == 'harness_children' else None)
            return value

    def _read(self, uow, *, scope, server, now, config, context, principal,
              partition, group_id, entry_id, cursor, limit, preview, check_budget):
        relation = None
        with ExitStack() as sources:
            if config.feature_attention:
                attempt = self.home._safe(now, lambda: sources.enter_context(self.home.attention.queries._relation(uow,
                        filters=normalize_filters({'state': 'all'}), now=now, config=config,
                        access=self.home.access, context=context,
                        source_scope={'workspace_id': scope.get('workspace_id')})))
                if isinstance(attempt, tuple):
                    relation = attempt
            check_budget()
            relations = self.queries.read(uow, scope=scope, server_id=server, now=now,
                attention_relation=relation, check_budget=check_budget)
            if not isinstance(relations, EntryRelations):
                raise TypeError('Home entries query returned an invalid internal relation')
            external = self.home._safe(now, lambda: self.queries.external(uow, scope=scope,
                server_id=server, now=now, config=config, observations=self.home.observations,
                relations=relations, check_budget=check_budget))
            if external is not None:
                relations.source_status['external'] = external['status']
            if partition.startswith('harness_'):
                self.home._safe(now, lambda: self.queries.blocking(uow, scope=scope,
                    server_id=server, relations=relations, check_budget=check_budget))
            check_budget()
            if partition.startswith('harness_'):
                value = home_harness_board.page(relations, scope=scope, server_id=server, principal=principal,
                    now=now, partition='children' if partition == 'harness_children' else 'unlinked' if partition == 'harness_unlinked' else 'column' if group_id else 'root',
                    column=group_id if partition == 'harness_board' else None,
                    card_id=group_id if partition == 'harness_children' else None,
                    cursor=cursor, limit=limit, preview=preview, check_budget=check_budget)
            elif partition == 'board':
                value = home_board.page(relations, scope=scope, server_id=server, principal=principal,
                    now=now, column=group_id, cursor=cursor, limit=limit, preview=preview,
                    check_budget=check_budget)
            else:
                value = pages.page(relations, scope=scope, server_id=server, principal=principal,
                    now=now, partition=partition, group_id=group_id, entry_id=entry_id,
                    cursor=cursor, limit=limit, preview=preview, check_budget=check_budget)
            check_budget()
            return value

"""One existing-Home-authorized UoW for entries, groups and exact children.

This implementation materializes O(N+relationships), bounded by source budgets
and a global processing deadline. It does not claim O(page) database work.
"""
from contextlib import ExitStack
import time

from ..domain.attention import normalize_filters
from ..domain.home_entries import EntryRelations
from ..domain import home_entry_pages as pages
from ..errors import OktoNexusError
from .home_ports import HomeEntryQueries


class HomeEntriesService:
    QUERY_SECONDS = 5.0

    def __init__(self, home_service, *, queries: HomeEntryQueries):
        self.home = home_service
        self.queries = queries

    def read(self, *, context, filters=None, partition='groups', group_id=None, entry_id=None,
             cursor=None, limit=10, preview=3):
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
            principal = context.actor_agent_id or 'local_operator'
            value = self.home._safe(now, lambda: self._read(uow, scope=scope, server=server,
                now=now, config=config, context=context, principal=principal,
                partition=partition, group_id=group_id, entry_id=entry_id, cursor=cursor,
                limit=limit, preview=preview, check_budget=check_budget))
            if 'version' not in value:
                value.update(version=1, scope=scope, server_id=server, generated_at=now,
                    snapshot_id=None, revision=None, partition=partition, group_id=group_id,
                    entry_id=entry_id, source_status={'entries': value['status']},
                    coverage={'result_tracking': 'unknown'},
                    summary={key: dict(value=None, total_is_exact=False,
                        unit='results' if key == 'unseen_results' else key)
                        for key in ('activities', 'external_instances', 'occurrences', 'sessions', 'results', 'unseen_results')},
                    server_attention=dict(status='unavailable', items=[], total=None,
                        total_is_exact=False, has_more=False))
                value['source_status'] = {key: 'unavailable' for key in
                    ('work', 'results', 'attention', 'connections', 'sessions', 'correlations', 'external')}
            value.update(event_cursor=int(bounds[0]), event_low_watermark=bounds[1])
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
            check_budget()
            value = pages.page(relations, scope=scope, server_id=server, principal=principal,
                now=now, partition=partition, group_id=group_id, entry_id=entry_id,
                cursor=cursor, limit=limit, preview=preview, check_budget=check_budget)
            check_budget()
            return value

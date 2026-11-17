"""One operator-authorized read snapshot, with independent source failures."""
from copy import deepcopy
from contextlib import ExitStack
from datetime import timedelta
import sqlite3

from ..domain import home
from ..domain.attention import canonical, digest, instant, normalize_filters
from ..errors import ErrorCode, OktoNexusError
from .home_ports import HomeOverviewQueries


class HomeOverviewService:
    def __init__(self, *, factory, access, queries: HomeOverviewQueries, attention, observations, clock, config):
        self.factory, self.access, self.queries = factory, access, queries
        self.attention, self.observations, self.clock, self.config = attention, observations, clock, config

    def _authorize(self, uow, context):
        if context is None or not self.access.authenticate(context, uow=uow, require_feature=False):
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED, 'Home requires an authenticated operator.', {})

    def _basis(self, uow, context, scope):
        self._authorize(uow, context)
        if scope.get('workspace_id') is not None and not uow.connection.execute(
                'SELECT 1 FROM workspaces WHERE workspace_id=?', (scope['workspace_id'],)).fetchone():
            raise OktoNexusError(ErrorCode.NOT_FOUND, 'Workspace is unavailable.', {})
        row = uow.connection.execute('SELECT server_id FROM execution_installation WHERE singleton=1').fetchone()
        # The installation identity exists independently of whether any runtime
        # is configured. Never derive it from a user-supplied target.
        if row is None:
            raise OktoNexusError(ErrorCode.CONFLICT, 'Server installation identity is unavailable.', {})
        return row[0], self.clock.now_iso(), deepcopy(self.config)

    @staticmethod
    def _unavailable(now, code, status='unavailable'):
        return dict(status=status, reason_code=code, as_of=now, next_refresh_at=None,
            items=[], total=None, total_is_exact=False, has_more=False, next_cursor=None)

    def _safe(self, now, read):
        try:
            return read()
        except sqlite3.Error:
            return self._unavailable(now, 'HOME_SOURCE_UNAVAILABLE')
        except OktoNexusError as exc:
            if exc.code in ('HOME_QUERY_BUDGET', 'ATTENTION_QUERY_BUDGET', 'OBSERVATION_QUERY_BUDGET', ErrorCode.DB_ERROR):
                return self._unavailable(now, str(exc.code))
            if exc.code == 'FEATURE_DISABLED':
                return self._unavailable(now, 'FEATURE_DISABLED', 'disabled')
            raise

    def _attention(self, uow, scope, server, now, limit, relation, value=None, *, serverwide=False, after=None):
        if value is None:
            value = self.queries.attention_page(uow, relation=relation, limit=limit, scope=scope,
                now=now, serverwide=serverwide, after=after)
        items = value['items'][:limit]
        more = len(value['items']) > limit
        deadline = (instant(now) + timedelta(seconds=15)).isoformat()
        deadline = min(deadline, value['next_change_at']) if value['next_change_at'] else deadline
        return dict(status='ready', as_of=now, next_refresh_at=deadline, items=items,
            total=value['total'], total_is_exact=True, has_more=more,
            next_cursor=home.encode_cursor('server_attention' if serverwide else 'attention',
                dict(scope, _server_id=server), value['snapshot_revision'],
                [canonical([items[-1]['priority'], items[-1]['first_detected_at']]), items[-1]['attention_id']]) if more else None,
            revision=value['snapshot_revision'])

    def _external(self, uow, scope, now, config, limit, after=None):
        if not config.feature_observations:
            return self._unavailable(now, 'FEATURE_DISABLED', 'disabled')
        return self.queries.external(uow, scope=scope, now=now, config=config, limit=limit,
            after=after, observations=self.observations)

    def read(self, *, context, filters=None, section=None, cursor=None, limit=20,
             limit_work=10, limit_attention=3, limit_results=6, limit_agents=6):
        scope = home.filters(filters)
        if section not in (None, 'work', 'results', 'activity', 'agents', 'external', 'attention', 'server_attention'):
            home.invalid()
        if section is None and cursor is not None:
            home.invalid()
        for bound in (limit, limit_work, limit_attention, limit_results, limit_agents):
            home.limit(bound)
        attention_section = section in ('attention', 'server_attention')
        after = None if attention_section else home.decode_cursor(cursor, section, scope)
        with self.factory.unit_of_work(write=False) as uow, ExitStack() as sources:
            server, now, config = self._basis(uow, context, scope)
            if attention_section:
                after = home.decode_cursor(cursor, section, dict(scope, _server_id=server))
            statistics = {}
            combined = None
            attention_relation, attention_error = None, None
            if config.feature_attention:
                # Preserve canonical Server-wide occurrences independently of
                # project/agent filters, then partition before totals/pages.
                # One authorized relation is shared by Work/Results/both lanes.
                attention_filters = normalize_filters(dict(state='all'))
                try:
                    attention_relation = sources.enter_context(self.attention.queries._relation(uow,
                        filters=attention_filters, now=now, config=config, access=self.access, context=context,
                        source_scope={'workspace_id':scope.get('workspace_id')},
                        server_only=section == 'server_attention'))
                except (sqlite3.Error, OktoNexusError) as exc:
                    if isinstance(exc, OktoNexusError) and exc.code == ErrorCode.PERMISSION_DENIED:
                        raise
                    attention_error = 'HOME_ATTENTION_UNAVAILABLE'
            if section is None and attention_relation is not None:
                try:
                    combined = self.queries.overview(uow, scope=scope, server_id=server, now=now,
                        limits=dict(work=limit_work, results=limit_results, attention=limit_attention, server_attention=3),
                        attention_relation=attention_relation)
                except sqlite3.Error:
                    # Retry only independent read projections, so one failed
                    # source cannot turn other sections into empty successes.
                    combined = None

            def read_block(name, size, page_after=None):
                def read():
                    if name in ('work', 'results', 'activity'):
                        if attention_error and scope.get('state') in ('awaiting_operator','awaiting_agent'):
                            return self._unavailable(now, attention_error)
                        if combined is not None and name in combined:
                            value, counts = combined[name]
                        else:
                            value, counts = self.queries.page(uow, section=name, scope=scope, server_id=server,
                                now=now, limit=size, after=page_after, attention_relation=attention_relation)
                        if attention_error and name != 'activity':
                            value.update(status='partial', reason_code=attention_error, total=None, total_is_exact=False)
                        statistics[name] = counts
                        return value
                    if name == 'agents':
                        return self.queries.agents(uow, scope=scope, now=now, limit=size,
                            clock=self.clock, config=config, after=page_after)
                    if name == 'external':
                        return self._external(uow, scope, now, config, size, page_after)
                    if not config.feature_attention:
                        return self._unavailable(now, 'FEATURE_DISABLED', 'disabled')
                    if attention_error:
                        return self._unavailable(now, attention_error)
                    return self._attention(uow, scope, server, now, size, attention_relation,
                        combined[name] if combined is not None and page_after is None else None,
                        serverwide=name == 'server_attention', after=page_after)
                return self._safe(now, read)

            if section:
                value = read_block(section, limit, after)
                return dict(value, version=1, server_id=server, scope=scope, generated_at=now,
                    snapshot_id=digest([server, scope, section, value.get('revision')]))
            blocks = {name: read_block(name, size) for name, size in (
                ('work', limit_work), ('results', limit_results), ('agents', limit_agents),
                ('attention', limit_attention), ('server_attention', 3), ('external', 6))}
            bounds = uow.connection.execute("SELECT COALESCE((SELECT seq FROM sqlite_sequence WHERE name='events'),0),(SELECT MIN(event_id) FROM events)").fetchone()

        def counter(value, label, unit, reason=None):
            result = dict(value=value, total_is_exact=value is not None, label=label, unit=unit)
            if reason:
                result['reason_code'] = reason
            return result
        ready = blocks['work']['status'] == 'ready'
        new_results = statistics.get('results', {}).get('new_results') if blocks['results']['status']=='ready' else None
        summary = dict(running=counter(statistics.get('work', {}).get('running') if ready else None, 'Running', 'activities'),
            waiting_start=counter(statistics.get('work', {}).get('waiting') if ready else None, 'Waiting to start', 'activities'),
            needs_you=counter(blocks['attention']['total'], 'Needs you', 'occurrences'),
            results=counter(new_results, 'New results' if new_results is not None else 'Recent results', 'results',
                'RESULT_VIEW_TRACKING_NOT_COMPLETE' if new_results is None else None),
            external=counter(blocks['external']['total'], 'External activity', 'external_instances'))
        return dict(version=1, server_id=server, scope=scope, generated_at=now,
            snapshot_id=digest([server, scope, {k: v.get('revision') for k, v in blocks.items()}]),
            event_cursor=int(bounds[0]), event_low_watermark=bounds[1], summary=summary,
            work=blocks['work'], attention=blocks['attention'], results=blocks['results'],
            agents=blocks['agents'], external_activity=blocks['external'], server_attention=blocks['server_attention'])

    def resolve(self, *, context, target, workspace_id=None):
        selected = home.target(target)
        scope = home.filters(dict(workspace_id=workspace_id))
        with self.factory.unit_of_work(write=False) as uow:
            server, now, config = self._basis(uow, context, scope)
            if selected['server_id'] != server or (workspace_id is not None and selected['workspace_id'] != workspace_id):
                raise OktoNexusError(ErrorCode.CONFLICT, 'Home target belongs to another scope.', {})
            value = self.queries.target(uow, selected)
            if value is None:
                raise OktoNexusError(ErrorCode.NOT_FOUND, 'Home target is no longer available.', {})
            if value['workspace_id'] != selected['workspace_id']:
                raise OktoNexusError(ErrorCode.CONFLICT, 'Home target scope changed.', {})
            result = dict(version=1, target=selected, available=True, source_revision=digest(value),
                agent_id=value.get('agent_id'), observed_at=now)
            if selected['kind'] in ('session', 'connection'):
                keys = ('server_id', 'executor_id', 'workspace_id', 'binding_id', 'workspace_binding_id', 'agent_id')
                context_value = {key: value[key] for key in keys}
                if selected['kind'] == 'session':
                    context_value.update(session_id=value['session_id'], lifecycle_state=value['lifecycle_state'])
                result[selected['kind'] + '_context'] = context_value
            return result

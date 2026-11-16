"""Disposable Server-lane contract probe; no global producer or NULL DB rows.

Uses the same pre-authorized domain-occurrence query-port harness as the SQLite
contract tests. HTTP/SQL/read projections and canonical preference writes stay
real. Only seen/snooze for these own contract IDs may mutate this fixture.
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import contextmanager
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace

from fastapi.responses import JSONResponse

from okto_nexus.bootstrap.dependencies import bootstrap
from okto_nexus.bootstrap import embedded_inventory
from okto_nexus.adapters.inbound.http.app import build_app
from okto_nexus.adapters.outbound.sqlite.attention import SqliteAttentionQueries

from .browser_fixture import seed, serve
from .test_home_server_attention import ContractItems, item


class BrowserContractItems(ContractItems):
    """Expose both canonical viewing/filtered CTEs to all real App consumers."""
    @contextmanager
    def _relation(self, uow, **kwargs):
        self.calls += 1
        assert kwargs['context'].trusted_local_operator
        filters = kwargs['filters']
        if kwargs.get('source_scope') is not None or kwargs.get('server_only'):
            assert 'workspace_id' not in filters and 'agent_id' not in filters
        with SqliteAttentionQueries._relation(self, uow, **kwargs) as (sql, params):
            clauses = []
            params = dict(params, contract_items=json.dumps(self.items))
            for name in ('workspace_id', 'agent_id', 'category', 'kind', 'priority'):
                if name in filters:
                    params['contract_filter_'+name] = filters[name]
                    clauses.append("json_extract(item,'$."+name+"')=:contract_filter_"+name)
            if filters['state'] == 'active':
                clauses.append("json_extract(item,'$.active')=1")
            elif filters['state'] != 'all':
                params['contract_filter_state'] = filters['state']
                clauses.append("json_extract(item,'$.resolution')=:contract_filter_state")
            if filters['seen'] in ('seen', 'unseen'):
                clauses.append("json_extract(item,'$.seen_state.seen')="+('1' if filters['seen'] == 'seen' else '0'))
            elif filters['seen'] == 'snoozed':
                clauses.append("json_extract(item,'$.seen_state.snoozed')=1")
            yield ('WITH canonical_existing AS MATERIALIZED ('+sql+' SELECT item FROM viewing), '
                   'viewing AS MATERIALIZED (SELECT item FROM canonical_existing UNION ALL '
                   'SELECT nexus_attention_preferences_v1(j.value,p.seen_at,p.snoozed_until,p.revision,:now) '
                   'FROM json_each(:contract_items) j LEFT JOIN attention_preferences p '
                   "ON p.principal='operator' AND p.attention_id=json_extract(j.value,'$.attention_id')), "
                   'filtered AS MATERIALIZED (SELECT item FROM viewing WHERE '+(' AND '.join(clauses) or '1')+') ', params)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=0)
    parser.add_argument('--stop-file', type=Path, required=True)
    parser.add_argument('--ready-file', type=Path, required=True)
    args = parser.parse_args()
    home = Path(tempfile.mkdtemp(prefix='nexus-home-server-contract-browser-'))
    embedded_inventory.discover_local_candidates = lambda **_: SimpleNamespace(candidates=())
    deps = bootstrap({}, ['--home', str(home), '--feature-harness-integrations', 'false', '--embedding-mode', 'off'])
    try:
        seed(deps)
        with deps.connection_factory.unit_of_work() as uow:
            deps.repos.workspaces.upsert(uow, workspace_id='home-quiet')
            uow.connection.execute("UPDATE workspaces SET display_name='Quiet workspace' WHERE workspace_id='home-quiet'")
        now = deps.clock.now_iso()
        values = [item(now, f'browser-server-{n}', category='watch' if n % 2 else 'action_required') for n in range(6)]
        values += [item(now, f'browser-project-{workspace}-{n}', workspace, category='action_required')
                   for workspace in ('home-alpha', 'home-beta') for n in range(4)]
        app = build_app(deps)
        app.state.attention.queries = BrowserContractItems(values)
        fixed_clock = SimpleNamespace(now_iso=lambda: now)
        app.state.home.clock = app.state.attention.clock = fixed_clock
        assert app.state.home.attention is app.state.attention
        allowed_mutations = {f'/api/v1/attention/{row["attention_id"]}/{action}'
                             for row in values for action in ('seen', 'snooze')}

        @app.middleware('http')
        async def own_mutations_only(request, call_next):
            if request.method not in {'GET', 'HEAD', 'OPTIONS'} and not (
                    request.method == 'POST' and request.url.path in allowed_mutations):
                return JSONResponse({'fixture': 'Only own canonical viewing preferences may mutate.'}, status_code=405)
            return await call_next(request)

        asyncio.run(serve(app, port=args.port, stop_file=args.stop_file,
                          ready_file=args.ready_file, fixture_home=home))
    finally:
        deps.connection_factory.close()


if __name__ == '__main__':
    main()

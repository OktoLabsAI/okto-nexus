"""Read-only profiler and query-plan diagnostics for the existing synthetic DB.

Keeps function names/timings and EXPLAIN plan descriptions only. No SQL text,
bound values, credentials, event contents or database hashes are retained.
"""
from __future__ import annotations
import cProfile
import json
from pathlib import Path
import pstats
import time

from benchmark import ROOT, QUOTAS, WORKSPACE, utc, write_result, error_metadata


def name(filename):
    filename = filename.replace('\\', '/')
    if '/okto_nexus/' in filename:
        return 'okto_nexus/' + filename.split('/okto_nexus/', 1)[1]
    return filename.rsplit('/', 1)[-1]


def main():
    from okto_nexus.bootstrap.dependencies import bootstrap
    from okto_nexus.bootstrap.execution_authority import build_execution_access
    from okto_nexus.application.attention import AttentionService
    from okto_nexus.adapters.outbound.sqlite.attention import SqliteAttentionQueries
    from okto_nexus.domain.runtime_context import RuntimeRequestContext
    from okto_nexus.domain.attention import normalize_filters, stamp

    output = ROOT / 'attention-profile.json'
    if output.exists():
        raise SystemExit('Profiler output exists; preserve it.')
    argv = ['--home', str(ROOT / 'home'), '--embedding-mode', 'off', '--feature-harness-integrations', 'false',
            '--feature-observations', 'true', '--feature-attention', 'true', '--metrics-mode', 'disabled']
    for key, value in QUOTAS.items():
        argv.extend(['--' + key.replace('_', '-'), str(value)])
    deps = bootstrap({}, argv)
    operator = RuntimeRequestContext(None, 'http_loopback', trusted_local_operator=True)
    access = build_execution_access(deps)
    queries = SqliteAttentionQueries(decision_registry=deps.approvals.attention_decision_actions)
    attention = AttentionService(factory=deps.connection_factory, access=access, queries=queries,
        clock=deps.clock, config=deps.config)
    report = {'started_at': utc(), 'scope': 'Read-only source profiler of synthetic 4096-instance DB',
        'notes': ['cProfile adds overhead and can alter where the fixed 5-second query budget interrupts.',
                  'SQLite driver self time approximates native SQL work excluding profiled Python callbacks; it is not a complete engine profiler.',
                  'Cumulative function times overlap and must not be added.',
                  'No query text, bound values, credential hashes, payloads or database files are retained.'],
        'cases': []}
    try:
        for kind in ('external_blocked', 'external_completion_unseen', None):
            filters = {'workspace_id': WORKSPACE, **({'kind': kind} if kind else {})}
            profile = cProfile.Profile()
            started = time.perf_counter()
            profile.enable()
            try:
                result = attention.read(context=operator, filters=filters, limit=50)
                outcome = {'ok': True, 'total': result['total'], 'returned_items': len(result['items'])}
            except Exception as error:
                outcome = {'ok': False, 'error': error_metadata(error)}
            finally:
                profile.disable()
            elapsed_ms = (time.perf_counter() - started) * 1000
            stats = pstats.Stats(profile)
            functions = [dict(file=name(key[0]), line=key[1], function=key[2], primitive_calls=value[0],
                             total_calls=value[1], self_ms=value[2] * 1000, cumulative_ms=value[3] * 1000)
                         for key, value in stats.stats.items()]
            sql_self = sum(row['self_ms'] for row in functions if 'sqlite3.Connection' in row['function'] or 'sqlite3.Cursor' in row['function'])
            case = {'kind': kind or 'all', 'elapsed_ms': elapsed_ms, 'outcome': outcome,
                'total_profiled_ms': stats.total_tt * 1000, 'sqlite_driver_self_ms_approx': sql_self,
                'top_cumulative': sorted(functions, key=lambda row: row['cumulative_ms'], reverse=True)[:45],
                'top_self': sorted(functions, key=lambda row: row['self_ms'], reverse=True)[:30]}
            with deps.connection_factory.unit_of_work(write=False) as uow:
                attention._authorize(uow, operator)
                with queries._relation(uow, filters=normalize_filters(filters), now=stamp(deps.clock.now_iso()),
                        config=deps.config, access=access, context=operator) as (sql, params):
                    plans = uow.connection.execute('EXPLAIN QUERY PLAN ' + sql + 'SELECT count(*) FROM filtered', params).fetchall()
                    case['aggregate_query_plan'] = [{'id': row[0], 'parent': row[1], 'detail': row[3]} for row in plans]
            report['cases'].append(case)
            write_result(output, report)
            print(json.dumps({'kind': case['kind'], 'elapsed_ms': round(elapsed_ms, 2),
                              'sqlite_driver_self_ms_approx': round(sql_self, 2), 'outcome': outcome}), flush=True)
    finally:
        deps.connection_factory.close()
        report.update(finished_at=utc(), factory_closed=True)
        write_result(output, report)


if __name__ == '__main__':
    main()

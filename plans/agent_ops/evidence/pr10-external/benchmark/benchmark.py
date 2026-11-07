"""OBS11 source benchmark: real SQLite/services, synthetic identities, no provider.

Run only after the root agent explicitly authorizes the frozen source campaign.
No bearer, credential hash, SQL text, source payload or personal environment is
written to output. The database necessarily stores its own synthetic capability
hashes; that private database is not a retained/shareable benchmark artifact.
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import statistics
import threading
import time
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parent
WORKSPACE = 'pr10-benchmark-workspace'
QUOTAS = {
    'observation_source_rate_per_minute': 6000,
    'observation_source_burst': 1024,
    'observation_agent_rate_per_minute': 60000,
    'observation_agent_burst': 4096,
    'observation_installation_rate_per_minute': 600000,
    'observation_installation_burst': 16384,
    'observation_max_sources_per_agent': 1024,
    'observation_max_sources': 4096,
    'observation_max_instances': 4096,
    'observation_max_tokens_per_source': 64,
    'observation_max_events': 20000,
}


def utc():
    return datetime.now(timezone.utc).isoformat(timespec='microseconds')


def write_result(path, result):
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def error_metadata(error):
    return {'type': type(error).__name__, 'code': getattr(error, 'code', None)}


class Trace:
    """Count executed SQL classes, never retain expanded SQL or its parameters."""
    def __init__(self, factory):
        self.active = None
        self.lock = threading.Lock()
        original = factory.unit_of_work

        @contextmanager
        def instrumented(*args, **kwargs):
            with original(*args, **kwargs) as uow:
                with self.lock:
                    stats = self.active
                if stats is not None:
                    def count(statement):
                        first = statement.lstrip().split(None, 1)[0].upper() if statement.strip() else 'EMPTY'
                        with self.lock:
                            stats[first] += 1
                    uow.connection.set_trace_callback(count)
                try:
                    yield uow
                finally:
                    if stats is not None:
                        uow.connection.set_trace_callback(None)
        factory.unit_of_work = instrumented

    def begin(self):
        with self.lock:
            if self.active is not None:
                raise RuntimeError('Overlapping benchmark measurement')
            self.active = Counter()

    def end(self):
        with self.lock:
            stats, self.active = self.active, None
        return {'select_or_cte': stats['SELECT'] + stats['WITH'],
                'statement_classes': dict(sorted(stats.items())), 'trace_events': sum(stats.values())}


def measure(trace, call):
    trace.begin()
    start, cpu = time.perf_counter(), time.process_time()
    try:
        result = call()
        timing = {'elapsed_ms': (time.perf_counter() - start) * 1000,
                  'cpu_ms': (time.process_time() - cpu) * 1000, 'ok': True}
        return result, dict(timing, queries=trace.end())
    except Exception as error:
        timing = {'elapsed_ms': (time.perf_counter() - start) * 1000,
                  'cpu_ms': (time.process_time() - cpu) * 1000, 'ok': False, 'error': error_metadata(error)}
        return None, dict(timing, queries=trace.end())


def storage(deps):
    database = Path(deps.config.db_path)
    sizes = {name: (path.stat().st_size if path.exists() else 0) for name, path in (
        ('database_bytes', database), ('wal_bytes', Path(str(database) + '-wal')),
        ('shm_bytes', Path(str(database) + '-shm')))}
    with deps.connection_factory.unit_of_work(write=False) as uow:
        conn = uow.connection
        sizes.update(page_count=conn.execute('PRAGMA page_count').fetchone()[0],
                     page_size=conn.execute('PRAGMA page_size').fetchone()[0],
                     freelist_count=conn.execute('PRAGMA freelist_count').fetchone()[0])
        sizes['rows'] = {table: conn.execute('SELECT count(*) FROM ' + table).fetchone()[0] for table in (
            'observation_sources', 'observation_instances', 'observation_tokens', 'observation_heads',
            'observation_attention_anchors', 'observation_rate_buckets', 'events', 'attention_preferences')}
        sizes['observation_events'] = {row[0]: row[1] for row in conn.execute(
            "SELECT type,count(*) FROM events WHERE type GLOB 'observation.*' GROUP BY type")}
    return sizes


def profile_reads(deps, service, attention, trace, operator, *, repetitions):
    listing = service.read(context=operator, workspace_id=WORKSPACE, limit=1)
    first = listing['items'][0]['observed_instance_id'] if listing['items'] else None
    operations = {
        'observation_list_200': lambda: service.read(context=operator, workspace_id=WORKSPACE, limit=200),
        'observation_detail': lambda: service.get_instance(context=operator, observed_instance_id=first),
        'observation_summary': lambda: service.summary(context=operator, workspace_id=WORKSPACE),
        'attention_all_kinds_50': lambda: attention.read(context=operator, filters={'workspace_id': WORKSPACE}, limit=50),
        'attention_external_blocked_50': lambda: attention.read(context=operator,
            filters={'workspace_id': WORKSPACE, 'kind': 'external_blocked'}, limit=50),
        'attention_external_completion_50': lambda: attention.read(context=operator,
            filters={'workspace_id': WORKSPACE, 'kind': 'external_completion_unseen'}, limit=50),
    }
    result = {}
    for name, call in operations.items():
        samples = []
        for _ in range(repetitions):
            value, timing = measure(trace, call)
            if value is not None:
                timing['returned_items'] = len(value.get('items', [value['item']] if 'item' in value else []))
                timing['total_matching'] = value.get('total_instances', value.get('total'))
                timing['has_more'] = bool(value.get('next_after') or value.get('next_cursor'))
                timing['response_json_bytes'] = len(json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode())
            samples.append(timing)
        values = [sample['elapsed_ms'] for sample in samples if sample['ok']]
        result[name] = {'samples': samples, 'successful_samples': len(values),
            'median_ms': statistics.median(values) if values else None,
            'minimum_ms': min(values) if values else None, 'maximum_ms': max(values) if values else None}
    return result


def seed_to(deps, target, sources, instances, batches, operator, service):
    """Valid repository fixture registration, one write UoW per cardinality step."""
    from okto_nexus.application.auth import AgentKeyAuthService
    auth = AgentKeyAuthService(deps.repos.agents, deps.clock)
    existing = len(instances)
    additions = {}
    start = time.perf_counter()
    with deps.connection_factory.unit_of_work() as uow:
        if not instances:
            deps.repos.workspaces.upsert(uow, workspace_id=WORKSPACE, display_name='Synthetic OBS11 benchmark')
            for number in range(8):
                agent_id = f'pr10-benchmark-agent-{number}'
                deps.repos.agents.upsert(uow, agent_id=agent_id)
                auth.issue_key(uow, agent_id=agent_id)  # Discard private bearer immediately.
                deps.repos.agents.set_permissions(uow, agent_id=agent_id, preset_id=None,
                    permissions={'observations': {'publish': True, 'manage_self': True}})
        for number in range(existing, target):
            group = number // 100
            if group not in sources:
                sources[group] = deps.repos.observations.create_source(uow,
                    agent_id=f'pr10-benchmark-agent-{group % 8}', source_kind='custom',
                    workspace_ids=[WORKSPACE], registration_ref=f'benchmark-source-{group}',
                    now=deps.clock.now_iso(), source_limit=1024, installation_limit=4096)
            source = sources[group]
            value = deps.repos.observations.create_instance(uow, source_id=source['source_id'],
                expected_revision=source['revision'], workspace_id=WORKSPACE,
                external_instance_ref=f'synthetic-instance-{number}', now=deps.clock.now_iso(), instance_limit=4096)
            record = dict(value, fixture_number=number, sequence=0)
            instances.append(record)
            additions.setdefault(group, []).append(record)
    seed_ms = (time.perf_counter() - start) * 1000
    fresh_batches = []
    for group, values in additions.items():
        source = sources[group]
        granted = service.issue_token(context=operator, source_id=source['source_id'], body={
            'expected_revision': source['revision'], 'instance_grants': [
                {'observed_instance_id': item['observed_instance_id'], 'generation': item['generation']} for item in values]})
        packet = {'source': source, 'instances': values, 'token': granted['token']}
        batches.append(packet)
        fresh_batches.append(packet)
    return fresh_batches, seed_ms


def publish_batch(service, clock, packet, *, change=False):
    reports = []
    observed_at = clock.now_iso()
    for instance in packet['instances']:
        number = instance['fixture_number']
        initial = ('blocked', 'working', 'idle', 'unknown')[number % 4]
        state = ('working' if initial == 'blocked' else 'blocked') if change else initial
        report = dict(schema_version=1, source_id=packet['source']['source_id'],
            observed_instance_id=instance['observed_instance_id'], generation=instance['generation'],
            sequence=instance['sequence'] + 1, state=state, evidence='inferred', observed_at=observed_at,
            valid_for_seconds=3600, reason_code='external_input_required' if state == 'blocked' else None)
        if initial == 'idle' and not change:
            report['current_completion_ref'] = f'synthetic-completion-{number}'
        reports.append(report)
    result = service.publish(token=packet['token'], payload={'reports': reports})
    if len(result['receipts']) != len(reports) or any(row['replayed'] for row in result['receipts']):
        raise AssertionError('Fresh benchmark reports were not admitted exactly once')
    for item in packet['instances']:
        item['sequence'] += 1
    return result


async def sse_metadata(deps, attention, service, packet, trace):
    """Actual streaming generator/SQLite, explicitly NOT a TCP/ASGI benchmark."""
    from okto_nexus.adapters.inbound.http.attention_stream import attention_stream
    from okto_nexus.adapters.inbound.http.identity_ctx import trusted_local_operator
    from okto_nexus.adapters.outbound.sqlite.observability_repo import SqliteObservabilityQueries
    from okto_nexus.application.observability import ObservabilityService
    state = SimpleNamespace(deps=deps, attention=attention,
        observability=ObservabilityService(SqliteObservabilityQueries(), deps.clock, deps.config),
        sse_poll_seconds=0.01, sse_ping_seconds=1.0, server=SimpleNamespace(should_exit=False))
    request = SimpleNamespace(app=SimpleNamespace(state=state), state=SimpleNamespace(operator_session=False))
    guard = trusted_local_operator.set(True)
    iterator = None
    try:
        response = await attention_stream(request, cursor=0, workspace=WORKSPACE)
        iterator = response.body_iterator
        reset = await asyncio.wait_for(anext(iterator), timeout=10)
        publish_batch(service, deps.clock, packet, change=True)
        trace.begin()
        started = time.perf_counter()
        try:
            invalidation = await asyncio.wait_for(anext(iterator), timeout=10)
        finally:
            queries = trace.end()
        elapsed = (time.perf_counter() - started) * 1000
        frames = []
        for raw in (reset, invalidation):
            if isinstance(raw, bytes):
                raw = raw.decode('utf-8')
            data = json.loads(next(line[6:] for line in raw.splitlines() if line.startswith('data: ')))
            if set(data) != {'version', 'event_cursor', 'reason', 'clear'}:
                raise AssertionError('SSE frame exposed more than control metadata')
            frames.append({'bytes': len(raw.encode()), 'event': next(line[7:] for line in raw.splitlines() if line.startswith('event: ')),
                           'data_keys': sorted(data), 'reason': data['reason']})
        return {'status': 'MEASURED_IN_PROCESS_GENERATOR', 'not_tcp_or_browser': True,
                'poll_seconds': state.sse_poll_seconds, 'invalidation_ms': elapsed, 'queries': queries, 'frames': frames}
    except Exception as error:
        return {'status': 'ERROR', 'error': error_metadata(error), 'not_tcp_or_browser': True}
    finally:
        if iterator is not None:
            await iterator.aclose()
        trusted_local_operator.reset(guard)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--go', action='store_true', help='Only after explicit root campaign authorization')
    parser.add_argument('--phase', choices=('grow', 'read-only'), default='grow')
    parser.add_argument('--output', default='benchmark-grow.json')
    parser.add_argument('--repetitions', type=int, default=4)
    args = parser.parse_args()
    if not args.go:
        parser.error('Campaign is prepared; explicit --go is required after root authorization.')
    if not 1 <= args.repetitions <= 10:
        parser.error('Repetitions must be between 1 and 10.')
    output = (ROOT / args.output).resolve()
    if output.parent != ROOT or output.exists():
        parser.error('Choose a new result filename inside this benchmark directory.')
    home = ROOT / 'home'
    if args.phase == 'grow' and home.exists():
        parser.error('Grow campaign requires its fresh, absent home.')
    if args.phase == 'read-only' and not home.exists():
        parser.error('Read-only pass requires the completed grow home.')

    from okto_nexus.bootstrap.dependencies import bootstrap
    from okto_nexus.bootstrap.execution_authority import build_execution_access
    from okto_nexus.application.attention import AttentionService
    from okto_nexus.application.observations import ObservationService
    from okto_nexus.adapters.outbound.sqlite.attention import SqliteAttentionQueries
    from okto_nexus.domain.runtime_context import RuntimeRequestContext

    argv = ['--home', str(home), '--embedding-mode', 'off', '--feature-harness-integrations', 'false',
            '--feature-observations', 'true', '--feature-attention', 'true', '--metrics-mode', 'disabled']
    for key, value in QUOTAS.items():
        argv.extend(['--' + key.replace('_', '-'), str(value)])
    deps = bootstrap({}, argv)
    operator = RuntimeRequestContext(None, 'http_loopback', trusted_local_operator=True)
    service = ObservationService(deps=deps, access=build_execution_access(deps))
    attention = AttentionService(factory=deps.connection_factory, access=service.access,
        queries=SqliteAttentionQueries(decision_registry=deps.approvals.attention_decision_actions),
        clock=deps.clock, config=deps.config)
    trace = Trace(deps.connection_factory)
    result = {'schema_version': 1, 'phase': args.phase, 'started_at': utc(),
        'platform': platform.platform(), 'python': platform.python_version(),
        'scope': 'Synthetic source checkout benchmark, real SQLite/WAL and application services; no HTTP server, lifespan, harness discovery or provider.',
        'quotas': QUOTAS, 'repetitions': args.repetitions,
        'measurement_notes': [
            'Warm pooled connection; per-operation first sample and later samples are retained separately.',
            'Latency includes SQL trace counting overhead; no SQL text or parameters are retained.',
            'SELECT/CTE count excludes transaction open/close and does not count SQLite internal plan steps.',
            'Seeded registration uses repository contracts in one UoW per cardinality; publication uses real authenticated ObservationService.publish.',
            'SSE measurement uses the actual generator and SQLite in-process, not HTTP transport or browser.',
            'The private database contains synthetic credential hashes and must not be collected as evidence.',
        ], 'stages': []}
    try:
        result['storage_initial'] = storage(deps)
        if args.phase == 'read-only':
            result['stages'].append({'instances': result['storage_initial']['rows']['observation_instances'],
                'reads': profile_reads(deps, service, attention, trace, operator, repetitions=args.repetitions)})
        else:
            sources, instances, batches = {}, [], []
            for target in (1, 200, 4096):
                stage = {'instances': target, 'started_at': utc(), 'storage_before': storage(deps)}
                fresh, stage['registration_seed_ms'] = seed_to(deps, target, sources, instances, batches, operator, service)
                publications = []
                for packet in fresh:
                    _, metric = measure(trace, lambda packet=packet: publish_batch(service, deps.clock, packet))
                    metric['reports'] = len(packet['instances'])
                    publications.append(metric)
                    if not metric['ok']:
                        raise AssertionError('Benchmark seed publication failed')
                stage['initial_ingestion'] = publications
                admitted = sum(row['reports'] for row in publications)
                duration = sum(row['elapsed_ms'] for row in publications) / 1000
                stage['initial_ingestion_reports_per_second'] = admitted / duration if duration else None
                stage['storage_after_ingestion'] = storage(deps)
                stage['reads'] = profile_reads(deps, service, attention, trace, operator, repetitions=args.repetitions)
                packet = max(batches, key=lambda row: len(row['instances']))
                _, metric = measure(trace, lambda: publish_batch(service, deps.clock, packet, change=True))
                stage['fresh_update_batch'] = dict(metric, reports=len(packet['instances']))
                stage['storage_after_measurement'] = storage(deps)
                stage['finished_at'] = utc()
                result['stages'].append(stage)
                write_result(output, result)
                print(json.dumps({'stage_instances': target, 'read_failures': sum(
                    len(row['samples']) - row['successful_samples'] for row in stage['reads'].values())}), flush=True)
            # Select a different state than the most recently measured update.
            packet = dict(batches[-1], instances=batches[-1]['instances'][:1])
            result['sse'] = asyncio.run(sse_metadata(deps, attention, service, packet, trace))
        result['storage_final_open'] = storage(deps)
        result['status'] = 'COMPLETED_WITH_RECORDED_MEASUREMENTS'
    except Exception as error:
        result['status'] = 'ERROR'
        result['error'] = error_metadata(error)
    finally:
        deps.connection_factory.close()
        result['finished_at'] = utc()
        result['factory_closed'] = True
        database = Path(deps.config.db_path)
        result['storage_closed_file_bytes'] = {name: path.stat().st_size if path.exists() else 0
            for name, path in [('database', database), ('wal', Path(str(database) + '-wal')),
                               ('shm', Path(str(database) + '-shm'))]}
        write_result(output, result)
    print(json.dumps({'status': result['status'], 'result_file': output.name, 'factory_closed': True}), flush=True)
    return 1 if result['status'] == 'ERROR' else 0


if __name__ == '__main__':
    raise SystemExit(main())

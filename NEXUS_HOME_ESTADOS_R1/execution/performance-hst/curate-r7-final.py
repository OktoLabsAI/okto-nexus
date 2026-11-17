"""Seal R7 measurements dynamically; no application imports or timing reruns."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / 'persistent-r7-final'
READY = HERE.parent / 'package-hst-r7/READY.json'


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def main():
    result = json.loads((OUT / 'result.json').read_text(encoding='utf-8'))
    plan = json.loads((OUT / 'plan.json').read_text(encoding='utf-8'))
    ready = json.loads(READY.read_text(encoding='utf-8'))
    assert result['status'] == 'MEASURED' and len(result['completed']) == 10 and not result['not_run']
    cases, launches = [], []
    for item, job in zip(result['completed'], plan['jobs'], strict=True):
        assert item['case'] == job['name'] and item['exit_code'] == 0
        report_path = OUT / (item['case'] + '-report.json')
        report = json.loads(report_path.read_text(encoding='utf-8'))
        launch_path = HERE / item['launch']
        launch = json.loads(launch_path.read_text(encoding='utf-8'))
        assert launch['physical_exit'] and launch['exit_code'] == 0 and not launch.get('timeout')
        assert not launch['source_dataset_drift'] and not launch['source_seed_drift']
        assert report['productive_drift'] == [] and report['payload_drift'] is False and report['status'] == 'MEASURED'
        for series in report['series'].values():
            assert series['count'] == 20 and len(series['samples']) == 20
            assert all(s['http_status'] == 200 and s['status'] == 'ready' for s in series['samples'])
        assert report['targets']['read_p95_ms'] == 500
        assert report['targets']['http_first_response_proxy_ms'] == 2000
        if 'candidate' in job['variant']:
            assert report['wheel_sha256'] == ready['wheel_sha256']
            assert report['source_candidate'] == ready['source_commit']
            assert report['payload_files'] == ready['payload_files']
        cases.append({'case': item['case'], 'variant': job['variant'], 'connections': report['connections'],
            'volume': report['volume'], 'wheel_sha256': report['wheel_sha256'],
            'source_candidate': report['source_candidate'], 'payload_files': report['payload_files'],
            'package_modules': report['package_modules'],
            'series': {key: {k: v for k, v in value.items() if k != 'samples'} for key, value in report['series'].items()},
            'targets': report['targets'], 'first_http_response': report['first_http_response'],
            'instrumentation': report['instrumentation'], 'schema_after': report['schema_after'],
            'pid': launch['pid'], 'physical_exit': True, 'launch': '../' + item['launch'], 'report': report_path.name})
        launches.append(launch_path)
    candidate = [c for c in cases if c['variant'].startswith('candidate-')]
    baseline = [c for c in cases if c['variant'] == 'baseline-v1']
    assert len(candidate) == 8 and len(baseline) == 2
    def counts(group):
        return {'measured': len(group),
            'read_target_pass': sum(c['targets']['read_target_met'] for c in group),
            'read_target_fail': sum(not c['targets']['read_target_met'] for c in group),
            'first_http_proxy_pass': sum(c['targets']['first_http_proxy_met'] for c in group),
            'first_http_proxy_fail': sum(not c['targets']['first_http_proxy_met'] for c in group),
            'not_run': 0}
    candidate_counts, baseline_counts = counts(candidate), counts(baseline)
    status = 'PASS' if not candidate_counts['read_target_fail'] and not candidate_counts['first_http_proxy_fail'] else 'FAIL'
    failed = [c['case'] for c in cases if not c['targets']['read_target_met']]
    paired = []
    for workload in ('mixed', 'open'):
        base = next(c for c in baseline if c['case'] == f'{workload}-100-baseline-v1')
        for version in (1, 2):
            current = next(c for c in candidate if c['case'] == f'{workload}-100-candidate-v{version}')
            paired.append({'workload': workload, 'variant': f'candidate-v{version}',
                'p95_delta_percent': {key: 100 * (current['series'][key]['nearest_rank_p95_ms'] /
                    base['series'][key]['nearest_rank_p95_ms'] - 1) for key in base['series']}})
    qualification = {'version': 1, 'status': status,
        'status_scope': 'Candidate eight-cut HTTP read/proxy targets only; DOM remains NOT_RUN.',
        'cut': 'Final R7 persistent ASGI; all original/R2/R6 antecedents remain immutable.',
        'counts': counts(cases), 'candidate_counts': candidate_counts, 'baseline_counts': baseline_counts,
        'candidate_source': ready['source_commit'], 'candidate_wheel_sha256': ready['wheel_sha256'],
        'samples_per_series': 20, 'warmup_per_series': 3,
        'targets': {'read_p95_ms': 500, 'first_http_proxy_ms': 2000, 'first_useful_dom': 'NOT_RUN'},
        'cases': cases, 'paired_large_comparisons': paired, 'read_target_failed_cases': failed,
        'cleanup': {'all10workers_physically_exited': True, 'orchestrator_exit_code': 0,
            'timeout': False, 'retry': False, 'app_readers_active_after_window': False},
        'seed_dataset_schema_payload_productive_drift': False,
        'limits': ['Persistent httpx ASGI, one loop per worker; no TCP/browser/lifespan/background runtime.',
            'First HTTP proxy is not first-useful DOM. No DOM execution or DOM gate approval in this cut.',
            'Own SQL synthetic facts do not qualify providers/native authority/liveness/grants or application of decisions.',
            'No threshold waiver, retry, source/schema modification, or statistical confidence claim.',
            'Query counts do not qualify internal SQL row-scan complexity.',
            'Mixed100 contains925terminal/75open; OPEN100 contains1000open/100000history. Separate workloads.',
            'Baseline failures are reported separately and do not determine candidate status.']}
    save(OUT / 'qualification.json', qualification)
    lines = ['# Final R7 persistent-ASGI measurements', '',
        f"Candidate HTTP/read targets: **{status}**. Candidate counts: {candidate_counts}. Baseline counts: {baseline_counts}.", '',
        '| Case | Overview p50/p95 ms | Activity p50/p95 ms | Queries overview/activity | Bytes overview/activity |',
        '|---|---:|---:|---:|---:|']
    for case in cases:
        overview, activity = case['series']['overview_refresh'], case['series']['activity_page']
        oi, ai = case['instrumentation']['overview_refresh'], case['instrumentation']['activity_page']
        lines.append(f"| {case['case']} | {overview['p50_ms']:.3f} / {overview['nearest_rank_p95_ms']:.3f} | "
            f"{activity['p50_ms']:.3f} / {activity['nearest_rank_p95_ms']:.3f} | {oi['statement_count']} / "
            f"{ai['statement_count']} | {overview['max_payload_bytes']} / {activity['max_payload_bytes']} |")
    lines += ['', 'Paired differences against baseline in this same window (positive is slower):', '']
    for pair in paired:
        lines.append(f"- {pair['workload']} {pair['variant']}: overview {pair['p95_delta_percent']['overview_refresh']:+.2f}%; "
            f"activity {pair['p95_delta_percent']['activity_page']:+.2f}%.")
    lines += ['', *qualification['limits'], '', 'Raw reports retain20samples per series and exact origins/bytes/guards. '
        'All10workers and orchestrator exited0 physically. No app reader remains; only stdlib curation followed.', '']
    (OUT / 'report.md').write_text('\n'.join(lines), encoding='utf-8')
    paths = list(OUT.iterdir()) + launches + [Path(__file__), READY,
        HERE / 'persistent-final-matrix.py', HERE / 'persistent-launch.py', HERE / 'persistent-worker.py']
    save(OUT / 'manifest.json', {'files': [{'path': str(p.relative_to(HERE)) if p.is_relative_to(HERE) else str(p),
        'sha256': hashlib.sha256(p.read_bytes()).hexdigest(), 'bytes': p.stat().st_size}
        for p in sorted(paths) if p.is_file() and p.name != 'manifest.json']})
    print(json.dumps({'status': status, 'candidate_counts': candidate_counts, 'baseline_counts': baseline_counts,
        'qualification_sha256': hashlib.sha256((OUT / 'qualification.json').read_bytes()).hexdigest()}))


if __name__ == '__main__':
    main()

"""Curate completed14-cut experiment; no application import or measurements."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / 'persistent-r2-final'


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def main():
    result = json.loads((OUT / 'result.json').read_text(encoding='utf-8'))
    plan = json.loads((OUT / 'plan.json').read_text(encoding='utf-8'))
    assert result['status'] == 'MEASURED' and len(result['completed']) == 14 and not result['not_run']
    cases = []
    for item, job in zip(result['completed'], plan['jobs'], strict=True):
        assert item['case'] == job['name'] and item['exit_code'] == 0
        report = json.loads((OUT / (item['case'] + '-report.json')).read_text(encoding='utf-8'))
        launch = json.loads((HERE / item['launch']).read_text(encoding='utf-8'))
        assert launch['physical_exit'] and launch['exit_code'] == 0
        assert not launch['source_dataset_drift'] and not launch['source_seed_drift']
        assert not report['productive_drift'] and report['payload_drift'] is False
        assert report['status'] == 'MEASURED'
        for series in report['series'].values():
            assert series['count'] == 20 and all(s['http_status'] == 200 and s['status'] == 'ready' for s in series['samples'])
        cases.append({
            'case': item['case'], 'wheel_sha256': report['wheel_sha256'], 'source_candidate': report['source_candidate'],
            'payload_files': report['payload_files'], 'package_modules': report['package_modules'],
            'p95_ms': item['p95_ms'], 'targets': item['targets'], 'queries': report['instrumentation'],
            'max_payload_bytes': {k: v['max_payload_bytes'] for k, v in report['series'].items()},
            'pid': launch['pid'], 'physical_exit': True, 'schema_after': report['schema_after'],
            'launch': '../' + item['launch'], 'report': item['case'] + '-report.json',
        })
    failed = [c['case'] for c in cases if not c['targets']['read_target_met']]
    assert len(failed) == 8
    qualification = {
        'version': 1, 'status': 'FAIL', 'measurements_completed': 14,
        'target': {'read_p95_ms': 500, 'http_first_response_proxy_ms': 2000, 'first_useful_dom': 'NOT_RUN'},
        'samples': 20, 'warmup': 3, 'read_target_failed_cases': failed,
        'cases': cases, 'all_owned_workers_physically_exited': True,
        'source_seed_dataset_schema_payload_productive_drift': False,
        'limitations': [
            'Persistent httpx ASGI transport, one loop per worker, no lifespan/background service/TCP/browser.',
            'Synthetic SQL read facts do not prove runtime readiness, real authority or native causal resumption.',
            'Original 12 fresh-TestClient measurements remain immutable FAIL antecedents; no corrected/replaced timing claim.',
            'R2v2 is lower than R1v2 in both measured 100-case workloads, but still misses 500 ms; v1 performance is mixed.',
            'A single paired series per package/workload does not establish confidence intervals or universal improvement.',
            'No real provider, personal credential, external network request or productive write was executed.',
        ],
    }
    save(OUT / 'qualification.json', qualification)
    rows = ['# Persistent ASGI comparison', '',
            '**FAIL:** all eight 100-connection cuts exceed 500 ms p95. All six 1/10-connection cuts meet 500 ms. First useful DOM remains NOT_RUN.', '',
            '| Case | Overview p95 ms | Activity p95 ms |', '|---|---:|---:|']
    rows += [f"| {c['case']} | {c['p95_ms']['overview_refresh']:.3f} | {c['p95_ms']['activity_page']:.3f} |" for c in cases]
    rows += ['', *qualification['limitations'], '',
             'All 14 workers exited0 physically. Each report contains 20 raw samples per series, byte counts, query counts, package origins/hashes and start/end immutability checks. New byte-identical clones came from the unmeasured original seeds. No infrastructure retry occurred. The launcher preparation fixed a duplicate `cwd.mkdir` before any worker execution; that change is isolated from product code.', '']
    (OUT / 'report.md').write_text('\n'.join(rows), encoding='utf-8')
    paths = list(OUT.glob('*')) + [HERE / c['launch'].removeprefix('../') for c in cases] + [Path(__file__)]
    save(OUT / 'manifest.json', {'files': [
        {'path': p.relative_to(HERE).as_posix(), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest(), 'bytes': p.stat().st_size}
        for p in sorted(paths) if p.is_file() and p.name != 'manifest.json'
    ]})
    print(json.dumps({'qualification': str(OUT / 'qualification.json'), 'sha256': hashlib.sha256((OUT / 'qualification.json').read_bytes()).hexdigest(),
                      'cases': len(cases), 'failed_target': len(failed), 'physical_exit': True}))


if __name__ == '__main__':
    main()

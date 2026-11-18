"""Seal the final10 persistent measurements without executing application code."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / 'persistent-r6-final'


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def main():
    result = json.loads((OUT / 'result.json').read_text(encoding='utf-8'))
    plan = json.loads((OUT / 'plan.json').read_text(encoding='utf-8'))
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
        cases.append({'case':item['case'],'connections':report['connections'],'volume':report['volume'],
            'wheel_sha256':report['wheel_sha256'],'source_candidate':report['source_candidate'],
            'payload_files':report['payload_files'],'package_modules':report['package_modules'],
            'series':{key:{k:v for k,v in value.items() if k!='samples'} for key,value in report['series'].items()},
            'targets':report['targets'],'first_http_response':report['first_http_response'],
            'instrumentation':report['instrumentation'],'schema_after':report['schema_after'],
            'pid':launch['pid'],'physical_exit':True,'launch':'../'+item['launch'],'report':report_path.name})
        launches.append(launch_path)
    failed = [c['case'] for c in cases if not c['targets']['read_target_met']]
    assert len(failed) == 6 and all('-100-' in name for name in failed)
    paired = []
    for workload in ('mixed','open'):
        base = next(c for c in cases if c['case']==f'{workload}-100-baseline-v1')
        for version in (1,2):
            current = next(c for c in cases if c['case']==f'{workload}-100-candidate-v{version}')
            paired.append({'workload':workload,'variant':f'candidate-v{version}',
                'p95_delta_percent':{key:100*(current['series'][key]['nearest_rank_p95_ms']/base['series'][key]['nearest_rank_p95_ms']-1)
                                     for key in base['series']}})
    qualification = {'version':1,'status':'FAIL','cut':'final R6 persistent ASGI, separately preserved original/R2 antecedents',
        'counts':{'measured':10,'read_target_pass':4,'read_target_fail':6,'not_run':0},
        'candidate_source':'90b94ca9673c087554b7dc4a226490ef5417bd32',
        'candidate_wheel_sha256':'8ab8f08e8f5e06b428ed4642045ad5e4069d93891a869d4dc61fcaa5bb3ffa19',
        'samples_per_series':20,'warmup_per_series':3,
        'targets':{'read_p95_ms':500,'first_http_proxy_ms':2000,'first_useful_dom':'NOT_RUN'},
        'cases':cases,'paired_large_comparisons':paired,'read_target_failed_cases':failed,
        'cleanup':{'all10workers_physically_exited':True,'orchestrator_exit_code':0,'timeout':False,'retry':False,
                   'app_readers_active_after_window':False},
        'seed_dataset_schema_payload_productive_drift':False,
        'limits':['Persistent httpx ASGI transport, one loop per worker, no TCP/browser/lifespan/background runtime.',
                  'First HTTP proxy met 2s in all cuts; this is not first-useful DOM. Prepared HTTP/browser experiment is not executed.',
                  'Own SQL synthetic facts do not qualify provider, native liveness/authority, real grants or decision application.',
                  'All original 12 and persistent R2 cuts remain immutable; later source optimizations do not rewrite their results.',
                  'Query counts do not measure internal SQL row-scan complexity. No target waiver or confidence-interval claim.',
                  'Mixed100 has 925 terminal/75 open; OPEN100 has 1000 open/100000 history. They are separate workloads.',
                  'No product/source/schema edits or new optimization were made during this window.']}
    save(OUT/'qualification.json',qualification)
    lines=['# Final R6 persistent-ASGI measurements','',
           '**FAIL:** all six 100-connection cuts exceed the original 500ms p95 target. Four 1/10-connection candidate checks meet it. No threshold was relaxed; no retry or new optimization occurred.','',
           '| Case | Overview p50/p95 ms | Activity p50/p95 ms | Queries overview/activity | Bytes overview/activity |',
           '|---|---:|---:|---:|---:|']
    for c in cases:
        o,a=c['series']['overview_refresh'],c['series']['activity_page']
        io,ia=c['instrumentation']['overview_refresh'],c['instrumentation']['activity_page']
        lines.append(f"| {c['case']} | {o['p50_ms']:.3f} / {o['nearest_rank_p95_ms']:.3f} | {a['p50_ms']:.3f} / {a['nearest_rank_p95_ms']:.3f} | {io['statement_count']} / {ia['statement_count']} | {o['max_payload_bytes']} / {a['max_payload_bytes']} |")
    lines += ['', 'Paired p95 differences against the baseline in this same window (positive is slower):','']
    for c in paired:
        lines.append(f"- {c['workload']} {c['variant']}: overview {c['p95_delta_percent']['overview_refresh']:+.2f}%; activity {c['p95_delta_percent']['activity_page']:+.2f}%.")
    lines += ['',*qualification['limits'],'',
              'Every report preserves 20 raw samples per series, exact package origins/bytes, schema/seed ownership checks and productive-table snapshots. All ten workers exited 0 physically and the orchestrator exited 0. The exclusive window is closed; only stdlib evidence curation followed.', '']
    (OUT/'report.md').write_text('\n'.join(lines),encoding='utf-8')
    paths=list(OUT.iterdir())+launches+[Path(__file__),HERE/'persistent-final-matrix.py',HERE/'persistent-launch.py',HERE/'persistent-worker.py']
    save(OUT/'manifest.json',{'files':[{'path':p.relative_to(HERE).as_posix(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size}
                                     for p in sorted(paths) if p.is_file() and p.name!='manifest.json']})
    print(json.dumps({'status':'FAIL','counts':qualification['counts'],'qualification_sha256':hashlib.sha256((OUT/'qualification.json').read_bytes()).hexdigest()}))


if __name__=='__main__':
    main()

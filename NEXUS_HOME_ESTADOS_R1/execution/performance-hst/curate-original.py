"""Copy immutable original timing reports; never remeasure or revise targets."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOTS = {
    'mixed': Path('C:/Users/jpamb/AppData/Local/Temp/nexus-hst-performance-dataset-3dccbd580bd34431bb61ba507dfa9559'),
    'open': Path('C:/Users/jpamb/AppData/Local/Temp/nexus-hst-performance-open-c7deab6559c14026bbedef93822237d9'),
}


def main():
    out = HERE / 'original-timings'
    out.mkdir(exist_ok=True)
    cuts, manifest = [], []
    for workload, root in ROOTS.items():
        for source in sorted((root / 'reports').glob('measure-*.json')):
            data = source.read_bytes()
            target = out / source.name
            if target.exists() and target.read_bytes() != data:
                raise ValueError(f'Refusing to replace original report {target}')
            target.write_bytes(data)
            report = json.loads(data)
            manifest.append({'path': target.relative_to(HERE).as_posix(),
                             'sha256': hashlib.sha256(data).hexdigest(), 'source': str(source)})
            cuts.append({'workload': workload, 'connections': report['connections'],
                         'variant': report['variant'], 'report': target.relative_to(HERE).as_posix(),
                         'wheel_sha256': report['wheel_sha256'], 'source_candidate': report['source_candidate'],
                         'series': {key: {k: v for k, v in value.items() if k not in ('samples', 'warmup')}
                                    for key, value in report['series'].items()},
                         'instrumentation': report['instrumentation'], 'targets': report['targets'],
                         'payload_drift': report['payload_drift'], 'productive_drift': report['productive_drift']})
    assert len(cuts) == 12
    summary = {'status': 'FAIL', 'read_p95_target_ms': 500, 'warmup': 3, 'samples_per_series': 20,
               'cuts': cuts, 'manifest': manifest,
               'limitations': [
                   'HTTP/ASGI only: first useful DOM target 2s remains NOT_RUN.',
                   'TestClient creates a fresh AnyIO portal per GET; original timings remain failed, not corrected retroactively.',
                   'Mixed 100-case has 925 terminal and 75 open activities; separate OPEN dataset has 1000 open activities and 100000 history events.',
                   'Synthetic SQL performance facts do not qualify real runtime, authority, grants or native causal progress.',
                   'No latency claim applies to later source optimizations or a future candidate package.',
                   'Diagnostic cProfile costs overlap and are not additional p95 measurements.',
               ]}
    (HERE / 'original-summary.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    lines = ['# Original performance cuts', '',
             'FAIL: the 500 ms p95 target is missed by all 100-connection cuts. These results remain antecedents of the revision/SQL optimizations.', '',
             '| Workload | Connections | Variant | Overview p95 ms | Activity page p95 ms |',
             '|---|---:|---|---:|---:|']
    for cut in cuts:
        series = cut['series']
        lines.append(f"| {cut['workload']} | {cut['connections']} | {cut['variant']} | {series['overview_refresh']['nearest_rank_p95_ms']:.3f} | {series['activity_page']['nearest_rank_p95_ms']:.3f} |")
    lines += ['', *summary['limitations'], '',
              'All twelve workers exited with HTTP 200/ready, zero productive-table drift and unchanged installed wheel payloads. Per-process exit evidence remains in the corresponding `*-launch.json` files. Raw samples and exact report hashes are retained in `original-timings/` and `original-summary.json`. Infrastructure failures are preserved as build-attempt1/2 and profile-antecedent; they are not latency results.', '']
    (HERE / 'original-summary.md').write_text('\n'.join(lines), encoding='utf-8')


if __name__ == '__main__':
    main()

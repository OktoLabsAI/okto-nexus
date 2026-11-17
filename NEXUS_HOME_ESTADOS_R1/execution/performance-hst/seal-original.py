"""Seal original performance evidence without changing measurements or sources."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    summary = json.loads((HERE / 'original-summary.json').read_text(encoding='utf-8'))
    for name, root in (
        ('mixed', 'nexus-hst-performance-dataset-3dccbd580bd34431bb61ba507dfa9559'),
        ('open', 'nexus-hst-performance-open-c7deab6559c14026bbedef93822237d9'),
    ):
        raw = (Path('C:/Users/jpamb/AppData/Local/Temp') / root / 'dataset.json').read_bytes()
        target = HERE / f'original-{name}-dataset.json'
        if target.exists() and target.read_bytes() != raw:
            raise ValueError('Dataset metadata is immutable')
        target.write_bytes(raw)
    exits = []
    for cut in summary['cuts']:
        stem = Path(cut['report']).stem
        launch = json.loads((HERE / f'{stem}-launch.json').read_text(encoding='utf-8'))
        assert launch['exit_code'] == 0 and launch['physical_exit'] is True
        exits.append({'report': cut['report'], 'pid': launch['pid'], 'physical_exit': True, 'exit_code': 0})
    report = {
        'version': 1, 'qualification': 'FAIL', 'reason': '100-connection p95 read latency exceeds 500 ms',
        'cut': 'original installed baseline i4 / candidate ezz4igiu, before r2 optimization',
        'baseline_wheel': 'd2c322168d56e87bde22cfe262d5d2fbc9a5737b0572144774894624d561cf88',
        'candidate_wheel': '15cc6dfc6b43fc815d5031a8378232b1bfa96f9048eefb4d85699337994a5af7',
        'cut_count': len(exits), 'warmup_per_series': 3, 'samples_per_series': 20,
        'first_useful_dom': 'NOT_RUN', 'thresholds_unchanged': True,
        'measurements': 'original-summary.json', 'diagnostic': 'candidate100-v2-diagnostics.json',
        'diagnostic_scope': 'Separate mixed100 candidate-v2 GETs: service/serialization cProfile, SQL execute/fetch+EXPLAIN, and main-thread transport cProfile. Not new p95; cumulative costs overlap.',
        'physical_exits': exits,
        'infrastructure_antecedents': {
            'build-attempt1.json': 'Popen function replacement broke SDK typing before dataset seed; no latency result.',
            'build-attempt2.json': 'Network guard blocked Windows internal asyncio socketpair before dataset seed; no latency result.',
            'profile-antecedent': 'Nested cProfile rejected by Python3.13; no diagnostic or timing claim from this attempt.',
        },
        'security_scope': 'Own temporary synthetic SQL datasets; no provider, harness process, real credential, TCP service or productive API operation. Only guarded OS self-pipe loopback for AnyIO transport.',
        'limitations': summary['limitations'],
        'cleanup': 'All twelve owned timing workers physically exited as recorded individually; diagnostic worker also exited0. Temporary synthetic DBs retained for paired future comparison, not copied to repository.',
    }
    (HERE / 'original-qualification.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    files = []
    for path in sorted(HERE.rglob('*')):
        if path.is_file() and path.name != 'original-manifest.json' and '__pycache__' not in path.parts:
            files.append({'path': path.relative_to(HERE).as_posix(), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'bytes': path.stat().st_size})
    (HERE / 'original-manifest.json').write_text(json.dumps({'scope': 'Evidence files present at original performance curation; later cuts require separate manifests.', 'files': files}, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()

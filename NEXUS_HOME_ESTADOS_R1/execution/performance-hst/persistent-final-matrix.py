"""Prepare or run10 sequential persistent-ASGI cuts; never rebuild seeds."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
TEMP = Path('C:/Users/jpamb/AppData/Local/Temp')
MIXED = TEMP / 'nexus-hst-performance-dataset-3dccbd580bd34431bb61ba507dfa9559/dataset.json'
OPEN = TEMP / 'nexus-hst-performance-open-c7deab6559c14026bbedef93822237d9/dataset.json'
BASELINE = REPO / 'NEXUS_QUICK_CONNECT_R1/execution/qc36-final-package/READY.json'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, data):
    path.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--candidate-ready', type=Path, required=True)
    parser.add_argument('--label', required=True)
    parser.add_argument('--window', choices=['PERF_WINDOW_OPEN'])
    args = parser.parse_args()
    assert args.label and all(c.isalnum() or c in '-_' for c in args.label)
    destination = HERE / ('persistent-' + args.label)
    assert not destination.exists(), 'Never overwrite another cut'
    jobs = []
    # Large paired cuts first; small final-package checks follow.
    for workload, dataset in [('mixed', MIXED), ('open', OPEN)]:
        for variant, ready in [('baseline-v1', BASELINE), ('candidate-v1', args.candidate_ready), ('candidate-v2', args.candidate_ready)]:
            jobs.append(dict(name=f'{workload}-100-{variant}', dataset=dataset, connections=100, variant=variant, ready=ready))
    for size in (1, 10):
        for variant in ('candidate-v1', 'candidate-v2'):
            jobs.append(dict(name=f'mixed-{size}-{variant}', dataset=MIXED, connections=size, variant=variant, ready=args.candidate_ready))
    assert len(jobs) == 10
    destination.mkdir()
    jobs = [{key: str(value.resolve()) if isinstance(value, Path) else value for key, value in job.items()} for job in jobs]
    pins = {str(path.relative_to(REPO)): sha(path) for path in [
        HERE / 'benchmark.py', HERE / 'dataset.py', HERE / 'measure-worker.py',
        HERE / 'persistent-worker.py', HERE / 'persistent-launch.py', Path(__file__),
    ]}
    plan = dict(status='PREPARED_NOT_EXECUTED', jobs=jobs, helper_pins=pins,
                datasets={str(path): sha(path) for path in (MIXED, OPEN)}, samples=20, warmup=3,
                worker_deadline_seconds=180, parent_deadline_seconds=240,
                thresholds=dict(read_p95_ms=500, first_http_proxy_ms=2000, first_useful_dom='NOT_RUN'))
    save(destination / 'plan.json', plan)
    if args.window is None:
        print(json.dumps(dict(status=plan['status'], plan=str(destination / 'plan.json'))), flush=True)
        return
    assert Path(args.candidate_ready).exists(), 'Final READY required before any child starts'
    results = []
    for job in jobs:
        label = args.label + '-' + job['name']
        command = [sys.executable, '-B', '-X', 'utf8', str(HERE / 'persistent-launch.py'),
                   '--window', args.window, '--ready', job['ready'], '--dataset', job['dataset'],
                   '--connections', str(job['connections']), '--variant', job['variant'], '--label', label]
        assert all(sha(REPO / p) == value for p, value in pins.items()), 'Helper drift'
        started = time.monotonic()
        print(json.dumps(dict(phase='START', case=job['name'])), flush=True)
        # Launcher contains its own bounded240s worker; no new process tree is
        # started until it has confirmed that worker exited physically.
        run = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding='utf-8')
        (destination / (job['name'] + '-stdout.txt')).write_text(run.stdout, encoding='utf-8')
        (destination / (job['name'] + '-stderr.txt')).write_text(run.stderr, encoding='utf-8')
        result = dict(case=job['name'], exit_code=run.returncode, seconds=time.monotonic() - started)
        launch_path = HERE / ('persistent-' + label + '-launch.json')
        if launch_path.exists():
            launch = json.loads(launch_path.read_text(encoding='utf-8'))
            assert launch['physical_exit'], 'Do not continue with a live preceding worker'
            result['launch'] = launch_path.name
            output = Path(launch['output'])
            if output.exists():
                report = json.loads(output.read_text(encoding='utf-8'))
                assert report['schema_after'] == next(c['schema_sha256'] for c in json.loads(Path(job['dataset']).read_text())['cases'] if c['size'] == job['connections'])
                (destination / (job['name'] + '-report.json')).write_bytes(output.read_bytes())
                result.update(status=report['status'], targets=report['targets'],
                              p95_ms={key: value['nearest_rank_p95_ms'] for key, value in report['series'].items()})
        results.append(result)
        save(destination / 'progress.json', dict(status='RUNNING', completed=results, remaining=jobs[len(results):]))
        print(json.dumps(result), flush=True)
        if run.returncode or result.get('status') != 'MEASURED':
            save(destination / 'result.json', dict(status='INCOMPLETE', completed=results, not_run=jobs[len(results):]))
            raise SystemExit(run.returncode or 1)
    save(destination / 'result.json', dict(status='MEASURED', completed=results, not_run=[]))


if __name__ == '__main__':
    main()

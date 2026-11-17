"""Preserve exact interrupted-shard accounting; never promotes hung nodes."""
import importlib.util
import json
from pathlib import Path

from run_shard import ROOT

HERE = Path(__file__).resolve().parent


def main():
    plan = json.loads((HERE / 'remainder2-plan.json').read_text())
    own = Path(plan['own_root'])
    nodes = set(json.loads((own / 'collection/output/all-nodeids.json').read_text()))
    original = set(plan['completed_original'])
    observed, complete, failures, waves = set(), set(), [], []
    for directory in sorted(own.glob('wave*')):
        out = directory / 'output'
        result = json.loads((out / 'result.json').read_text())
        rows = [json.loads(line) for line in (out / 'reports.jsonl').read_text().splitlines()]
        observed.update(row['nodeid'] for row in rows)
        complete.update(row['nodeid'] for row in rows if row['phase'] == 'teardown')
        failed = [json.loads(line) for line in (out / 'failures.jsonl').read_text().splitlines()]
        failures.extend(failed)
        waves.append(dict(wave=directory.name, output=str(out), exit_code=result['exit_code'],
            phases=result['phases'], physically_exited=result['physically_exited'],
            call_failed=[row['nodeid'] for row in failed if row['phase'] == 'call'],
            teardown_completed=[row['nodeid'] for row in rows if row['phase'] == 'teardown']))
    assert original <= nodes and observed <= nodes
    assert not original & observed
    spec = importlib.util.spec_from_file_location('ci_hashes_readonly', ROOT / 'tools/ci_installed.py')
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    old = json.loads(Path(plan['original_campaign']).read_text())['input_hashes']
    now = helper.input_hashes()
    drift = sorted(name for name in old.keys() | now.keys() if old.get(name) != now.get(name))
    report = dict(status='STOPPED_FAIL_FAST_INCOMPLETE_NOT_FULL_PASS', shard=2,
        original_campaign=plan['original_campaign'], collected_total=len(nodes),
        original_reported=plan['completed_original'], derivative_observed_node_count=len(observed),
        derivative_teardown_complete_count=len(complete), derivative_partial_nodes=sorted(observed-complete),
        still_not_run=sorted(nodes-original-observed), still_not_run_count=len(nodes-original-observed),
        waves=waves, captured_failures=failures, changed_inputs_vs_original_start=drift,
        boundary_stop=json.loads((HERE / 'remainder2-boundary-stop.json').read_text()),
        qualification_limits=[
            'Original 145 PASS and 3 FAIL call lines lack final XML/trace due stuck teardown.',
            'Derivative call FAILs are preserved with live longrepr, interrupted teardown is not PASS.',
            'Frozen installed parent origin is checked; explicit legacy fixture children may use checkout source.',
            'No real providers/native harnesses or Windows session/logout/reboot actions.',
            'No product/test/CI helper edits, no package install or prefix payload changes.'
        ])
    (HERE / 'remainder2-stopped-summary.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(dict(collected=len(nodes), original_reported=len(original),
        derivative_observed=len(observed), derivative_partial=len(observed-complete),
        not_run=len(nodes-original-observed), input_drift=drift,
        all_wave_processes_exited=all(all(w['physically_exited'].values()) for w in waves))), flush=True)


if __name__ == '__main__':
    main()

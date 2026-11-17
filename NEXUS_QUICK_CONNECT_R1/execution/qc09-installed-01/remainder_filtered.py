"""Use exact retained node allowlist through file collection, avoiding2k selectors."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile

import remainder as runner
from run_shard import ROOT

HERE = Path(__file__).resolve().parent
BASE_PLUGIN = runner.PLUGIN
FILTER = '''
ALLOWED=set(json.loads(pathlib.Path(ALLOWED_VALUE).read_text(encoding='utf-8')))
def pytest_collectreport(report):
    (OUT/'progress.json').write_text(json.dumps(dict(nodeid=report.nodeid,phase='collection',at=time.time())),encoding='utf-8')
def pytest_collection_modifyitems(config,items):
    actual={i.nodeid for i in items}
    missing=ALLOWED-actual
    assert not missing, sorted(missing)
    chosen=[i for i in items if i.nodeid in ALLOWED]
    ignored=[i for i in items if i.nodeid not in ALLOWED]
    config.hook.pytest_deselected(items=ignored)
    items[:]=chosen
'''


def main():
    index = int(sys.argv[1])
    assert index in (0, 1)
    plan = json.loads((HERE / f'remainder{index}-plan.json').read_text())
    remaining = plan['remaining']
    own = Path(tempfile.mkdtemp(prefix=f'nexus-qc09-filtered-remainder{index}-'))
    ready = dict(shard=index, own_root=str(own), orchestrator_pid=os.getpid(), remaining_count=len(remaining),
        inherited_exact_plan=str(HERE / f'remainder{index}-plan.json'),
        selection='Original collected nodes minus only completed original items; file collection with exact node allowlist')
    (HERE / f'filtered{index}-ready.json').write_text(json.dumps(ready, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(ready), flush=True)
    spec = importlib.util.spec_from_file_location('qc_input_hashes', ROOT / 'tools/ci_installed.py')
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    before = helper.input_hashes()
    (own / 'input-hashes-before.json').write_text(json.dumps(before, indent=2)+'\n', encoding='utf-8')
    waves = []
    for number in range(1, 9):
        if not remaining:
            break
        allow = own / f'wave{number}-allowed.json'
        allow.write_text(json.dumps(remaining, indent=2)+'\n', encoding='utf-8')
        files = list(dict.fromkeys(node.split('::', 1)[0] for node in remaining))
        runner.PLUGIN = BASE_PLUGIN + FILTER.replace('ALLOWED_VALUE', repr(str(allow)))
        output, result = runner.execute(own / f'wave{number}', files)
        reports = [json.loads(line) for line in (output / 'reports.jsonl').read_text().splitlines()] if (output / 'reports.jsonl').exists() else []
        complete = {r['nodeid'] for r in reports if r['phase'] == 'teardown'}
        interrupted = None
        if result['phases']:
            progress = output / 'progress.json'
            interrupted = json.loads(progress.read_text()) if progress.exists() else None
            if interrupted and interrupted['phase'] != 'collection':
                assert interrupted['nodeid'] in remaining
                complete.add(interrupted['nodeid'])
        assert complete <= set(remaining)
        waves.append(dict(wave=number, output=str(output), allowed_sha256=hashlib.sha256(allow.read_bytes()).hexdigest(),
            completed_count=len(complete), interrupted_node=interrupted, result=result))
        remaining = [node for node in remaining if node not in complete]
        after = helper.input_hashes()
        changed = sorted(name for name in before.keys() | after.keys() if before.get(name) != after.get(name))
        (own / f'input-hashes-after-wave{number}.json').write_text(json.dumps(after, indent=2)+'\n', encoding='utf-8')
        report = dict(ready, waves=waves, still_not_run=remaining, changed_inputs=changed,
            status='INPUTS_CHANGED' if changed else 'INCOMPLETE' if remaining else 'EXECUTED_WITH_RECORDED_RESULTS')
        (HERE / f'filtered{index}-result.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
        print(json.dumps(dict(shard=index, wave=number, exit_code=result['exit_code'], completed=len(complete),
            remaining=len(remaining), interrupted_node=interrupted, changed_inputs=changed)), flush=True)
        if changed or not complete:
            break
    return 0 if not remaining else 2


if __name__ == '__main__':
    raise SystemExit(main())

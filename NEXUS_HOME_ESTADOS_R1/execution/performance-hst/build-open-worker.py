"""Required J04 complement: new dataset with exactly 1000 OPEN activities."""
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


parser = argparse.ArgumentParser(allow_abbrev=False)
parser.add_argument('--root', type=Path, required=True)
parser.add_argument('--ready', type=Path, required=True)
parser.add_argument('--released', choices=('PACKAGE_READY',), required=True)
args = parser.parse_args()
root = args.root.resolve()
if not root.is_relative_to(Path(tempfile.gettempdir()).resolve()) or not root.name.startswith('nexus-hst-performance-'):
    raise RuntimeError('Own new Temp root required.')
if not Path.cwd().resolve().is_relative_to(Path(tempfile.gettempdir()).resolve()):
    raise RuntimeError('Own Temp cwd required.')
benchmark = load('hst_perf_open_common', HERE / 'benchmark.py')
guard = load('hst_perf_open_guard', HERE / 'guard-depth.py')
benchmark.sanitize_environment()
ready = json.loads(args.ready.read_text())
before = benchmark.payload(ready)
root.mkdir(parents=True, exist_ok=False)
benchmark.save(root / '.hst-owned.json', dict(root=str(root), kind='hst-performance-synthetic-only'))
with guard.guarded():
    fixture = load('hst_perf_open_fixtures', REPO / 'NEXUS_UI_R1/execution/fixtures.py')
    seed = load('hst_perf_open_seed_base', HERE / 'dataset.py')
    with fixture.scenario(root / 'seed-100-open', clock=fixture.ControlledClock(benchmark.NOW)) as s:
        s.fixtures_copy = fixture._copy
        volume = seed.seed(s, 100, 100_000)
        with s.factory.unit_of_work() as uow:
            c = uow.connection
            c.execute("UPDATE execution_operations SET admission_state='ACCEPTED' WHERE workspace_id='hst-perf' AND action='turn.submit'")
            c.execute("UPDATE execution_receipts SET stage='SUBMITTED' WHERE (server_id,executor_id,operation_id) IN "
                      "(SELECT server_id,executor_id,operation_id FROM execution_operations WHERE workspace_id='hst-perf' AND action='turn.submit')")
            actual_open = c.execute("SELECT COUNT(*) FROM execution_operations WHERE workspace_id='hst-perf' AND action='turn.submit' AND admission_state='ACCEPTED'").fetchone()[0]
            actual_terminal = c.execute("SELECT COUNT(*) FROM execution_receipts r JOIN execution_operations o USING(server_id,executor_id,operation_id) "
                "WHERE o.workspace_id='hst-perf' AND o.action='turn.submit' AND r.stage IN ('SUCCEEDED','FAILED','CANCELLED')").fetchone()[0]
            actual_events = c.execute("SELECT COUNT(*) FROM execution_event_ingress i JOIN execution_sessions s USING(server_id,executor_id,session_id) "
                                     "WHERE s.workspace_id='hst-perf'").fetchone()[0]
            assert actual_open == 1000 and actual_terminal == 0 and actual_events == 100_000
            assert not list(c.execute('PRAGMA foreign_key_check'))
        volume.update(workload='J04-open-complement', expected_open=1000, actual_open=actual_open,
            terminal_activities=actual_terminal, expected_native_history=100_000, actual_native_history=actual_events,
            algorithm='Original synthetic generator, then all own benchmark turn activities set ACCEPTED/SUBMITTED before cloning; no native effects/authority qualification.')
        home = Path(s.deps.config.home_dir).resolve()
        relative = Path(s.deps.config.db_path).resolve().relative_to(home)
    clones = {}
    for variant in ('baseline-v1', 'candidate-v1', 'candidate-v2'):
        target = root / 'case-100' / variant
        shutil.copytree(home, target)
        assert benchmark.sha(target / relative) == benchmark.sha(home / relative)
        clones[variant] = str(target)
benchmark.origin_guard()
assert before == benchmark.payload(ready)
manifest = dict(version=1, state='BUILT_NOT_MEASURED', workload='J04-open-complement', ready=ready, clock=benchmark.NOW,
    helper_source_pins=benchmark.helper_pins(), builder_sha256=benchmark.sha(__file__),
    cases=[dict(size=100, volume=volume, db_relative=str(relative), database_sha256=benchmark.sha(home / relative),
                schema_sha256=benchmark.schema(home / relative), clones=clones)])
benchmark.save(root / 'dataset.json', manifest)
print(json.dumps(dict(state=manifest['state'], dataset=str(root), volume=volume)), flush=True)

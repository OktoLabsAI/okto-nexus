"""Read-only post-exit check; never calls the frozen runner's main()."""
import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
root = Path('C:/Users/jpamb/AppData/Local/Temp/nexus-hst-browser-6xmlua2u')
raw_path = root / 'native-zoom-run.private.json'
raw = json.loads(raw_path.read_text())
spec = importlib.util.spec_from_file_location('frozen_i05_runner', HERE / 'run_v2.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
after, _, _, _ = module.check(HERE / 'ROOT-GATE-v2.json')
assert after == raw['before']
assert module.sha(root / 'zoom-probe.py') == module.sha(module.NATIVE / 'probe_server_v2.py')
assert module.sha(root / 'playwright-cli.json') == module.sha(module.NATIVE / 'playwright-cli.json')
out = HERE / 'offline-pin-supplement'
out.mkdir(exist_ok=False)
report = dict(
    status='PASS_OFFLINE_POST_EXIT_PIN_CHECK',
    method='Import frozen run_v2.py and call pure check(Path gate) only; no main, allocation, browser, fixture or provider invocation',
    original_runtime_exit=1,
    original_runtime_error=dict(stage='final pin guard', type='AttributeError', cause='Local card variable a shadows argparse namespace before check(a.gate).'),
    raw_run_sha256=hashlib.sha256(raw_path.read_bytes()).hexdigest(),
    original_qualification_sha256=module.sha(HERE / 'runs/hst-native-zoom-r9-app-1/qualification.json'),
    original_manifest_sha256=module.sha(HERE / 'runs/hst-native-zoom-r9-app-1/manifest.json'),
    checked=after,
    matching_original_before=True,
    probe_worker_and_config_match=True,
    limits=['Offline later observation; original runtime error and after=null remain unchanged.', 'Canonical close UNKNOWN for A1/A2 is not resolved by this pin check.'],
)
(out / 'qualification.json').write_text(json.dumps(report, indent=2) + '\n')
manifest = {p.name:dict(sha256=module.sha(p),bytes=p.stat().st_size) for p in out.iterdir() if p.is_file()}
manifest['../offline_pin_check.py'] = dict(sha256=module.sha(Path(__file__)),bytes=Path(__file__).stat().st_size)
(out / 'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
print(json.dumps(dict(status=report['status'],manifest_sha256=module.sha(out / 'manifest.json'),checked=after),indent=2))

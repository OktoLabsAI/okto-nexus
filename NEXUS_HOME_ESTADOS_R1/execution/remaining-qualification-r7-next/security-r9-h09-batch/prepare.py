"""Gate before allocation; only prepare an inert own fixture, never start it."""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--gate', type=Path, required=True)
    args = parser.parse_args()
    preflight = module('security_preflight', HERE / 'preflight.py')
    checked = preflight.check(args.gate)  # All checks BEFORE allocation/subprocess.
    manifest = json.loads((HERE / 'prepared-manifest.json').read_text())
    browser = preflight.REPO / 'NEXUS_HOME_ESTADOS_R1/execution/browser-hst'
    ready = preflight.REPO / 'NEXUS_HOME_ESTADOS_R1/execution/package-hst-r9/READY.json'
    result = subprocess.run([
        'rtk', 'proxy', sys.executable, '-B', str(browser / 'prepare_runtime.py'),
        '--package-ready', str(ready), '--expected-source', preflight.SOURCE,
        '--mode', 'baseline', '--browser-window-open',
    ], input=b'', capture_output=True, timeout=20, check=True)
    allocation = json.loads(result.stdout)
    root = Path(allocation['root']).resolve()
    builder = module('security_fixture_builder', HERE / 'fixture_builder.py')
    source = browser / 'fixture.py'
    proof = builder.build(root, source, manifest['input_pins'][
        source.relative_to(preflight.REPO).as_posix()
    ], 'S1')
    runtime_ready = root / 'runtime-ready.json'
    config = json.loads(runtime_ready.read_text())
    config['fixture_sha256'] = proof['fixture_sha256']
    config['helper_pins']['security_controls.py'] = proof['helper_sha256']
    config['security_gate_sha256'] = preflight.sha(args.gate)
    config['security_case'] = checked['case']
    config['security_cut_id'] = checked['cut_id']
    runtime_ready.write_text(json.dumps(config, indent=2) + '\n')
    (root / 'security-builder-proof.json').write_text(json.dumps(proof, indent=2) + '\n')
    print(json.dumps({'root': str(root), 'runtime_ready': str(runtime_ready),
                      'fixture_built': True, 'runtime_started': False,
                      'case': checked['case'], 'provider_invocations': 0}, indent=2))


if __name__ == '__main__':
    main()

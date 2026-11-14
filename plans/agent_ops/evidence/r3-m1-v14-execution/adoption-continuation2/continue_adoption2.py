"""One explicit continuation after the pinned GET-only binding timeout."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def validate_prior(helper, context, manifest):
    prior = manifest['prior_continuation']
    for pin in prior['pins'].values():
        helper.require(sha(pin['path']) == pin['sha256'], 'PRIOR_CONTINUATION_CHANGED')
    failure = helper.read(prior['pins']['failure']['path'])
    helper.require(failure.get('error_type') == 'ConnectionError'
        and failure.get('code') == 'SERVER_UNREACHABLE'
        and all(failure.get(key) is False for key in
            ('controller_exists', 'snapshot_exists', 'original_adoption_result_exists')),
        'PRIOR_NOT_GET_ONLY_PRE_CONTROLLER_FAILURE')
    common = sys.modules['driver_common']
    common.require_tags(failure, context)
    common.require_tags(helper.read(prior['pins']['reservation']['path']), context)
    helper.require(not Path(prior['success_path']).exists(), 'PRIOR_ALREADY_SUCCEEDED')
    helper.require(prior['root_observed_exit'] == {'session_id': 52632, 'exit_code': 1},
        'PRIOR_EXIT_OBSERVATION_CHANGED')

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=('preflight', 'execute'))
    parser.add_argument('--manifest-sha256', required=True)
    args = parser.parse_args()
    if sha(HERE / 'manifest.json') != args.manifest_sha256:
        raise RuntimeError('MANIFEST_CHANGED')
    manifest = json.loads((HERE / 'manifest.json').read_bytes())
    if sha(__file__) != manifest['entry_sha256']:
        raise RuntimeError('ENTRY_CHANGED')
    pin = manifest['prior_continuation']['pins']['helper']
    if sha(pin['path']) != pin['sha256']:
        raise RuntimeError('PRIOR_HELPER_CHANGED')
    spec = importlib.util.spec_from_file_location('prior_adoption_continuation', pin['path'])
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    original_validation = helper.validate_before
    def validate(context, value):
        original_validation(context, value)
        validate_prior(helper, context, value)
    helper.validate_before = validate
    # Separate evidence directory; original helper, manifest and failed receipts stay immutable.
    helper.HERE = HERE
    return helper.main()

if __name__ == '__main__':
    raise SystemExit(main())

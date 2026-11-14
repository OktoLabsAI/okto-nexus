"""One v12 campaign only. Imports do not observe or mutate the real campaign."""
from pathlib import Path
from types import SimpleNamespace
import argparse
import hashlib
import importlib
import importlib.util
import json
import sys

HERE = Path(__file__).resolve().parent
BUNDLE = Path('C:/Users/jpamb/AppData/Local/Temp/m1-v12-bundle-bldo9qy7')
DRIVERS = BUNDLE / 'root-drivers'
PROPOSAL_SHA = 'd6b1340956fe5ed83cb16f56dd8af13c16c65341d9d517280ac2f6109d561040'
APPROVAL_SHA = '9a8824d2de05aa4202672912ac7f752a9f95d3b51726288d6fcb7a0b45130cc9'
CHECKPOINT_SHA = '89e40312cef86b38fc089857ba9dc5bc85ea29796f7003e8b96147dc12e13951'
OLD_STOP_SHA = 'c8a64c9c92d64f9b53560575aabebff8a269ae733f0a2c73c2b3121d207183a1'
CONTROL_SHA = 'f8315c107381ed0e24b19427f0855329eaed4ecb95f2135ed21bd27c626f21c6'
PID, BIRTH = 35400, 134391426803083035
GENERATION = 'd8122008262b10e75ec4d1124dd91417'
TASK_DIGEST = '427bf6ff7308e6d2a04962d367db2ee39c6fd7db45b9613a804350c1b05cd1bf'


def require(value, code):
    if not value:
        raise ValueError(code)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def parser():
    p = argparse.ArgumentParser()
    for name in ('proposal', 'expected-proposal-sha256', 'approval-path', 'approval-sha256',
                 'manifest', 'manifest-sha256'):
        p.add_argument('--' + name, required=True)
    return p


def load(args):
    require(args.expected_proposal_sha256 == PROPOSAL_SHA and sha(args.proposal) == PROPOSAL_SHA, 'ONE_PROPOSAL_REQUIRED')
    require(args.approval_sha256 == APPROVAL_SHA and sha(args.approval_path) == APPROVAL_SHA, 'ORIGINAL_APPROVAL_REQUIRED')
    require(sha(args.manifest) == args.manifest_sha256, 'SUPPLEMENT_MANIFEST_CHANGED')
    manifest = read(args.manifest)
    require(set(manifest['runtime']) == {'supplement_common.py', 'stop_once.py', 'reconcile_final.py'}, 'SUPPLEMENT_SCOPE_CHANGED')
    for name, digest in manifest['runtime'].items():
        require(sha(HERE / name) == digest, 'SUPPLEMENT_SOURCE_CHANGED')
    proposal = read(args.proposal)
    for key, entry in proposal['execution_bundle']['files'].items():
        if key.startswith('root_driver_'):
            require(Path(entry['path']).parent == DRIVERS and sha(entry['path']) == entry['sha256'], 'ORIGINAL_DRIVER_CHANGED')
    sys.path.insert(0, str(DRIVERS))
    common = importlib.import_module('driver_common')
    context = common.gate(args)
    deps = SimpleNamespace(common=common, presence=importlib.import_module('confirm_final_presence'),
        observation=importlib.import_module('m1_v12_observation'), closure=importlib.import_module('close_campaign'))
    return context, deps


def checkpoint_summary(context, deps):
    path = context.ROOT / 'private/controller.json'
    require(sha(path) == CHECKPOINT_SHA, 'CONTROLLER_CHANGED')
    value = read(path)
    entry = context.P['execution_bundle']['files']['controller_token_collector']
    require(sha(entry['path']) == entry['sha256'], 'COLLECTOR_CHANGED')
    spec = importlib.util.spec_from_file_location('supplement_collector', entry['path'])
    collector = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(collector)
    state = collector.restore(value['collector'])
    summary = deps.closure.checkpoint_summary(context, value, collector.summary(state))
    require(value['owners'] == {'local': context.P['paths']['server_home']}
        and set(value['requests']) == {'m1v12-local-setup'}, 'LOCAL_SETUP_ONLY_REQUIRED')
    request = value['requests']['m1v12-local-setup']
    require(request['kind'] == 'setup' and request['lane'] == 'local' and request['settled'] is True
        and request['monitor']['high_water'] == 22178 and value['faults'] == ['DEADLINE120'], 'SETUP_STATE_CHANGED')
    require(all(not state[k] for k in ('requests', 'streams', 'threads', 'turns'))
        and value['independent_observation']['worker_in_flight'] is False, 'WORK_OR_LIVE_WORKER_PRESENT')
    require(summary['cumulative_reserved_admissions'] == 8 and summary['cumulative_minimum_observed_tokens'] == 111651,
            'CARRY_CHANGED')
    return summary


def safe_main(function):
    try:
        return function()
    except Exception as error:
        import re
        code = str(error)
        print(json.dumps({'status': 'SUPPLEMENT_REFUSED_OR_UNCONFIRMED',
            'code': code if re.fullmatch('[A-Z0-9_]{1,128}', code) else type(error).__name__}))
        return 2

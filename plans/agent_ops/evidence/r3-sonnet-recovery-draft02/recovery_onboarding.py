"""Local canonical setup02 draft only. No identity, HTTP or provider selection."""
from pathlib import Path
import argparse
import importlib.util
import json
import subprocess
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from recovery_context import RecoveryContext, require, read_json, pin, sha


def load_base(sources):
    # Reuse the exact qualified draft schema/inventory validation, not its effects.
    for name, source in sources.items():
        path = pin(source)
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules['remote_onboarding']


def commands(X):
    p = X.P
    cli = [X.python, '-I', '-B', '-X', 'utf8', '-m']
    connector = cli + ['okto_nexus_connector.cli.main', '--state-dir', p['paths']['connector_state']]
    discover = connector + ['--json', 'discover', '--harness', 'claude_stream']
    create = connector + ['connect', '--server', p['origin'], '--harness', 'claude_stream',
        '--executable', p['native']['path'], '--project', p['paths']['project'],
        '--provider-home', p['provider_home'], '--binding-alias', p['profile'],
        '--agent', p['agent_id'], '--request-id', p['setup_request_id'],
        '--setup-draft', str(X.draft_path), '--customize', '--no-start-at-login']
    # Prospective only: this executable has NO action that dispatches this argv.
    future_review = cli + ['okto_nexus.adapters.inbound.cli.main', 'connect',
        '--operator-profile', p['operator_profile'], '--remote-draft', str(X.draft_path),
        '--profile', p['profile'], '--agent', p['agent_id'], '--workspace-id', p['workspace_id'],
        '--plan', '--json', '--home', p['paths']['operator_home']]
    return discover, create, future_review, 'sonnet\n1\n2\n3\n2\n1\n60\n3\n1\n'


def require_rotation_before_review(value, p):
    require(value.get('status') == 'ROTATED_ONCE_IMPORTED_ONCE'
        and value.get('agent_id') == p['agent_id'] and value.get('server_id') == p['server_id']
        and type(value.get('old_epoch')) is int and value['old_epoch'] == 1
        and type(value.get('current_epoch')) is int and value['current_epoch'] == 2
        and all(type(value.get(k)) is int and value[k] == 1 for k in ('rotation_post_count', 'consumer_count'))
        and value.get('original_transfer_preserved_unconfirmed') is True
        and value.get('old_profile_replayed') is False, 'CANONICAL_EPOCH_TWO_IMPORT_REQUIRED')
    transfer = value.get('protected_transfer', {})
    require(transfer.get('status') == 'TRANSFERRED_ONCE'
        and all(type(transfer.get(k)) is int and transfer[k] == 0
                for k in ('producer_exit', 'consumer_exit', 'active_job_processes_after'))
        and transfer.get('forced_owned_cleanup') is False
        and transfer.get('public_ipc_readers_joined') is True
        and transfer.get('effect_guard_required') is True
        and transfer.get('effect_gates_allowed') == ['producer', 'consumer'], 'ROTATION_IMPORT_UNCONFIRMED')


def preserve_old(before, after):
    require(before == after, 'OLD_SETUP_CHANGED_DURING_NEW_DRAFT')


class Context:
    def __init__(self, path, expected):
        require(Path(path).resolve() == HERE / 'draft02-plan.json' and sha(path) == expected, 'DRAFT_PLAN_CHANGED')
        self.P = read_json(path)
        self.plan_sha = expected
        require(self.P['scope'] == 'LOCAL_CANONICAL_SETUP02_DRAFT_ONLY'
            and self.P['setup_request_id'] == 'm1-sonnet-remote-setup-02'
            and self.P['profile'] == 'm1-sonnet-remote-recovery02'
            and self.P['agent_id'] == 'm1-sonnet-remote'
            and self.P['selected_actions'] == ['draft'], 'DRAFT_SCOPE_CHANGED')
        for source in self.P['runtime_pins'].values():
            pin(source)
        lp = self.P['lifecycle_plan']
        self.base = RecoveryContext(pin(lp), lp['sha256'])
        self.ROOT, self.PUBLIC, self.PRIVATE = self.base.ROOT, self.base.PUBLIC, self.base.PRIVATE
        self.python = self.base.python
        require(Path(self.P['python']).resolve() == Path(self.python).resolve(), 'DRAFT_PACKAGE_CHANGED')
        for name, original in [('connector_state', 'connector_state'), ('operator_home', 'operator_home'), ('project', 'connector_project')]:
            require(Path(self.P['paths'][name]).resolve() == Path(self.base.P['paths'][original]).resolve(), 'DRAFT_OWN_PATH_CHANGED')
        self.validators = load_base(self.P['qualified_sources'])
        self.draft_path = self.PUBLIC / 'recovery02-connector-draft.json'

    def save(self, name, value):
        self.base.save(name, dict(value, draft_plan_sha256=self.plan_sha))

    def invoke(self, name, argv, answers=None):
        require(name in ('discover', 'draft'), 'LOCAL_DRAFT_ACTION_REQUIRED')
        self.save('draft02-' + name + '-reserved.json', {'state': 'RESERVED_BEFORE_CLI', 'provider_calls': 0, 'argv': argv})
        stdout, stderr = self.PRIVATE / ('draft02-' + name + '.stdout'), self.PRIVATE / ('draft02-' + name + '.stderr')
        with stdout.open('xb') as out, stderr.open('xb') as err:
            child = subprocess.Popen(argv, cwd=self.ROOT, env=self.base.connector_env(),
                stdin=subprocess.PIPE if answers is not None else subprocess.DEVNULL,
                stdout=out, stderr=err, creationflags=subprocess.CREATE_NO_WINDOW)
            # Parent remains owner of this one CLI; no kill, retry or other selection.
            child.communicate(None if answers is None else answers.encode('utf-8'))
        self.save('draft02-' + name + '-returned.json', {'returncode': child.returncode,
            'stdout_sha256': sha(stdout), 'stderr_sha256': sha(stderr), 'provider_calls': 0})
        require(child.returncode == 0, 'DRAFT_CLI_UNCONFIRMED_' + name)
        return read_json(stdout) if answers is None else None


def draft(X):
    from okto_nexus_connector.platform.paths import state_file
    from okto_nexus_connector.storage.state_store import StateStore
    from okto_nexus_connector.services import remote_setup
    store = StateStore(state_file(Path(X.P['paths']['connector_state'])))
    # Compare the actual current setup01 record before/after this selection. Do
    # not pin a stale whole-state hash from before prepare/rotation/lifecycle.
    before = remote_setup.load(store, 'm1-sonnet-remote-setup-01')
    require(remote_setup.PREFIX + X.P['setup_request_id'] not in store.load().preferences,
            'SETUP02_ALREADY_EXISTS_NO_REPLAY')
    require(not X.draft_path.exists(), 'DRAFT02_ALREADY_EXISTS')
    pin(X.P['native'])
    discover, create, future_review, answers = commands(X)
    inventory = X.invoke('discover', discover)
    selected = X.validators.validate_inventory(inventory, X.P['native'])
    X.save('draft02-inventory-selection.json', selected)
    X.invoke('draft', create, answers)
    document = read_json(X.draft_path)
    X.validators.validate_draft(document, X.P)
    require(document.get('agent_hint') == X.P['agent_id'], 'EXISTING_AGENT_HINT_CHANGED')
    preserve_old(before, remote_setup.load(store, 'm1-sonnet-remote-setup-01'))
    X.save('draft02-validated.json', {'draft_sha256': sha(X.draft_path),
        'configuration': document['configuration'], 'candidate_ref': document['installation']['candidate_ref'],
        'setup01_preserved': True, 'identity_created': False, 'http_selected': False, 'provider_calls': 0,
        'future_review_argv_not_executed': future_review, 'future_review_requires_epoch2_rotation_import': True})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--plan', required=True)
    parser.add_argument('--expected-plan-sha256', required=True)
    parser.add_argument('action', choices=['draft'])
    args = parser.parse_args()
    X = Context(args.plan, args.expected_plan_sha256)
    draft(X)
    print(json.dumps({'status': 'DRAFT02_CANONICALLY_PREPARED', 'provider_calls': 0}))


if __name__ == '__main__':
    main()

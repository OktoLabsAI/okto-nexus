"""Finite canonical setup02 reuse: review/bootstrap/host/decision/Finish/DONE."""
from pathlib import Path
import argparse
import json
import subprocess
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from recovery_context import RecoveryContext, require, read_json, pin, sha
from recovery_onboarding import require_rotation_before_review

ACTIONS = ('review', 'bootstrap', 'host-prepare', 'operator-decide', 'host-finish', 'complete')


def validate_review(doc, p, draft):
    review = doc.get('remote_review', {})
    selected = review.get('selection', {})
    require(doc.get('kind') == 'remote_project_setup' and doc.get('server_id') == p['server_id']
        and doc.get('review_revision') == review.get('review_revision') and isinstance(doc.get('review_revision'), str)
        and review.get('draft') == draft and selected.get('server_id') == p['server_id'], 'REVIEW_SCOPE_CHANGED')
    require(selected.get('identity', {}).get('mode') == 'select'
        and selected['identity'].get('agent_id') == p['agent_id']
        and selected.get('workspace', {}).get('mode') == 'select'
        and selected['workspace'].get('workspace_id') == p['workspace_id']
        and selected.get('credential') == {'mode': 'reuse_existing', 'expected_epoch': 2}, 'EXISTING_IDENTITY_EPOCH_TWO_REQUIRED')
    require(doc.get('selection', {}).get('operator_profile') == p['operator_profile']
        and doc['selection'].get('create_agent') is False
        and doc['selection'].get('agent') == p['agent_id'], 'HUMAN_OPERATOR_REUSE_REQUIRED')
    return review


def validate_bootstrap(doc, p):
    b = doc.get('bootstrap', {})
    require(all(b.get(k) == p[k] for k in ('server_id', 'agent_id', 'workspace_id'))
        and b.get('setup_run_id') == p['setup_request_id']
        and type(b.get('credential_epoch')) is int and b['credential_epoch'] == 2
        and doc.get('material_status') == 'reuse_existing'
        and not doc.get('material_delivery'), 'NO_NEW_MATERIAL_EPOCH_TWO_REQUIRED')


def validate_done(doc, p, draft):
    validate_review(doc, p, draft)
    validate_bootstrap(doc, p)
    binding = doc.get('result', {}).get('binding', {})
    scope = doc.get('remote_scope', {})
    final = doc.get('final_binding', {})
    require(doc.get('state') == 'done' and doc.get('result', {}).get('saved') is True
        and binding.get('state') == 'APPROVED'
        and all(binding.get(k) == p[k] for k in ('server_id', 'agent_id', 'workspace_id'))
        and binding.get('adapter_id') == 'claude_stream'
        and binding.get('candidate_ref') == draft['installation']['candidate_ref'], 'CANONICAL_DONE_BINDING_REQUIRED')
    from okto_nexus.application.terminal_connection import RemoteTerminalConnection
    require(set(scope) == set(RemoteTerminalConnection.SCOPE)
        and all(scope[k] == binding.get(k) for k in scope)
        and all(final.get(k) == binding.get(k) for k in ('server_id', 'agent_id', 'workspace_id', 'executor_id', 'binding_id'))
        and isinstance(final.get('proposal_id'), str)
        and final.get('finish_id') == final['proposal_id'] + '_setup', 'FINAL_FINISH_SCOPE_UNCONFIRMED')
    return scope


def canonical_commands(X):
    p = X.P
    common = [X.base.python, '-I', '-B', '-X', 'utf8', '-m']
    nexus = common + ['okto_nexus.adapters.inbound.cli.main', 'connect', '--operator-profile', p['operator_profile'],
        '--profile', p['profile'], '--home', p['paths']['operator_home'], '--json', '--no-chat']
    review = nexus + ['--remote-draft', p['draft']['path'], '--agent', p['agent_id'],
        '--workspace-id', p['workspace_id'], '--plan']
    host = common + ['okto_nexus_connector.cli.main', '--state-dir', p['paths']['connector_state'],
        'connect', '--setup-receipt', str(X.handoff_path), '--identity', p['agent_id'], '--no-start-at-login']
    return nexus, review, host


class Context:
    def __init__(self, path, expected, expected_review=None):
        require(Path(path).resolve() == HERE / 'binding02-plan.json' and sha(path) == expected, 'BINDING_PLAN_CHANGED')
        self.P = read_json(path)
        self.plan_sha, self.expected_review = expected, expected_review
        require(self.P['actions'] == list(ACTIONS) and self.P['setup_request_id'] == 'm1-sonnet-remote-setup-02'
            and self.P['profile'] == 'm1-sonnet-remote-recovery02', 'BINDING_SELECTION_CHANGED')
        for source in self.P['pins'].values():
            pin(source)
        lp = self.P['lifecycle_plan']
        self.base = RecoveryContext(pin(lp), lp['sha256'])
        self.PUBLIC, self.PRIVATE = self.base.PUBLIC, self.base.PRIVATE
        self.draft = read_json(pin(self.P['draft']))
        self.profile_path = Path(self.P['paths']['operator_home']) / 'terminal/profiles' / (self.P['profile'] + '.json')
        self.handoff_path = self.PUBLIC / 'recovery02-host-handoff.json'
        for name in ('server_home', 'operator_home', 'connector_state'):
            require(Path(self.P['paths'][name]).resolve() == Path(self.base.P['paths'][name]).resolve(), 'OWN_BINDING_PATH_CHANGED')

    def save(self, name, value):
        self.base.save(name, dict(value, binding_plan_sha256=self.plan_sha))

    def require_prior(self, action):
        value = read_json(self.PUBLIC / ('binding02-' + action + '-result.json'))
        require(value.get('binding_plan_sha256') == self.plan_sha, 'PREVIOUS_BINDING_SELECTION_CHANGED')
        return value

    def identity(self):
        from okto_nexus_connector.platform.paths import state_file
        from okto_nexus_connector.storage.state_store import StateStore
        state = StateStore(state_file(Path(self.P['paths']['connector_state']))).load()
        identity = state.identity_by_alias(self.P['agent_id'])
        require(identity is not None and identity.server_id == self.P['server_id']
            and identity.agent_id == self.P['agent_id'] and type(identity.credential_epoch) is int
            and identity.credential_epoch == 2 and identity.revoked is False, 'IMPORTED_IDENTITY_EPOCH_TWO_REQUIRED')
        return state

    def rotation(self):
        path = self.PUBLIC / 'rotation-import-result.json'
        value = read_json(path)
        require_rotation_before_review(value, self.P)
        require(value.get('rotation_plan_sha256') == self.P['rotation_plan']['sha256'], 'ROTATION_PLAN_BINDING_CHANGED')
        authority = Path(read_json(pin(self.P['rotation_plan']))['authorization_receipt'])
        require(value.get('authorization_receipt_sha256') == sha(authority), 'ROTATION_AUTHORITY_CHANGED')
        self.identity()
        return {'path': str(path), 'sha256': sha(path)}

    def retained_review(self):
        path = self.PUBLIC / 'recovery02-review.json'
        require(self.expected_review is not None and sha(path) == self.expected_review, 'ROOT_REVIEW_SELECTION_REQUIRED')
        value = read_json(path)
        require(value.get('binding_plan_sha256') == self.plan_sha and value['rotation_import_result_pin'] == self.rotation(), 'REVIEW_AUTHORITY_CHAIN_CHANGED')
        doc = read_json(self.profile_path)
        validate_review(doc, self.P, self.draft)
        require(doc['review_revision'] == value['review_revision'], 'REVIEW_REVISION_CHANGED')
        return doc, value

    def local_setup(self):
        state = self.identity()
        key = 'configure.' + self.P['server_id'] + '.' + self.P['agent_id'] + '.' + self.P['setup_request_id']
        return state.preferences.get(key)

    def invoke(self, action, argv, *, connector=False):
        require(action in ACTIONS, 'FINITE_BINDING_ACTION_REQUIRED')
        self.base.require_ready()
        self.save('binding02-' + action + '-reserved.json', {'argv': argv, 'provider_calls': 0, 'state': 'RESERVED_BEFORE_CLI'})
        stdout = self.PRIVATE / ('binding02-' + action + '.stdout')
        stderr = self.PRIVATE / ('binding02-' + action + '.stderr')
        with stdout.open('xb') as out, stderr.open('xb') as err:
            child = subprocess.Popen(argv, cwd=self.base.ROOT,
                env=self.base.connector_env() if connector else self.base.env(), stdin=subprocess.DEVNULL,
                stdout=out, stderr=err, creationflags=subprocess.CREATE_NO_WINDOW)
            # Same retained one-shot ownership as the qualified onboarding CLI;
            # no timeout kill, concurrent control, or automatic replay.
            child.communicate()
        self.save('binding02-' + action + '-returned.json', {'returncode': child.returncode,
            'stdout_sha256': sha(stdout), 'stderr_sha256': sha(stderr), 'provider_calls': 0})
        if connector:
            require(child.returncode == 0, 'HOST_CLI_UNCONFIRMED')
            return None
        value = read_json(stdout)
        require(child.returncode in (0, 3), 'OPERATOR_CLI_UNCONFIRMED')
        return value


def run(X, action):
    rotation = X.rotation()
    nexus, review_argv, host = canonical_commands(X)
    if action == 'review':
        require(not X.profile_path.exists(), 'NEW_RECOVERY_PROFILE_REQUIRED')
        X.invoke(action, review_argv)
        doc = read_json(X.profile_path)
        validate_review(doc, X.P, X.draft)
        require(doc['state'] == 'review', 'CANONICAL_REVIEW_REQUIRED')
        X.save('recovery02-review.json', {'profile': X.P['profile'], 'profile_sha256': sha(X.profile_path),
            'review_revision': doc['review_revision'], 'review': doc['remote_review'],
            'rotation_import_result_pin': rotation, 'current_credential_epoch': 2, 'provider_calls': 0})
        return
    doc, reviewed = X.retained_review()
    if action == 'bootstrap':
        require(doc['state'] == 'review' and sha(X.profile_path) == reviewed['profile_sha256']
            and not X.handoff_path.exists(), 'EXACT_UNAPPLIED_REVIEW_REQUIRED')
        value = X.invoke(action, nexus + ['--approve', doc['review_revision'], '--timeout', '1',
            '--setup-receipt-output', str(X.handoff_path)])
        doc = read_json(X.profile_path)
        validate_bootstrap(doc, X.P)
        require(value.get('state') == doc.get('state') == 'awaiting_host'
            and read_json(X.handoff_path) == doc.get('handoff'), 'BOOTSTRAP_HANDOFF_UNCONFIRMED')
    elif action == 'host-prepare':
        X.require_prior('bootstrap')
        require(doc['state'] == 'awaiting_host' and X.local_setup() is None, 'NEW_HOST_SETUP_REQUIRED')
        validate_bootstrap(doc, X.P)
        X.invoke(action, host, connector=True)
        local = X.local_setup()
        require(local is not None and local.get('stage') in ('apply', 'done')
            and local.get('remote_setup') == {'setup_run_id': X.P['setup_request_id'], 'review_revision': doc['review_revision']}, 'HOST_PREPARATION_UNCONFIRMED')
    elif action == 'operator-decide':
        X.require_prior('host-prepare')
        require(doc['state'] == 'awaiting_host', 'OPERATOR_MATERIALIZATION_STATE_REQUIRED')
        value = X.invoke(action, nexus + ['--timeout', '1'])
        doc = read_json(X.profile_path)
        require(doc['state'] in ('awaiting_finish', 'done')
            and value.get('state') in ('awaiting_finish', 'configured'), 'OPERATOR_BINDING_DECISION_UNCONFIRMED')
    elif action == 'host-finish':
        X.require_prior('operator-decide')
        require(doc['state'] in ('awaiting_finish', 'done'), 'OPERATOR_FINISH_STATE_REQUIRED')
        local = X.local_setup()
        require(local is not None and local.get('stage') in ('apply', 'done'), 'EXACT_HOST_APPLY_CHECKPOINT_REQUIRED')
        if local['stage'] != 'done':
            X.invoke(action, host, connector=True)
        local = X.local_setup()
        require(local.get('stage') == 'done' and local.get('result', {}).get('saved') is True,
            'HOST_FINISH_NOT_CONFIRMED')
    elif action == 'complete':
        X.require_prior('host-finish')
        require(X.local_setup().get('stage') == 'done', 'HOST_FINISH_REQUIRED')
        value = X.invoke(action, nexus + ['--timeout', '1'])
        doc = read_json(X.profile_path)
        scope = validate_done(doc, X.P, X.draft)
        require(value.get('state') == 'configured', 'CANONICAL_CONFIGURED_RESULT_REQUIRED')
        X.save('recovery02-profile-completed.json', {'profile_sha256': sha(X.profile_path), 'profile': X.P['profile'],
            'server_id': X.P['server_id'], 'remote_scope': scope, 'current_credential_epoch': 2,
            'rotation_import_result_pin': rotation,
            'canonical_review_pin': {'path': str(X.PUBLIC / 'recovery02-review.json'), 'sha256': X.expected_review},
            'profile_review_revision': doc['review_revision'], 'material_status': 'reuse_existing', 'provider_calls': 0})
    X.save('binding02-' + action + '-result.json', {'profile_state': read_json(X.profile_path)['state'],
        'current_credential_epoch': 2, 'rotation_import_result_pin': rotation, 'provider_calls': 0})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--plan', required=True)
    parser.add_argument('--expected-plan-sha256', required=True)
    parser.add_argument('--expected-review-sha256')
    parser.add_argument('action', choices=ACTIONS)
    args = parser.parse_args()
    X = Context(args.plan, args.expected_plan_sha256, args.expected_review_sha256)
    run(X, args.action)
    print(json.dumps({'status': 'COMPLETED', 'action': args.action, 'provider_calls': 0}))


if __name__ == '__main__':
    main()

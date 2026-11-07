"""Operator checkpoint and credential boundaries over a synthetic canonical peer.

Server SQLite/HTTP contracts and Connector integration have separate suites.
This peer never claims to qualify a provider, native service or real process.
"""
from copy import deepcopy
import io
import json
from types import SimpleNamespace

import pytest

from nexus_connector_core.connection_configuration import parse_portable_connection_configuration
from okto_nexus.application.project_preset import ORIGIN, configuration, identity_defaults
from okto_nexus.application.remote_setup_contract import build_review
from okto_nexus.application.remote_terminal_setup import RemoteProjectSetup
from okto_nexus.application.terminal_connection import ConnectionError
from okto_nexus.adapters.inbound.cli import connect, remote_setup_io, terminal_target


KEY = 'nxs_' + 'a' * 48


class Peer:
    base = 'https://example.invalid'

    def __init__(self):
        self.calls, self.saved, self.keys, self.exports = [], [], [], []
        self.review = self.bootstrap = None
        self.boots = self.decisions = 0
        self.host_ready = self.finished = self.approved = False
        self.lost = None
        self.changed = False
        self.bad_final = False
        self.proposal = dict(proposal_id='proposal-one', server_id='server-one', can_apply=True,
            approved_diff_hash='sha256:' + 'f' * 64, revision=1)

    def envelope(self, *, issuing=False):
        handoff = None if self.bootstrap is None else dict(format='okto.remote-setup-handoff', version=1,
            bootstrap=deepcopy(self.bootstrap), child_requests=self.review['child_requests'],
            draft_revision=self.review['draft_revision'], review_revision=self.review['review_revision'])
        final = (dict(server_id='server-one', agent_id='project-helper', workspace_id='workspace-one',
            executor_id='executor-one', binding_id='binding-one', proposal_id='proposal-one',
            finish_id='proposal-one_setup') if self.finished else None)
        if self.bad_final:
            final = {'api_key': KEY}
        return dict(state='committed' if self.finished else 'awaiting_host' if self.bootstrap else 'reviewed',
            review=deepcopy(self.review), bootstrap=deepcopy(self.bootstrap), handoff=handoff,
            material={'api_key': KEY} if issuing else None,
            material_status='issued_once' if issuing else 'unavailable' if self.bootstrap else 'not_issued',
            current_references='matching' if self.bootstrap else None, final_binding=final)

    def __call__(self, method, path, body=None):
        self.calls.append((method, path, deepcopy(body)))
        if path.endswith('/connections/me'):
            result = dict(agent_id='operator', server_id='server-one',
                capabilities=dict(remote_setup=dict(revision=1, draft_version=1, handoff_version=1)))
        elif path.endswith('remote-setup:review'):
            selected = dict(server_id='server-one', identity=body['identity'], workspace=body['workspace'],
                credential=dict(mode='issue_once', expected_epoch=0),
                baseline=dict(execution_revision=0, runtime_revision=0, defaults_revision=1,
                    binding_revision=None, endpoint_revision=None),
                native_decision_policy=dict(expected_revision='e' * 64, initialize=True),
                project_preset=dict(ORIGIN), identity_snapshot=identity_defaults(),
                remote_machine_policy='manual', previous_machines=[])
            self.review = build_review(body['draft'], selected)
            result = dict(state='reviewed', review=self.review)
        elif path.endswith('remote-setup:recover'):
            result = self.envelope()
        elif path.endswith('remote-setup:bootstrap'):
            self.boots += 1
            assert self.bootstrap is None
            self.bootstrap = body | dict(server_id='server-one', agent_id='project-helper',
                workspace_id='workspace-one', credential_epoch=1)
            result = self.envelope(issuing=True)
        elif path.endswith('remote-setup:materialization'):
            result = dict(state='requires_review' if self.changed else
                'review_matches' if self.host_ready else 'needs_canonical_metadata',
                changed_fields=['configuration'] if self.changed else [], missing_fields=[] if self.host_ready else ['proposal'],
                canonical_fields={}, proposal=deepcopy(self.proposal), approval_id='approval-one',
                final_binding=None, comparison_only=True, authority_granted=False, requires_authenticated_operator=True)
        elif path == '/api/v1/approvals/approval-one':
            result = dict(data=dict(approval_id='approval-one', agent_id='project-helper', workspace_id='workspace-one',
                action='execution.binding.authorize', request_payload={'proposal_id': 'proposal-one'},
                decision_detail=dict(proposal=deepcopy(self.proposal), proposal_state='PREPARED', expired=False),
                status='approved' if self.approved else 'pending', decided_by='operator' if self.approved else None,
                decided_at='now' if self.approved else None, justification=None,
                executed_result={'proposal_id': 'proposal-one'} if self.approved else None))
        elif path == '/api/v1/approvals/approval-one/decision':
            self.decisions += 1
            assert body == {'decision': 'approve'} and not self.approved
            self.approved = True
            result = dict(data=dict(approval_id='approval-one', status='approved', decided_by='operator',
                decided_at='now', executed_result={'proposal_id': 'proposal-one'}))
        elif path.endswith('/connections/bindings/binding-one'):
            result = dict(server_id='server-one', agent_id='project-helper', workspace_id='workspace-one',
                executor_id='executor-one', binding_id='binding-one', workspace_binding_id='wxb-one',
                adapter_id='codex_app_server', candidate_ref='nexus-install-v1:' + 'a' * 64,
                execution_location='remote', state='APPROVED')
        elif '/connections/setup/project-helper?' in path:
            result = dict(saved_configuration=True)
        else:
            pytest.fail('Unexpected synthetic request: ' + method + ' ' + path)
        if self.lost and path.endswith(self.lost):
            self.lost = None
            raise ConnectionError('OUTCOME_UNKNOWN', 'Synthetic response loss', possible_effect=True)
        return deepcopy(result)

    def flow(self, *, sink=True, save=None):
        return RemoteProjectSetup(self, save or (lambda value: self.saved.append(deepcopy(value))),
            origin=self.base, material_sink=self.keys.append if sink else None,
            handoff_sink=self.exports.append)


@pytest.fixture
def selection(tmp_path):
    draft = dict(format='okto.remote-setup-draft', version=1, setup_run_id='setup-one',
        server_origin=Peer.base, connector_id='connector-one', project_label='Project',
        agent_hint=None, workspace_hint=None, start_at_login=False,
        installation=dict(adapter_id='codex_app_server', candidate_ref='nexus-install-v1:' + 'a' * 64,
            inventory_revision=None),
        local_consent=dict(local_consent_id='consent-one', local_root_proof_digest=None, configuration_digest=None),
        configuration=parse_portable_connection_configuration(
            configuration(adapter_id='codex_app_server', project='', label='Project')))
    return dict(agent='project-helper', create_agent=True, display_name='Project helper', client=None,
        project=str(tmp_path), label='Local shortcut', workspace_id=None, binding_id=None,
        candidate_ref=None, provider_home=None, operator_profile='remote', remote_draft=draft)


def test_review_does_not_bootstrap_and_requires_the_exact_confirmation(selection):
    peer = Peer()
    flow = peer.flow()
    document = flow.review(selection)
    assert peer.boots == peer.decisions == 0 and peer.keys == []
    with pytest.raises(ConnectionError, match='Approve'):
        flow.apply(document, approval='wrong', timeout=0)
    assert peer.boots == peer.decisions == 0


def test_origin_conflict_is_refused_before_any_request(selection):
    peer = Peer()
    selection['remote_draft']['server_origin'] = 'https://another.invalid'
    with pytest.raises(ConnectionError) as failure:
        peer.flow().review(selection)
    assert failure.value.code == 'SERVER_ORIGIN_MISMATCH' and peer.calls == []


@pytest.mark.parametrize('capability', [None, {'revision': True, 'draft_version': 1, 'handoff_version': 1}],
    ids=['legacy', 'boolean_revision'])
def test_incompatible_server_is_refused_before_review_persistence(selection, capability):
    calls = []
    def call(method, path, body=None):
        calls.append((method, path))
        return dict(agent_id='operator', server_id='server-one', capabilities={'remote_setup': capability or {}})
    flow = RemoteProjectSetup(call, lambda _: pytest.fail('unexpected checkpoint'), origin=Peer.base)
    with pytest.raises(ConnectionError) as failure:
        flow.review(selection)
    assert failure.value.code == 'SERVER_UPGRADE_REQUIRED'
    assert len(calls) == 1 and calls[0][0] == 'GET'


def test_headless_creation_is_refused_before_bootstrap_and_can_resume_interactively(selection):
    peer = Peer()
    flow = peer.flow(sink=False)
    document = flow.review(selection)
    with pytest.raises(ConnectionError) as failure:
        flow.apply(document, approval=document['review_revision'], timeout=0)
    assert failure.value.code == 'INTERACTIVE_KEY_DELIVERY_REQUIRED'
    assert peer.boots == 0
    result = peer.flow().apply(deepcopy(peer.saved[-1]), timeout=0)
    assert result['state'] == 'awaiting_host' and peer.boots == 1 and peer.keys == [KEY]


def test_lost_initial_review_keeps_generated_identity_and_recovers_without_reposting(selection):
    peer = Peer()
    flow = peer.flow()
    peer.lost = 'remote-setup:review'
    with pytest.raises(ConnectionError):
        flow.review(selection)
    pending = deepcopy(peer.saved[-1])
    assert pending['state'] == 'review_submitted' and pending['selection']['agent'] == 'project-helper'
    recovered = flow.recover_review(pending)
    assert recovered['state'] == 'review' and recovered['review_revision'] == peer.review['review_revision']
    assert sum(path.endswith('remote-setup:review') for _, path, _ in peer.calls) == 1
    assert peer.boots == peer.decisions == 0


def test_lost_refreshed_review_preserves_bootstrap_and_requires_new_consent(selection):
    peer = Peer()
    flow = peer.flow()
    document = flow.review(selection)
    flow.apply(document, approval=document['review_revision'], timeout=0)
    original = deepcopy(peer.bootstrap)
    changed = deepcopy(selection)
    changed['remote_draft']['configuration']['tool_access'] = 'always_allow'
    peer.lost = 'remote-setup:review'
    with pytest.raises(ConnectionError):
        flow.review(changed, previous=deepcopy(peer.saved[-1]))
    recovered = flow.recover_review(deepcopy(peer.saved[-1]))
    assert recovered['state'] == 'review' and recovered['bootstrap'] == original
    assert recovered['review_revision'] != original['review_revision'] and 'approved_revision' not in recovered
    with pytest.raises(ConnectionError, match='Approve'):
        flow.apply(recovered, timeout=0)
    result = flow.apply(recovered, approval=recovered['review_revision'], timeout=0)
    assert result['bootstrap'] == original and result['handoff']['review_revision'] == recovered['review_revision']
    assert peer.boots == 1 and peer.keys == [KEY]


def test_one_shot_key_never_enters_results_checkpoints_or_exported_handoff(selection):
    peer = Peer()
    flow = peer.flow()
    document = flow.review(selection)
    result = flow.apply(document, approval=document['review_revision'], timeout=0)
    assert peer.keys == [KEY] and peer.boots == 1 and peer.decisions == 0
    assert KEY not in json.dumps([result, peer.saved, peer.exports])
    resumed = flow.apply(deepcopy(peer.saved[-1]), timeout=0)
    assert resumed['material_delivery'] == 'delivered_once' and resumed['material_status'] == 'unavailable'
    assert peer.keys == [KEY] and peer.boots == 1


def test_lost_bootstrap_response_recovers_references_without_reissue(selection):
    peer = Peer()
    flow = peer.flow()
    document = flow.review(selection)
    peer.lost = 'remote-setup:bootstrap'
    with pytest.raises(ConnectionError) as failure:
        flow.apply(document, approval=document['review_revision'], timeout=0)
    assert failure.value.possible_effect
    result = flow.apply(deepcopy(peer.saved[-1]), timeout=0)
    assert result['bootstrap'] == peer.bootstrap and result['material_status'] == 'unavailable'
    assert peer.boots == 1 and peer.keys == [] and KEY not in json.dumps(peer.saved)


def test_lost_decision_resumes_same_approval_then_only_host_finish_completes(selection):
    peer = Peer()
    flow = peer.flow()
    document = flow.review(selection)
    peer.host_ready, peer.lost = True, '/decision'
    with pytest.raises(ConnectionError):
        flow.apply(document, approval=document['review_revision'], timeout=0)
    assert peer.decisions == 1
    pending = flow.apply(deepcopy(peer.saved[-1]), timeout=0)
    assert pending['state'] == 'awaiting_finish' and peer.decisions == peer.boots == 1
    peer.finished = True
    done = flow.apply(deepcopy(peer.saved[-1]), timeout=0)
    assert done['state'] == 'configured' and done['work_state'] == 'not_submitted'
    before = len(peer.calls)
    assert flow.apply(deepcopy(peer.saved[-1])) == done
    assert all(method == 'GET' for method, _, _ in peer.calls[before:])
    assert not any(path.endswith('bindings:apply') for _, path, _ in peer.calls)


def test_changed_material_never_approves_and_keeps_the_original_bootstrap(selection):
    peer = Peer()
    flow = peer.flow()
    document = flow.review(selection)
    peer.changed = peer.host_ready = True
    result = flow.apply(document, approval=document['review_revision'], timeout=0)
    assert result['state'] == 'review_required' and result['changed_fields'] == ['configuration']
    assert peer.decisions == 0 and peer.boots == 1


def test_unexpected_secret_field_in_receipt_is_refused_without_checkpointing_it(selection):
    peer = Peer()
    flow = peer.flow()
    document = flow.review(selection)
    peer.bad_final = True
    with pytest.raises(ConnectionError) as failure:
        flow.apply(document, approval=document['review_revision'], timeout=0)
    assert failure.value.code == 'RECEIPT_UNCONFIRMED'
    assert peer.boots == 0 and KEY not in json.dumps(peer.saved)


def test_checkpoint_failure_after_bootstrap_reports_uncertainty_without_reissue(selection):
    peer = Peer()
    def save(value):
        if value.get('bootstrap'):
            raise OSError('synthetic disk failure')
        peer.saved.append(deepcopy(value))
    flow = peer.flow(save=save)
    document = flow.review(selection)
    with pytest.raises(ConnectionError) as failure:
        flow.apply(document, approval=document['review_revision'], timeout=0)
    assert failure.value.code == 'CHECKPOINT_UNCONFIRMED' and failure.value.possible_effect
    recovered = peer.flow().apply(deepcopy(peer.saved[-1]), timeout=0)
    assert recovered['bootstrap'] == peer.bootstrap and peer.boots == 1 and peer.keys == []


def test_cli_plan_and_headless_refusal_do_not_leak_material_or_start_local_service(selection, tmp_path, monkeypatch, capsys):
    peer = Peer()
    home = tmp_path / 'home'
    target = SimpleNamespace(adapter=SimpleNamespace(home=home), operator_profile='remote', operator_http=peer,
        inspect=lambda: {'state': 'ready'}, ensure_running=lambda **_: {'state': 'ready'})
    monkeypatch.setattr(terminal_target, 'resolve_terminal_target', lambda *args: target)
    draft_path = tmp_path / 'draft.json'
    draft_path.write_text(json.dumps(selection['remote_draft']), encoding='utf-8')
    args = ['--operator-profile', 'remote', '--profile', 'project', '--new-agent', 'project-helper',
        '--project', str(tmp_path), '--remote-draft', str(draft_path), '--json', '--timeout', '0.01']
    assert connect.run_connect(args + ['--plan']) == 0
    review = json.loads(capsys.readouterr().out)
    assert review['kind'] == RemoteProjectSetup.KIND and peer.boots == 0
    assert connect.run_connect(args + ['--approve', review['review_revision']]) == 3
    failure = json.loads(capsys.readouterr().out)
    assert failure['code'] == 'INTERACTIVE_KEY_DELIVERY_REQUIRED' and peer.boots == 0
    assert KEY not in (home / 'terminal/profiles/project.json').read_text(encoding='utf-8')


def test_material_delivery_requires_tty_and_is_separate_from_public_stdout(monkeypatch):
    class TTY(io.StringIO):
        def isatty(self):
            return True
    streams = [TTY(), TTY(), TTY()]
    for name, stream in zip(('stdin', 'stdout', 'stderr'), streams):
        monkeypatch.setattr(remote_setup_io.sys, name, stream)
    assert remote_setup_io.material_sink(True) is None
    remote_setup_io.material_sink(False)(KEY)
    assert KEY in streams[2].getvalue() and KEY not in streams[1].getvalue()
    monkeypatch.setattr(remote_setup_io.sys, 'stdout', io.StringIO())
    assert remote_setup_io.material_sink(False) is None


@pytest.mark.parametrize('flag', ['--start-at-login', '--no-start-at-login'])
def test_operator_startup_flags_never_override_or_silently_ignore_host_review(flag, selection, tmp_path, monkeypatch, capsys):
    peer = Peer()
    target = SimpleNamespace(adapter=SimpleNamespace(home=tmp_path / 'home'), operator_profile='remote',
        operator_http=peer, inspect=lambda: {'state': 'ready'}, ensure_running=lambda **_: {'state': 'ready'})
    monkeypatch.setattr(terminal_target, 'resolve_terminal_target', lambda *args: target)
    draft = deepcopy(selection['remote_draft'])
    draft['start_at_login'] = True
    path = tmp_path / 'host-startup-draft.json'
    path.write_text(json.dumps(draft), encoding='utf-8')
    code = connect.run_connect(['--operator-profile', 'remote', '--remote-draft', str(path), '--profile', 'project',
        '--project', str(tmp_path), '--plan', '--json', flag])
    assert code == 3
    assert json.loads(capsys.readouterr().out)['code'] == 'REMOTE_STARTUP_NOT_LOCAL'
    assert peer.calls == peer.saved == []


def test_handoff_output_refuses_an_unrelated_file_before_any_write(tmp_path):
    path = tmp_path / 'existing.json'
    original = b'{"keep":"user data"}'
    path.write_bytes(original)
    with pytest.raises(ConnectionError) as failure:
        remote_setup_io.handoff_sink(path, 'setup-one', as_json=True)
    assert failure.value.code == 'HANDOFF_DESTINATION_CONFLICT' and path.read_bytes() == original


def test_local_project_revision_keeps_the_committed_workspace(selection, tmp_path, capsys):
    peer = Peer()
    flow = peer.flow()
    original = flow.review(selection)
    flow.apply(original, approval=original['review_revision'], timeout=0)
    updated = deepcopy(selection['remote_draft'])
    updated['project_label'] = 'Another local project label'
    updated['installation']['adapter_id'] = 'claude_stream'
    updated['configuration']['adapter_id'] = 'claude_stream'
    path = tmp_path / 'updated-draft.json'
    path.write_text(json.dumps(updated), encoding='utf-8')
    args = SimpleNamespace(agent=None, client=None, workspace_id=None, binding_id=None,
        candidate_ref=None, provider_home=None, new_agent=None, name=None, project=None,
        profile='project', remote_draft=path, review_current=True)
    changed = connect.saved_selection(original, args, str(tmp_path))
    assert changed['client'] == 'claude'
    revised = flow.review(changed, previous=original)
    assert revised['remote_review']['draft'] == updated
    assert revised['remote_review']['selection']['workspace'] == original['remote_review']['selection']['workspace']
    assert revised['bootstrap'] == original['bootstrap'] and peer.boots == 1
    assert revised['state'] == 'review' and 'approved_revision' not in revised
    remote_setup_io.display_review(revised)
    output = capsys.readouterr().out
    assert 'Identity: reuse committed project-helper' in output and 'Workspace: workspace-one' in output
    assert 'display its canonical key once' not in output


def test_human_review_displays_material_permissions_configuration_and_origin(selection, capsys):
    peer = Peer()
    document = peer.flow().review(selection)
    remote_setup_io.display_review(document)
    output = capsys.readouterr().out
    assert Peer.base in output and selection['remote_draft']['installation']['candidate_ref'] in output
    assert 'Tool access: "ask"' in output and 'Execution authorization:' in output
    assert 'Coordination limits:' in output and 'send direct' in output
    assert KEY not in output


@pytest.mark.parametrize('delivered', [False, True])
def test_human_pending_state_distinguishes_lost_material_from_previous_delivery(delivered, capsys):
    result = dict(state='awaiting_host', setup_run_id='setup-one', agent_id='project-helper',
        material_status='unavailable')
    if delivered:
        result['material_delivery'] = 'delivered_once'
    connect._display(result, False)
    output = capsys.readouterr().out
    assert ('key already received' in output) is delivered
    assert ('did not confirm receiving' in output) is not delivered


@pytest.mark.parametrize('stage', ['bootstrap_submitted', 'decision_submitted', 'review'])
def test_expired_login_preserves_known_uncertainty_without_reposting(stage, selection, tmp_path, monkeypatch, capsys):
    peer = Peer()
    document = peer.flow().review(selection)
    document['state'] = stage
    peer.calls.clear()
    home = tmp_path / 'operator-home'
    path = home / 'terminal/profiles/project.json'
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(document), encoding='utf-8')
    original = path.read_bytes()
    def expired(**kwargs):
        raise ConnectionError('OPERATOR_LOGIN_REQUIRED', 'Sign in again.')
    target = SimpleNamespace(adapter=SimpleNamespace(home=home), operator_profile='remote',
        operator_http=peer, ensure_running=expired)
    monkeypatch.setattr(terminal_target, 'resolve_terminal_target', lambda *args: target)
    assert connect.run_connect(['--profile', 'project', '--project', str(tmp_path), '--json']) == 3
    result = json.loads(capsys.readouterr().out)
    uncertain = stage != 'review'
    assert result['code'] == 'OPERATOR_LOGIN_REQUIRED' and result['possible_effect'] is uncertain
    assert result['state'] == ('unconfirmed' if uncertain else 'refused')
    assert peer.calls == [] and path.read_bytes() == original

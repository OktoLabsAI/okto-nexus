"""Lost grant issuance stays uncertain while operator authentication is unavailable."""
import json
from types import SimpleNamespace

import pytest

from okto_nexus.adapters.inbound.cli import terminal_target, work
from okto_nexus.adapters.outbound.operator_client import RemoteOperatorHTTP
from okto_nexus.application.terminal_connection import ConnectionError, document_revision
from okto_nexus.application.terminal_work import TerminalWork


def checkpoint(state):
    review = {
        'scope': {'server_id': 'server-one', 'binding_id': 'binding-one', 'agent_id': 'agent-one'},
        'request': {'binding_id': 'binding-one', 'client_request_id': 'retained-authorization'},
        'can_issue': True,
    }
    return {'format': 1, 'authorization': {
        'state': state, 'review': review, 'review_revision': document_revision(review),
    }}


def connection():
    return {'state': 'done', 'server_id': 'server-one',
            'selection': {'agent': 'agent-one', 'operator_profile': 'human'},
            'result': {'binding': {'binding_id': 'binding-one'}}}


@pytest.mark.parametrize('state', ['review', 'submitted', 'done'])
def test_authentication_failure_keeps_only_unresolved_issuance_uncertain(state):
    original = checkpoint(state)
    calls, saved = [], []

    def unavailable(method, path, body=None):
        calls.append((method, path, body))
        raise ConnectionError('OPERATOR_LOGIN_REQUIRED', 'Sign in again.')

    flow = TerminalWork(unavailable, saved.append, connection(), original)
    with pytest.raises(ConnectionError) as failure:
        flow.authorize(approval=original['authorization']['review_revision'])
    assert failure.value.code == 'OPERATOR_LOGIN_REQUIRED'
    assert failure.value.possible_effect is (state == 'submitted')
    assert len(calls) == 1 and calls[0][0] == 'GET'
    assert saved == [] and flow.document == original


@pytest.mark.parametrize('state', ['submitted', 'done'])
def test_recovery_transport_failure_does_not_erase_prior_uncertainty_or_reissue(state):
    original = checkpoint(state)
    calls, saved = [], []

    def interrupted(method, path, body=None):
        calls.append((method, path, body))
        if method == 'GET':
            return {'server_id': 'server-one'}
        assert path.endswith('authorizations:recover')
        raise ConnectionError('TRANSPORT_UNAVAILABLE', 'Recovery is unavailable.')

    flow = TerminalWork(interrupted, saved.append, connection(), original)
    with pytest.raises(ConnectionError) as failure:
        flow.authorization_review() if state == 'submitted' else flow.authorize()
    assert failure.value.possible_effect is (state == 'submitted')
    assert [call[0] for call in calls] == ['GET', 'POST']
    assert saved == [] and flow.document == original


@pytest.mark.parametrize('state', ['submitted', 'done'])
def test_real_post_transport_uncertainty_does_not_reopen_a_confirmed_issuance(state):
    wire = RemoteOperatorHTTP('https://nexus.example')
    calls, saved = [], []

    def timeout(request, **kwargs):
        calls.append((request.method, request.full_url))
        raise TimeoutError('Synthetic receipt timeout')

    wire.opener = SimpleNamespace(open=timeout)

    def call(method, path, body=None):
        if method == 'GET':
            return {'server_id': 'server-one'}
        return wire(method, path, body)

    original = checkpoint(state)
    flow = TerminalWork(call, saved.append, connection(), original)
    with pytest.raises(ConnectionError) as failure:
        flow.authorize()
    assert failure.value.code == 'OUTCOME_UNKNOWN'
    assert failure.value.possible_effect is (state == 'submitted')
    assert len(calls) == 1 and calls[0][1].endswith('authorizations:recover')
    assert saved == [] and flow.document == original


@pytest.mark.parametrize('state', ['review', 'submitted', 'done'])
@pytest.mark.parametrize('failure_kind', ['login', 'vault'])
@pytest.mark.parametrize('phase', ['target', 'inspect'])
def test_cli_auth_failure_preserves_durable_unknown_issuance_before_flow_opens(
    state, failure_kind, phase, tmp_path, monkeypatch, capsys,
):
    profile_path = tmp_path / 'terminal/profiles/project.json'
    profile_path.parent.mkdir(parents=True)
    profile_path.write_text(json.dumps(connection()), encoding='utf-8')
    work_path = tmp_path / 'terminal/work/project.json'
    work_path.parent.mkdir(parents=True)
    original = checkpoint(state)
    work_path.write_text(json.dumps(original), encoding='utf-8')
    before = work_path.read_bytes()
    calls = []

    def unavailable(*args):
        calls.append(phase)
        if failure_kind == 'login':
            raise ConnectionError('OPERATOR_LOGIN_REQUIRED', 'Sign in again.')
        raise OSError('Vault unavailable')

    service = SimpleNamespace(adapter=SimpleNamespace(home=tmp_path), inspect=unavailable)
    monkeypatch.setattr(terminal_target, 'RemoteTarget', unavailable if phase == 'target' else lambda *args: service)
    assert work.run_work(['authorize', '--profile', 'project', '--home', str(tmp_path), '--json']) == 3
    result = json.loads(capsys.readouterr().out)
    assert result['state'] == ('unconfirmed' if state == 'submitted' else 'refused')
    assert result['possible_effect'] is (state == 'submitted')
    assert calls == [phase] and work_path.read_bytes() == before

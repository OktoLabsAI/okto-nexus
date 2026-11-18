"""Session catalog commands use the public ID and canonical binding."""

import json
from contextlib import contextmanager
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest

from okto_nexus.adapters.inbound.cli import session
from okto_nexus.adapters.inbound.cli.main import main

BINDING = {'server_id': 'server', 'executor_id': 'executor', 'binding_id': 'binding', 'agent_id': 'agent',
               'workspace_id': 'workspace', 'workspace_binding_id': 'realization', 'endpoint_id': 'endpoint'}


class Catalog:
    def __init__(self, *, base='http://127.0.0.1:4000', drift=False, two_live=False):
        self.base = base
        self.drift = drift
        self.two_live = two_live
        self.routes = []

    def __call__(self, method, url, body=None):
        assert method == 'GET' and body is None
        path = urlsplit(url).path
        assert path.startswith('/api/v1/runtime-management/')
        path = path.removeprefix('/api/v1/runtime-management')
        query = parse_qs(urlsplit(url).query, keep_blank_values=True)
        self.routes.append(path)
        if path == '/connections/me':
            return {'server_id': 'server', 'agent_id': 'operator'}
        if path == '/agents/operator/executors':
            return {'items': [{'kind': 'embedded', 'executor_id': 'executor'}], 'has_more': False}
        if path == '/connections/project-context':
            return {'version': 1, 'server_id': 'server', 'executor_id': 'executor', 'workspace_id': None,
                        'project_root': query['project_root'][0], 'project_revision': 'sha256:' + 'a' * 64,
                        'mapped_workspace_ids': ['workspace']}
        if path == '/connections/public-ids':
            assert query['workspace_id'] == ['workspace']
            return {'version': 1, 'capabilities': {'public_connection': 1}, 'server_id': 'server',
                        'scope': {'workspace_id': 'workspace'}, 'revision': 'b' * 64, 'total': 1,
                        'total_is_exact': True, 'has_more': False, 'next_cursor': None,
                        'items': [{'connect_id': 'reviewer', 'state': 'bound', 'workspace_id': 'workspace',
                                    'canonical_ref': BINDING}]}
        if path == '/connections/bindings/binding':
            return BINDING
        if path == '/runtime/sessions':
            assert (query['executor_id'], query['binding_id'], query['agent_id']) == (
                ['executor'], ['binding'], ['agent'])
            first = query['after_session_id'] == ['']
            ident = 'session-a' if first else 'session-b'
            scope = BINDING | {'session_id': ident}
            if not first and self.drift:
                scope['workspace_binding_id'] = 'other-realization'
            live = first or self.two_live
            return {'has_more': first, 'next_after_session_id': ident,
                    'sessions': [{'scope': scope, 'lifecycle_state': 'READY' if live else 'CLOSED',
                                  'lease_state': 'ACTIVE' if live else 'CLOSED', 'control_available': live}]}
        if path in ('/runtime/sessions/session-a', '/runtime/sessions/session-b'):
            assert query['executor_id'] == ['executor']
            ident = path.split('/')[-1]
            return {'scope': BINDING | {'session_id': ident, 'session_owner_generation': 7},
                    'control_available': ident == 'session-a'}
        pytest.fail(f'Unexpected route {path}')


@pytest.mark.parametrize('remote', [False, True])
def test_list_resolves_exact_id_and_all_pages(remote, monkeypatch, capsys):
    catalog = Catalog(base='https://nexus.example' if remote else 'http://127.0.0.1:4000')
    service = SimpleNamespace(operator_http=catalog, inspect=lambda: {'state': 'ready', 'server_id': 'server'})
    monkeypatch.setattr(session, 'resolve_terminal_target', lambda *args: service)
    args = ['--workspace-id', 'workspace', '--operator-profile', 'user'] if remote else []
    assert main(['session', 'list', '--id', 'reviewer', '--json', *args]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['complete'] is True and result['scope']['workspace_binding_id'] == 'realization'
    assert [(row['scope']['session_id'], row['lifecycle_state']) for row in result['sessions']] == [
        ('session-a', 'READY'), ('session-b', 'CLOSED')]
    assert ('/connections/project-context' in catalog.routes) is not remote
    assert catalog.routes.count('/runtime/sessions') == 2


def test_list_fails_closed_on_later_scope_change(monkeypatch, capsys):
    catalog = Catalog(drift=True)
    service = SimpleNamespace(operator_http=catalog, inspect=lambda: {'state': 'ready', 'server_id': 'server'})
    monkeypatch.setattr(session, 'resolve_terminal_target', lambda *args: service)
    assert main(['session', 'list', '--id', 'reviewer', '--json']) == 3
    result = json.loads(capsys.readouterr().out)
    assert result['code'] == 'WORK_SCOPE_CHANGED'
    assert 'sessions' not in result


def test_json_attach_requires_choice_and_never_opens_terminal(monkeypatch, capsys):
    catalog = Catalog(two_live=True)
    service = SimpleNamespace(operator_http=catalog, inspect=lambda: {'state': 'ready', 'server_id': 'server'})
    monkeypatch.setattr(session, 'resolve_terminal_target', lambda *args: service)
    assert main(['session', 'attach', '--id', 'reviewer', '--json']) == 3
    result = json.loads(capsys.readouterr().out)
    assert result['code'] == 'SESSION_SELECTION_REQUIRED'
    assert result['choices'] == ['session-a', 'session-b']
    assert catalog.routes.count('/runtime/sessions') == 2
    assert main(['session', 'attach', '--id', 'reviewer', '--session-id', 'session-b', '--json']) == 3
    assert json.loads(capsys.readouterr().out)['code'] == 'SESSION_UNAVAILABLE'


def test_tty_picker_rechecks_selected_session_instead_of_switching_targets(monkeypatch, capsys):
    catalog = Catalog(two_live=True)
    tty = SimpleNamespace(isatty=lambda: True)
    service = SimpleNamespace(operator_http=catalog, inspect=lambda: {'state': 'ready', 'server_id': 'server'})
    monkeypatch.setattr('builtins.input', lambda prompt: '2')
    monkeypatch.setattr(session, 'sys', SimpleNamespace(stdin=tty, stdout=tty))
    monkeypatch.setattr(session, 'resolve_terminal_target', lambda *args: service)
    assert main(['session', 'attach', '--id', 'reviewer']) == 3
    assert catalog.routes[-1] == '/runtime/sessions/session-b'
    assert 'This exact session is unavailable' in capsys.readouterr().out


def test_exact_attach_uses_reviewed_generation_and_leaves_checkout_untouched(monkeypatch, capsys):
    catalog = Catalog()
    catalog.token = 'synthetic-cookie'
    service = SimpleNamespace(operator_http=catalog, inspect=lambda: {'state': 'ready', 'server_id': 'server'})
    tty = SimpleNamespace(isatty=lambda: True)
    monkeypatch.setattr(session, 'sys', SimpleNamespace(stdin=tty, stdout=tty))
    monkeypatch.setattr(session, 'resolve_terminal_target', lambda *args: service)
    monkeypatch.setattr(session, 'select_viewer', lambda executable: 'reviewed-executable')
    collected = []
    scope = {name: value for name, value in BINDING.items() if name != 'endpoint_id'} | {'session_id': 'session-a'}

    def review(call, **kwargs):
        assert call is catalog
        assert kwargs == {'scope': scope, 'expected_session_generation': 7}
        return 'fresh-revision'

    @contextmanager
    def attach(call, *, client_intent_id, **kwargs):
        assert call is catalog and client_intent_id.startswith('viewer_')
        assert kwargs == {'scope': scope, 'expected_session_generation': 7, 'capability_revision': 'fresh-revision'}
        collected.append('attach')
        yield SimpleNamespace(attachment_id='att_fixture')
        collected.append('detach')

    monkeypatch.setattr(session, 'review_local_presentation', review)
    monkeypatch.setattr(session, 'open_local_presentation', attach)
    monkeypatch.setattr(session, 'present_codex', lambda link, exe: collected.append((link.attachment_id, exe)))
    assert main(['session', 'attach', '--id', 'reviewer', '--session-id', 'session-a']) == 0
    assert '/runtime/sessions' not in catalog.routes
    assert collected == ['attach', ('att_fixture', 'reviewed-executable'), 'detach']
    output = capsys.readouterr().out
    assert 'Session session-a' in output and 'Viewer detached' in output and catalog.token not in output


@pytest.mark.parametrize(('stage', 'successor_state', 'exit_code'), [
    ('SUBMITTED', None, 0),
    ('SUBMISSION_STARTED', 'OPEN_PENDING', 0),
    ('SUBMISSION_STARTED', 'CLOSED', 1),
    ('OUTCOME_UNKNOWN', None, 1),
])
def test_saved_resume_recovers_its_exact_intent_after_unknown_submission(
        monkeypatch, capsys, stage, successor_state, exit_code):
    class SavedCatalog(Catalog):
        token = 'synthetic-cookie'
        resolution = None
        operation = None
        submissions = 0

        def __call__(self, method, url, body=None):
            path = urlsplit(url).path
            if path.startswith(session.PREFIX + '/runtime/intents/'):
                if self.resolution is None:
                    raise session.ConnectionError('NOT_FOUND', 'Missing intent.', http_status=404)
                assert path.endswith('/' + self.resolution['client_intent_id'])
                return {'resolution': self.resolution, 'operation': self.operation}
            if path == session.PREFIX + '/runtime/intents:resolve':
                assert method == 'POST'
                assert body['intent'] == 'runtime.resume_saved' and body['session_id'] == 'session-b'
                assert body['source_session_generation'] == 7 and 'text' not in body and 'new_session' not in body
                self.resolution = {'client_intent_id': body['client_intent_id'], 'operation_id': 'saved-open',
                    'resolution_revision': 1, 'intent_hash': 'sha256:' + 'a' * 64,
                    'saved_resume': {'source_session_id': 'session-b', 'source_session_generation': 7},
                    'scope': {key: value for key, value in BINDING.items() if key != 'endpoint_id'} |
                             {'session_id': 'successor', 'session_owner_generation': 1}}
                return self.resolution
            if path == session.PREFIX + '/runtime/operations':
                assert method == 'POST' and body['operation_id'] == 'saved-open'
                self.submissions += 1
                self.operation = {'operation_id': 'saved-open', 'scope': self.resolution['scope'], 'action': 'runtime.open',
                                  'executor_stage': stage}
                raise session.ConnectionError('OUTCOME_UNKNOWN', 'Simulated lost response.', possible_effect=True)
            if path == session.PREFIX + '/runtime/sessions/successor':
                assert method == 'GET' and parse_qs(urlsplit(url).query) == {'executor_id': ['executor']}
                assert stage == 'SUBMISSION_STARTED' and successor_state is not None
                return {'scope': self.resolution['scope'], 'lifecycle_state': successor_state,
                        'lease_state': 'CLOSED' if successor_state == 'CLOSED' else 'ACTIVE'}
            return super().__call__(method, url, body)

    catalog = SavedCatalog()
    service = SimpleNamespace(operator_http=catalog, inspect=lambda: {'state': 'ready', 'server_id': 'server'})
    monkeypatch.setattr(session, 'resolve_terminal_target', lambda *args: service)
    args = ['session', 'resume', '--id', 'reviewer', '--session-id', 'session-b', '--json']
    assert main(args) != 0
    assert json.loads(capsys.readouterr().out)['code'] == 'OUTCOME_UNKNOWN'
    assert main(args) == exit_code
    result = json.loads(capsys.readouterr().out)
    assert result['session_id'] == 'successor' and result['source_session_id'] == 'session-b'
    assert result['operation_id'] == 'saved-open' and result['executor_stage'] == stage
    if exit_code:
        assert result['state'] == 'resume_unconfirmed' and 'outcome is unconfirmed' in result['message']
    else:
        assert result['state'] == 'resume_requested'
    assert catalog.submissions == 1 and '/runtime/sessions' not in catalog.routes

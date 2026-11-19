"""Session catalog commands use the public ID and canonical binding."""

import json
import os
from contextlib import contextmanager
from io import StringIO
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest

from okto_nexus.adapters.inbound.cli import session
from okto_nexus.adapters.inbound.cli.main import main
from okto_nexus.application.terminal_connection import ConnectionError

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
    assert 'Press Ctrl+] to detach' in output and 'Session session-a' in output and 'Viewer detached' in output
    assert catalog.token not in output


def test_pi_attachment_selects_the_ticketed_transcript_and_detaches_locally(monkeypatch, capsys):
    call = Catalog()
    call.token = 'synthetic-cookie'
    binding = BINDING | {'adapter_id': 'pi_rpc'}
    reviewed = []

    def review(api, **selection):
        assert api is call and selection['expected_session_generation'] == 7
        assert selection['presentation'] == 'pi' and selection['scope']['session_id'] == 'session-a'
        return 'pi-revision'

    @contextmanager
    def attach(api, **selection):
        assert api is call and selection['capability_revision'] == 'pi-revision'
        assert selection['scope']['session_id'] == 'session-a' and 'pi_viewport' in selection
        try:
            yield SimpleNamespace(attachment_id='pi-attachment')
        finally:
            reviewed.append('socket closed')

    monkeypatch.setattr(session, 'review_local_presentation', review)
    monkeypatch.setattr(session, 'open_local_presentation', attach)
    monkeypatch.setattr(session, '_show_pi_transcript', lambda link: reviewed.append(link.attachment_id))
    result = session.attach_session(call, binding, session_id='session-a', interactive=True)
    assert result['attach_strategy'] == 'pi_local_read' and result['status'] == 'detached'
    assert reviewed == ['pi-attachment', 'socket closed']
    assert 'Ctrl+C detaches' in capsys.readouterr().out
    with pytest.raises(ConnectionError, match='reviewed Windows terminal'):
        session.attach_session(call, binding, session_id='session-a', interactive=True, viewer_executable='another-viewer')


def test_pi_writer_confirms_transfer_and_opens_the_native_editor(monkeypatch):
    call = Catalog()
    call.token = 'synthetic-cookie'
    binding = BINDING | {'adapter_id': 'pi_rpc'}
    writer = SimpleNamespace(capability_revision='pi-writer', occupied=True)
    calls = []

    def review(api, **selection):
        assert api is call and selection['presentation'] == 'pi' and selection['write'] is True
        return writer

    @contextmanager
    def attach(api, **selection):
        assert api is call and selection['capability_revision'] == 'pi-writer'
        assert selection['writer'] is writer and selection['pi_editor'] is True
        yield SimpleNamespace(attachment_id='writer')

    monkeypatch.setattr(session, 'sys', SimpleNamespace(platform='win32'))
    monkeypatch.setattr(session, 'review_local_presentation', review)
    monkeypatch.setattr(session, 'open_local_presentation', attach)
    monkeypatch.setattr(session, 'show_pi_editor', lambda link, recover: calls.append(link.attachment_id))
    monkeypatch.setattr('builtins.input', lambda _: 'n')
    assert session.attach_session(call, binding, session_id='session-a', interactive=True, write=True) is None
    assert calls == []
    monkeypatch.setattr('builtins.input', lambda _: 'y')
    result = session.attach_session(call, binding, session_id='session-a', interactive=True, write=True)
    assert result['attach_strategy'] == 'pi_local_write'
    assert calls == ['writer']


def test_pi_console_decodes_split_paste_and_keeps_detach_local():
    from okto_nexus.adapters.inbound.cli.pi_viewer_terminal import _PiKeys

    keys = _PiKeys()
    assert keys.feed('\x1b[20') == []
    assert keys.feed('0~Revisão\r\nsegunda\x03\x1b[20') == []
    assert keys.feed('1~\x1b[D\x7f\r\x03') == [
        ('insert', 'Revisão\nsegunda'), ('left', None), ('backspace', None), ('enter', None), ('detach', None),
    ]
    assert keys.feed('\x1b[13;28;13;1;16;1_\x1b[221;27;29;1;8;1_') == [('newline', None), ('detach', None)]


def test_pi_receipt_recovers_the_original_presenter_intent(monkeypatch, capsys):
    intent = 'pi_input_' + 'a' * 32

    class PiReceipts(Catalog):
        token = 'synthetic-cookie'

        def __call__(self, method, url, body=None):
            expected = '/api/v1/runtime-management/runtime/sessions/session-a/presenter/inputs/receipt'
            if urlsplit(url).path != expected:
                return super().__call__(method, url, body)
            assert method == 'GET' and body is None
            query = parse_qs(urlsplit(url).query)
            assert query['client_intent_id'] == [intent]
            assert query['expected_session_generation'] == ['7']
            scope = {key: BINDING[key] for key in BINDING if key != 'endpoint_id'} | {'session_id': 'session-a'}
            assert all(query[key] == [value] for key, value in scope.items() if key != 'session_id')
            return {'scope': scope, 'session_owner_generation': 7, 'reorientation': False,
                    'input_id': 'input-original', 'status': 'QUEUED'}

    service = SimpleNamespace(operator_http=PiReceipts(), inspect=lambda: {'state': 'ready', 'server_id': 'server'})
    monkeypatch.setattr(session, 'resolve_terminal_target', lambda *args: service)
    assert main(['session', 'receipt', '--id', 'reviewer', '--session-id', 'session-a',
                 '--owner-generation', '7', '--intent', intent, '--json']) == 0
    assert json.loads(capsys.readouterr().out)['receipt']['input_id'] == 'input-original'


def test_pi_terminal_keeps_split_utf8_and_recovers_style_after_ctrl_c(monkeypatch):
    output = StringIO()
    monkeypatch.setattr(session, 'sys', SimpleNamespace(platform='linux', stdout=output))
    pieces = iter([b'Pi \xe2', b'\x9c\x93'])

    def next_frame():
        value = next(pieces, None)
        if value is None:
            raise KeyboardInterrupt
        return value

    session._show_pi_transcript(SimpleNamespace(read_pi_output=next_frame))
    assert output.getvalue() == 'Pi ✓\x1b[0m\x1b[?25h\n'


@pytest.mark.parametrize('http_status', [404, 405])
def test_missing_server_features_refuse_before_viewer_selection_or_input(monkeypatch, http_status):
    class OlderServer(Catalog):
        token = 'fixture-cookie'
        server_id = 'server'

        def __call__(self, method, url, body=None):
            path = urlsplit(url).path
            if path.endswith(('/attachments:review', '/commands')):
                raise ConnectionError('REQUEST_REFUSED', 'Unavailable route', http_status=http_status)
            return super().__call__(method, url, body)

    api = OlderServer()
    monkeypatch.setattr(session, 'select_viewer', lambda *_: pytest.fail('Unexpected executable selection'))
    with pytest.raises(ConnectionError, match='does not offer native presentation') as attach:
        session.attach_session(api, BINDING, session_id='session-a', interactive=True, write=True)
    assert attach.value.code == 'PRESENTATION_UNAVAILABLE' and not attach.value.possible_effect

    def no_input(*_):
        pytest.fail('Unexpected confirmation or input')

    with pytest.raises(ConnectionError, match='does not offer session commands') as command:
        session.execute_session_command(api, BINDING, 'session-a', 'send', interactive=True,
                                        message_file=None, read=no_input, write=no_input)
    assert command.value.code == 'SESSION_COMMAND_UNAVAILABLE' and not command.value.possible_effect


@pytest.mark.skipif(os.name != 'nt', reason='Windows console input')
def test_detach_key_distinguishes_paste_and_other_win32_key_events():
    from okto_nexus.adapters.inbound.cli.windows_viewer_terminal import _TerminalKeys

    key = _TerminalKeys()
    assert not key.read('\x1b[20')
    assert not key.read('0~paste\x1d\x1b[221;27;29;1;8;1_\x1b[201~')
    assert not key.read('\x1b[221;27;29;0;8;1_\x1b[221;27;93;1;9;1_')
    assert not key.read('\x1b[67;46;3;1;8;1_')
    assert not key.read('\x1b[221;27;29;1;')
    assert key.read('8;1_') == {'\x1d'}
    assert _TerminalKeys().read('\x1d\x1b[89;21;25;1;8;1_\x0e') == {'\x1d', '\x19', '\x0e'}


@pytest.mark.parametrize('pi_run', [False, True])
def test_terminal_steer_recovers_original_receipt_after_response_loss(monkeypatch, capsys, pi_run):
    scope = {key: value for key, value in BINDING.items() if key != 'endpoint_id'} | {'session_id': 'session-a'}
    exact = {'scope': scope, 'session_owner_generation': 7}
    target = ({'kind': 'observed_run', 'run_ref': 'prun_' + '1' * 32} if pi_run
              else {'kind': 'native_turn', 'turn_id': 'turn-one'})

    class CommandServer(Catalog):
        token = 'fixture-login'
        sent = None

        def __call__(self, method, url, body=None):
            path = urlsplit(url).path
            if path.endswith('/commands'):
                return exact | {'version': 1, 'capability_revision': 'catalog-1', 'items': [{
                    'command_id': 'steer', 'handler': 'review_steer', 'state': 'supported', 'requires_confirmation': True}]}
            if path.endswith('/steer'):
                return exact | {'control': {'target': target, 'queue_revision': 2, 'capability_revision': 'steer-1',
                                           'effect_revision': 'effect-1',
                                           'effect': 'next_boundary' if pi_run else 'same_turn'}}
            if method == 'POST':
                assert path.endswith('/terminal/commands:execute') and self.sent is None
                self.sent = body
                raise session.ConnectionError('OUTCOME_UNKNOWN', 'Simulated lost response.', possible_effect=True)
            if path.endswith('/terminal/inputs/receipt'):
                assert parse_qs(urlsplit(url).query)['client_intent_id'] == [self.sent['client_intent_id']]
                assert parse_qs(urlsplit(url).query)['expected_session_generation'] == ['7']
                boundary = {'steer_boundary': 'awaiting_boundary', 'steer_submitted': True, 'possible_effect': True,
                            'operation_id': 'op-original'} if pi_run else {}
                return exact | {'input_id': 'input-original', 'status': 'DISPATCHING', 'reorientation': True} | boundary
            return super().__call__(method, url, body)

    api = CommandServer()
    service = SimpleNamespace(operator_http=api, inspect=lambda: {'state': 'ready', 'server_id': 'server'})
    tty = SimpleNamespace(isatty=lambda: True)
    answers = iter(('Text by the human operator', '', 'Text by the human operator', 'yes'))
    monkeypatch.setattr('builtins.input', lambda _: next(answers))
    monkeypatch.setattr(session, 'sys', SimpleNamespace(stdin=tty, stdout=tty))
    monkeypatch.setattr(session, 'resolve_terminal_target', lambda *args: service)
    connection = ['--id', 'reviewer', '--session-id', 'session-a']
    assert main(['session', 'steer', *connection]) == 0
    assert api.sent is None and 'Action cancelled' in capsys.readouterr().out
    assert main(['session', 'steer', *connection]) == 0
    assert api.sent['target'] == target and api.sent['confirmed_effect_revision'] == 'effect-1'
    assert api.sent['expected_queue_revision'] == 2 and api.sent['confirmed'] is True
    assert api.sent['content'] == [{'type': 'text', 'text': 'Text by the human operator'}]
    notice = 'Pi queued the reorientation for the next boundary.' if pi_run else 'The message is being delivered.'
    assert notice in capsys.readouterr().out
    assert main(['session', 'receipt', *connection, '--intent', api.sent['client_intent_id'],
                 '--owner-generation', '7', '--json']) == 0
    assert json.loads(capsys.readouterr().out)['receipt']['input_id'] == 'input-original'


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

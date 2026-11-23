"""Session catalog commands use the public ID and canonical binding."""

import json
import os
from contextlib import contextmanager
from io import StringIO
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest

from okto_nexus.adapters.inbound.cli import codex_viewer_process, session
from okto_nexus.adapters.inbound.cli.main import main
from okto_nexus.application.terminal_connection import (
    ConnectionError,
    document_revision,
)

BINDING = {'server_id': 'server', 'executor_id': 'executor', 'binding_id': 'binding', 'agent_id': 'agent',
               'workspace_id': 'workspace', 'workspace_binding_id': 'realization', 'endpoint_id': 'endpoint'}


@pytest.mark.parametrize('answer', ['no', 'yes', 'lost-receipt', 'no-grant', 'legacy-recovery'])
def test_empty_open_requires_confirmation_and_recovers_the_same_receipt(tmp_path, monkeypatch, answer):
    from okto_nexus.adapters.inbound.cli.session_open import empty_session

    binding = BINDING | {'binding_revision': 1}
    scope = binding | {'session_id': 'exact-session', 'session_owner_generation': 1}
    scope.pop('endpoint_id')
    home = tmp_path / 'nexus'
    work = home / 'terminal/work'
    work.mkdir(parents=True)
    retained_work = work / 'profile.json'
    retained_work.write_bytes(b'{ "work": "retained" }')
    service = SimpleNamespace(adapter=SimpleNamespace(home=home))
    resolution = {'operation_id': 'exact-opening', 'intent_hash': 'exact-hash', 'resolution_revision': 1,
                  'reuse': False, 'can_submit': True, 'session_id': 'exact-session',
                  'scope': scope, 'semantic_intent': {'action': 'runtime.open'}}
    operation = {'operation_id': 'exact-opening', 'intent_hash': 'exact-hash', 'action': 'runtime.open',
                 'scope': scope, 'executor_stage': 'SUBMITTED'}
    writes = []

    class Human:
        base, username, token = 'http://127.0.0.1:8202', 'operator', 'fixture'

        def __call__(self, method, path, body=None):
            if path.endswith('/runtime-policy'):
                return {'data': {'effective': {'session_policy': 'per_sender'}}}
            if method == 'POST':
                writes.append(body)
                if path.endswith('intents:resolve'):
                    resolution['client_intent_id'] = body['client_intent_id']
                    return resolution
                assert path.endswith('/runtime/operations')
                if answer == 'no-grant':
                    raise ConnectionError('PERMISSION_DENIED', 'Current grant required')
                if answer == 'lost-receipt':
                    raise ConnectionError('OUTCOME_UNKNOWN', 'Injected lost response', possible_effect=True)
                return operation
            if path.endswith('/runtime/sessions/exact-session?executor_id=executor'):
                return {'scope': scope, 'control_available': True}
            if answer == 'legacy-recovery' and path.endswith('/runtime/intents/' + legacy_intent):
                raise ConnectionError('NOT_FOUND', 'No resolution was recorded', http_status=404)
            assert path.endswith('/runtime/intents/' + resolution['client_intent_id'])
            return {'resolution': resolution, 'operation': operation, 'initial_turn_operation_id': None}

    call = Human()
    assert empty_session(service, call, binding) is None
    monkeypatch.setattr('builtins.input', lambda _: '' if answer == 'no' else 'y')
    legacy_intent = 'empty_open_' + 'a' * 32
    if answer == 'no':
        assert empty_session(service, call, binding, allow_new=True) is None
        assert writes == [] and not list((home / 'terminal/session-openings').glob('*.json'))
    elif answer == 'yes':
        assert empty_session(service, call, binding, allow_new=True) == 'exact-session'
    elif answer == 'legacy-recovery':
        old_scope = {key: value for key, value in BINDING.items() if key != 'endpoint_id'}
        directory = home / 'terminal/session-openings'
        directory.mkdir()
        (directory / (document_revision(old_scope) + '.json')).write_text(json.dumps({
            'format': 1, 'state': 'pending', 'scope': old_scope, 'intent': legacy_intent, 'binding_revision': 1,
            'actor': {'origin': call.base, 'username': call.username},
        }), encoding='utf-8')
        monkeypatch.setattr('builtins.input', lambda _: pytest.fail('Use the explicit recovery command'))
        with pytest.raises(ConnectionError) as pending:
            empty_session(service, call, binding, allow_new=True, confirmed_in_viewer=True)
        assert pending.value.code == 'OPENING_PENDING' and pending.value.possible_effect and writes == []
        monkeypatch.setattr('builtins.input', lambda _: 'y')
        assert empty_session(service, call, binding) == 'exact-session'
        assert writes[0]['client_intent_id'] == legacy_intent
    else:
        expected = 'OUTCOME_UNKNOWN' if answer == 'lost-receipt' else 'PERMISSION_DENIED'
        with pytest.raises(ConnectionError) as rejected:
            empty_session(service, call, binding, allow_new=True)
        assert rejected.value.code == expected
        if answer == 'lost-receipt':
            monkeypatch.setattr('builtins.input', lambda _: pytest.fail('Recovery already has an admission'))
            assert empty_session(service, call, binding) == 'exact-session'
        else:
            assert 'work authorize' in rejected.value.message
            assert empty_session(service, call, binding) is None
    if answer != 'no':
        assert len(writes) == 2
        assert writes[0]['intent'] == 'runtime.start' and 'text' not in writes[0]
        assert ('new_session' in writes[0]) == (answer != 'legacy-recovery')
        assert writes[0].get('new_session', True) is True
        assert writes[1]['client_intent_id'] == writes[0]['client_intent_id']
        checkpoint, = (home / 'terminal/session-openings').glob('*.json')
        assert json.loads(checkpoint.read_text(encoding='utf-8'))['format'] == (1 if answer == 'legacy-recovery' else 2)
    assert retained_work.read_bytes() == b'{ "work": "retained" }'


@pytest.mark.parametrize(('stage', 'lifecycle', 'lease', 'generation', 'code'), [
    ('SUBMITTED', 'CLOSED', 'CLOSED', 1, 'OPENING_CLOSED'),
    ('SUCCEEDED', 'FAILED', 'CLOSED', 1, 'OPENING_CLOSED'),
    ('SUBMITTED', 'READY', 'ACTIVE', 1, 'OPENING_PENDING'),
    ('SUBMITTED', 'CLOSED', 'REVOKED', 1, 'OPENING_PENDING'),
    ('SUBMITTED', 'CLOSED', 'CLOSED', 2, 'OPENING_PENDING'),
    ('OUTCOME_UNKNOWN', 'CLOSED', 'CLOSED', 1, 'OPENING_PENDING'),
])
def test_recovered_opening_settles_only_the_exact_confirmed_retirement(
        tmp_path, monkeypatch, stage, lifecycle, lease, generation, code):
    from okto_nexus.adapters.inbound.cli import session_open

    binding = BINDING | {'binding_revision': 1}
    binding_scope = {key: value for key, value in BINDING.items() if key != 'endpoint_id'}
    scope = binding_scope | {'binding_revision': 1, 'session_id': 'original', 'session_owner_generation': 1}
    intent = 'empty_open_' + 'e' * 32
    opening_path = tmp_path / 'terminal/session-openings' / (document_revision(binding_scope) + '.json')
    opening_path.parent.mkdir(parents=True)
    checkpoint = {'format': 2, 'state': 'pending', 'scope': binding_scope, 'binding_revision': 1,
                  'intent': intent, 'actor': {'origin': 'http://127.0.0.1:8202', 'username': 'operator'}}
    opening_path.write_text(json.dumps(checkpoint), encoding='utf-8')
    resolution = {'scope': scope, 'session_id': 'original', 'client_intent_id': intent, 'can_submit': True,
                  'operation_id': 'opening', 'intent_hash': 'hash', 'semantic_intent': {'action': 'runtime.open'}}
    operation = {'scope': scope, 'operation_id': 'opening', 'intent_hash': 'hash', 'action': 'runtime.open',
                 'executor_stage': stage, 'possible_effect': True}
    reads = []

    class Human:
        base, username, token = 'http://127.0.0.1:8202', 'operator', 'test'

        def __call__(self, method, path):
            assert method == 'GET'
            reads.append(path)
            if path.endswith('/runtime/intents/' + intent):
                return {'resolution': resolution, 'operation': operation, 'initial_turn_operation_id': None}
            assert path.endswith('/runtime/sessions/original?executor_id=executor')
            return {'scope': scope | {'session_owner_generation': generation},
                    'lifecycle_state': lifecycle, 'lease_state': lease, 'control_available': False}

    clock = iter((0, 31))
    monkeypatch.setattr(session_open, 'time', SimpleNamespace(monotonic=lambda: next(clock)))
    monkeypatch.setattr('builtins.input', lambda _: pytest.fail('Recovery must not ask for another opening'))
    service = SimpleNamespace(adapter=SimpleNamespace(home=tmp_path))
    with pytest.raises(ConnectionError) as error:
        session_open.empty_session(service, Human(), binding, allow_new=True)
    assert error.value.code == code and error.value.possible_effect
    saved = json.loads(opening_path.read_text(encoding='utf-8'))
    if code == 'OPENING_CLOSED':
        assert saved == checkpoint | {'state': 'settled', 'session_id': 'original', 'operation_id': 'opening'}
        assert 'original' in error.value.message and 'opening' in error.value.message
    else:
        assert saved == checkpoint
    assert len(reads) == (1 if stage == 'OUTCOME_UNKNOWN' else 2)


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
            return BINDING | {'binding_revision': 4}
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


def test_session_open_confirms_the_selected_connection_without_attaching(monkeypatch, capsys):
    catalog = Catalog(two_live=True)
    catalog.token = 'operator-fixture'
    service = SimpleNamespace(operator_http=catalog, inspect=lambda: {'state': 'ready', 'server_id': 'server'})
    terminal = SimpleNamespace(isatty=lambda: True)
    monkeypatch.setattr(session, 'sys', SimpleNamespace(stdin=terminal, stdout=terminal))
    monkeypatch.setattr(session, 'resolve_terminal_target', lambda *_: service)

    def open_empty(selected_service, call, binding, *, allow_new):
        assert selected_service is service and call is catalog
        assert binding == BINDING | {'binding_revision': 4} and allow_new is True
        return 'empty-new'

    monkeypatch.setattr(session, 'empty_session', open_empty)
    monkeypatch.setattr(session, 'attach_session', lambda *_args, **_kwargs: pytest.fail('Open must not attach'))
    assert main(['session', 'open', '--id', 'reviewer', '--workspace-id', 'workspace']) == 0
    assert 'Opened empty session empty-new.' in capsys.readouterr().out
    assert '/runtime/sessions' not in catalog.routes


@pytest.mark.parametrize(('tty', 'extra'), [(False, []), (True, ['--json']), (True, ['--session-id', 'existing'])])
def test_session_open_rejects_implicit_or_conflicting_selection_before_connecting(tty, extra, monkeypatch):
    terminal = SimpleNamespace(isatty=lambda: tty)
    monkeypatch.setattr(session, 'sys', SimpleNamespace(stdin=terminal, stdout=terminal))
    monkeypatch.setattr(session, 'resolve_terminal_target', lambda *_: pytest.fail('Invalid opening accessed the Server'))
    with pytest.raises(SystemExit) as refused:
        main(['session', 'open', '--id', 'reviewer', *extra])
    assert refused.value.code == 2


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


@pytest.mark.parametrize(('server', 'executor', 'revision', 'code'), [
    ('wrong', 'executor', '4', 'SERVER_ID_MISMATCH'),
    ('server', 'wrong', '4', 'CONNECTION_SELECTOR_CONFLICT'),
    ('server', 'executor', '3', 'CONNECTION_SELECTOR_CONFLICT'),
    ('server', 'executor', '4', None),
])
def test_connector_handoff_verifies_scope_before_attachment(server, executor, revision, code, monkeypatch, tmp_path, capsys):
    catalog = Catalog(base='https://nexus.example')
    service = SimpleNamespace(operator_http=catalog, inspect=lambda: {'state': 'ready', 'server_id': 'server'},
                              adapter=SimpleNamespace(home=tmp_path / 'Nexus client home'))
    tty = SimpleNamespace(isatty=lambda: True)
    monkeypatch.setattr(session, 'sys', SimpleNamespace(stdin=tty, stdout=tty))
    monkeypatch.setattr(session, 'resolve_terminal_target', lambda service_args, profile, operator, local: service
                        if service_args == [] and profile is None and operator == 'human' else pytest.fail('Wrong topology'))
    monkeypatch.setattr(session, 'project_profile', lambda *_: pytest.fail('Connector handoff must not use CWD'))
    scope = {key: value for key, value in BINDING.items() if key != 'endpoint_id'} | {'session_id': 'session-a'}
    detached = {'status': 'detached', 'scope': scope, 'attachment_id': 'att_' + 'a' * 32,
                'attach_strategy': 'codex_remote_read', 'capability_revision': 'sha256:' + 'a' * 64}

    def attach(call, binding, **options):
        assert code is None and call is catalog and binding == BINDING | {'binding_revision': 4}
        assert options == {'session_id': None, 'viewer_executable': None, 'interactive': True, 'write': False}
        return detached

    monkeypatch.setattr(session, 'attach_session', attach)
    reported = []
    monkeypatch.setattr(session, '_display', lambda view, as_json: reported.append(view))
    file = tmp_path / 'attachment.json'
    assert main(['session', 'attach', '--binding-id', 'binding', '--server-id', server, '--executor-id', executor,
                 '--workspace-id', 'workspace', '--binding-revision', revision, '--operator-profile', 'human',
                 '--attachment-receipt', str(file)]) == (0 if code is None else 3)
    terminal = capsys.readouterr().out
    if code is None:
        assert json.loads(file.read_text()) == detached and not reported
        assert terminal.startswith('Reattach to this session: ')
        for option in ('--binding-id=binding', '--server-id=server', '--executor-id=executor',
                       '--workspace-id=workspace', '--session-id=session-a', '--binding-revision=4',
                       '--operator-profile=human', 'Nexus client home'):
            assert option in terminal
        assert '--attachment-receipt' not in terminal and detached['attachment_id'] not in terminal
    else:
        assert not file.exists() and reported[0]['code'] == code
        assert not terminal
    assert catalog.routes == ([] if code == 'SERVER_ID_MISMATCH' else ['/connections/bindings/binding'])


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


@pytest.mark.parametrize('write', [False, True])
def test_unreviewed_codex_viewer_is_refused_before_attachment(monkeypatch, capsys, write):
    catalog = Catalog()
    catalog.token = 'synthetic-cookie'
    service = SimpleNamespace(operator_http=catalog, inspect=lambda: {'state': 'ready', 'server_id': 'server'})
    tty = SimpleNamespace(isatty=lambda: True)
    monkeypatch.setattr(session, 'sys', SimpleNamespace(stdin=tty, stdout=tty))
    monkeypatch.setattr(session, 'resolve_terminal_target', lambda *args: service)
    monkeypatch.setattr(session, 'review_local_presentation', lambda *args, **kwargs: 'fresh-revision')
    monkeypatch.setattr(session, 'open_local_presentation',
                        lambda *args, **kwargs: pytest.fail('Unexpected attachment offer'))
    monkeypatch.setattr(session, 'present_codex', lambda *args: pytest.fail('Unexpected viewer launch'))
    monkeypatch.setattr(codex_viewer_process, 'os', SimpleNamespace(name='nt'))
    monkeypatch.setattr(codex_viewer_process.platform, 'machine', lambda: 'AMD64')
    monkeypatch.setattr(codex_viewer_process, 'candidate',
                        lambda *args, **kwargs: SimpleNamespace(fingerprint='sha256:' + 'a' * 64))

    args = ['session', 'attach', '--id', 'reviewer', '--session-id', 'session-a', '--viewer-executable', 'codex.exe']
    assert main(args + (['--write'] if write else [])) == 3
    assert capsys.readouterr().out.startswith('Use --viewer-executable with the reviewed Codex 0.170.0.')


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


def test_claude_attachment_reads_the_exact_session_and_detaches_locally(monkeypatch, capsys):
    call = Catalog()
    call.token = 'synthetic-cookie'
    binding = BINDING | {'adapter_id': 'claude_stream'}
    closes = []

    def review(api, **selection):
        assert api is call and selection['expected_session_generation'] == 7
        assert selection['presentation'] == 'claude' and selection['scope']['session_id'] == 'session-a'
        return 'claude-revision'

    def read():
        try:
            return next(frames)
        except StopIteration:
            raise KeyboardInterrupt from None

    @contextmanager
    def attach(api, **selection):
        assert api is call and selection['capability_revision'] == 'claude-revision'
        assert selection['scope']['session_id'] == 'session-a' and selection['claude'] is True
        try:
            yield SimpleNamespace(attachment_id='claude-reader', read_terminal_output=read)
        finally:
            closes.append('claude-reader')

    frames = iter([b'Working \xe2', b'\x9c\x93'])
    monkeypatch.setattr(session, 'review_local_presentation', review)
    monkeypatch.setattr(session, 'open_local_presentation', attach)
    result = session.attach_session(call, binding, session_id='session-a', interactive=True)
    assert result['attach_strategy'] == 'claude_local_read' and result['status'] == 'detached'
    assert closes == ['claude-reader']
    output = capsys.readouterr().out
    assert 'Ctrl+C detaches' in output and 'Working ✓' in output
    with pytest.raises(ConnectionError, match='read-only'):
        session.attach_session(call, binding, session_id='session-a', interactive=True, write=True)


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
    monkeypatch.setattr(session, 'show_pi_editor', lambda link, recover, **_: calls.append(link.attachment_id))
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
    assert keys.feed('\x1b[200~review\x12\x18\x19\x0e\x1b[201~') == [('insert', 'review')]
    assert keys.feed('\x1b[82;19;18;1;8;1_\x1b[88;45;24;1;8;1_\x1b[89;21;25;1;8;1_\x0e') == [
        ('steer_review', None), ('interrupt_review', None), ('control_confirm', None), ('control_cancel', None),
    ]
    assert keys.feed('\x0f\x1b[79;24;15;1;8;1_') == [('open_empty_session', None), ('open_empty_session', None)]
    assert keys.feed('\x1b[200~\x0f\x1b[201~') == []


@pytest.mark.parametrize(('initial_keys', 'confirmation', 'allowed', 'result'), [
    ([], '\x19', True, 'open_empty_session'),
    ([], '\x0e', True, None),
    ([], '', True, None),
    ([], '', False, None),
    (['Draft to preserve'], '', True, None),
])
def test_pi_separate_open_stays_local_and_leaves_a_draft_attached(
        monkeypatch, capsys, initial_keys, confirmation, allowed, result):
    from contextlib import nullcontext

    from okto_nexus.adapters.inbound.cli import windows_viewer_terminal
    from okto_nexus.adapters.inbound.cli.pi_viewer_terminal import show_pi_editor

    keys = iter([*initial_keys, '\x0f', *([confirmation] if confirmation else []), None])
    monkeypatch.setattr(windows_viewer_terminal, 'viewer_console_input', lambda _: nullcontext(lambda: next(keys)))
    monkeypatch.setattr(windows_viewer_terminal, 'ansi_viewer_output', lambda _: nullcontext())
    forwarded = []

    def edit(*, key, text, **_):
        forwarded.append((key, text))
        return False, None

    link = SimpleNamespace(poll_pi_output=lambda _: None, edit_pi_input=edit)
    assert show_pi_editor(link, lambda _: None, allow_empty_open=allowed) == result
    assert forwarded == [('insert', text) for text in initial_keys]
    if initial_keys:
        assert 'Finish the draft' in capsys.readouterr().out


@pytest.mark.parametrize('opened', [None, 'session-a', 'session-next'])
def test_pi_separate_open_reviews_after_detach_and_prints_exact_successor_command(monkeypatch, capsys, tmp_path, opened):
    class PiCatalog(Catalog):
        token = 'operator-fixture'

        def __call__(self, method, url, body=None):
            result = super().__call__(method, url, body)
            return result | {'adapter_id': 'pi_rpc'} if url.endswith('/connections/bindings/binding') else result

    api = PiCatalog()
    service = SimpleNamespace(operator_http=api, operator_profile='terminal-user',
                              adapter=SimpleNamespace(home=tmp_path),
                              inspect=lambda: {'state': 'ready', 'server_id': 'server'})
    terminal = SimpleNamespace(isatty=lambda: True)
    monkeypatch.setattr(session, 'sys', SimpleNamespace(stdin=terminal, stdout=terminal))
    monkeypatch.setattr(session, 'resolve_terminal_target', lambda *_: service)
    events = []

    def attach(call, binding, *, session_id, interactive, write, allow_empty_open, **_):
        assert call is api and binding['adapter_id'] == 'pi_rpc'
        assert interactive and write and allow_empty_open
        events.append(('viewer', session_id))
        detached = {'status': 'detached', 'scope': binding | {'session_id': session_id}}
        return detached | {'next_action': 'open_empty_session'} if session_id == 'session-a' else detached

    def open_empty(selected_service, call, binding, *, allow_new, confirmed_in_viewer):
        assert selected_service is service and call is api
        assert allow_new and confirmed_in_viewer and binding['binding_revision'] == 4
        assert events == [('viewer', 'session-a'), ('detach', 'session-a')]
        events.append(('review_open', opened))
        return opened

    monkeypatch.setattr(session, 'attach_session', attach)
    monkeypatch.setattr(session, 'empty_session', open_empty)
    monkeypatch.setattr(session, 'display_reattach_command',
                        lambda attached, *_args, **_kwargs: events.append(('detach', attached['scope']['session_id'])))
    assert main(['session', 'attach', '--write', '--id', 'reviewer', '--workspace-id', 'workspace',
                 '--session-id', 'session-a']) == 0
    assert events == [('viewer', 'session-a'), ('detach', 'session-a'), ('review_open', opened)]
    output = capsys.readouterr().out
    assert 'keep the original session session-a and its queue' in output
    command = [line for line in output.splitlines() if line.startswith('Attach to the new session: ')]
    if opened == 'session-next':
        assert len(command) == 1 and '--session-id=session-next' in command[0] and '--write' in command[0]
    else:
        assert not command


@pytest.mark.parametrize('steer', [False, True])
def test_pi_receipt_recovers_the_original_presenter_intent(monkeypatch, capsys, steer):
    intent = ('pi_steer_' if steer else 'pi_input_') + 'a' * 32

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
            receipt = {'scope': scope, 'session_owner_generation': 7, 'reorientation': steer,
                       'input_id': 'input-original', 'status': 'DISPATCHING' if steer else 'QUEUED'}
            if steer:
                receipt.update(operation_id='operation-original', possible_effect=True, steer_boundary='applied')
            return receipt

    service = SimpleNamespace(operator_http=PiReceipts(), inspect=lambda: {'state': 'ready', 'server_id': 'server'})
    monkeypatch.setattr(session, 'resolve_terminal_target', lambda *args: service)
    assert main(['session', 'receipt', '--id', 'reviewer', '--session-id', 'session-a',
                 '--owner-generation', '7', '--intent', intent, '--json']) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['receipt']['input_id'] == 'input-original'
    if steer:
        assert result['command'] == 'steer' and result['message'] == 'Pi applied the reorientation.'


def test_pi_interrupt_receipt_uses_the_native_presenter_scope(monkeypatch, capsys):
    intent = 'pi_interrupt_' + 'a' * 32

    class InterruptReceipt(Catalog):
        token = 'synthetic-cookie'

        def __call__(self, method, url, body=None):
            if not urlsplit(url).path.endswith('/presenter/interrupt/receipt'):
                return super().__call__(method, url, body)
            assert method == 'GET' and body is None
            query = parse_qs(urlsplit(url).query)
            assert (query['client_intent_id'], query['expected_session_generation']) == ([intent], ['7'])
            scope = {key: BINDING[key] for key in BINDING if key != 'endpoint_id'}
            assert all(query[key] == [value] for key, value in scope.items())
            return {'scope': scope | {'session_id': 'session-a', 'session_owner_generation': 7},
                    'operation_id': 'original-interrupt', 'interrupt': {'target_status': 'interrupted', 'queue_paused': True}}

    service = SimpleNamespace(operator_http=InterruptReceipt(), inspect=lambda: {'state': 'ready', 'server_id': 'server'})
    monkeypatch.setattr(session, 'resolve_terminal_target', lambda *args: service)
    assert main(['session', 'receipt', '--id', 'reviewer', '--session-id', 'session-a',
                 '--owner-generation', '7', '--intent', intent, '--json']) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['receipt']['operation_id'] == 'original-interrupt'
    assert result['command'] == 'interrupt' and 'queue is paused' in result['message']


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


def test_claude_interrupt_cli_confirms_the_operation_and_recovers_the_only_receipt():
    scope = {key: value for key, value in BINDING.items() if key != 'endpoint_id'} | {'session_id': 'session-a'}
    exact = {'scope': scope, 'session_owner_generation': 7}
    target = {'kind': 'claude_operation', 'operation_id': 'op_' + '1' * 32}

    class CommandServer(Catalog):
        token = 'fixture-login'
        sent = None

        def __call__(self, method, url, body=None):
            path = urlsplit(url).path
            if path.endswith('/commands'):
                return exact | {'version': 1, 'capability_revision': 'catalog-1', 'items': [{
                    'command_id': 'interrupt', 'handler': 'review_interrupt', 'state': 'supported',
                    'requires_confirmation': True}]}
            if path.endswith('/interrupt'):
                return exact | {'control': {'target': target, 'queue_revision': 2, 'capability_revision': 'stop-1'}}
            if method == 'POST':
                assert path.endswith('/terminal/commands:execute') and self.sent is None
                self.sent = body
                raise session.ConnectionError('OUTCOME_UNKNOWN', 'Simulated lost response.', possible_effect=True)
            if path.endswith('/terminal/interrupt/receipt'):
                assert parse_qs(urlsplit(url).query)['client_intent_id'] == [self.sent['client_intent_id']]
                return {'scope': scope | {'session_owner_generation': 7}, 'operation_id': 'original-control',
                        'interrupt': {'target_status': 'interrupted', 'queue_paused': True}}
            return super().__call__(method, url, body)

    api = CommandServer()
    prompts = []

    def confirm(prompt):
        prompts.append(prompt)
        return 'yes'

    result = session.execute_session_command(api, BINDING, 'session-a', 'interrupt', interactive=True,
                                             message_file=None, read=confirm, write=lambda _: None)
    assert prompts == ['Interrupt the current Claude turn and pause the queue? [y/N] ']
    assert api.sent['target'] == target and api.sent['confirmed'] is True and 'content' not in api.sent
    assert result['receipt']['operation_id'] == 'original-control' and 'queue is paused' in result['message']


@pytest.mark.parametrize(('stage', 'successor_state', 'result_state', 'exit_code'), [
    ('SUBMITTED', 'READY', 'resume_requested', 0),
    ('SUBMITTED', 'CLOSED', 'resume_closed', 1),
    ('SUBMISSION_STARTED', 'OPEN_PENDING', 'resume_requested', 0),
    ('SUBMISSION_STARTED', 'CLOSED', 'resume_unconfirmed', 1),
    ('OUTCOME_UNKNOWN', None, 'resume_unconfirmed', 1),
])
@pytest.mark.parametrize('existing_review', [False, True])
def test_saved_resume_recovers_its_exact_intent_after_unknown_submission(
        monkeypatch, capsys, stage, successor_state, result_state, exit_code, existing_review):
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
                    'session_id': 'successor', 'can_submit': True, 'reuse': False,
                    'semantic_intent': {'action': 'runtime.open'},
                    'saved_resume': {'source_session_id': 'session-b', 'source_session_generation': 7},
                    'scope': {key: value for key, value in BINDING.items() if key != 'endpoint_id'} |
                             {'session_id': 'successor', 'session_owner_generation': 1}}
                return self.resolution
            if path == session.PREFIX + '/runtime/operations':
                assert method == 'POST' and body['operation_id'] == 'saved-open'
                self.submissions += 1
                self.operation = {'operation_id': 'saved-open', 'scope': self.resolution['scope'], 'action': 'runtime.open',
                                  'intent_hash': self.resolution['intent_hash'],
                                  'executor_stage': stage}
                raise session.ConnectionError('OUTCOME_UNKNOWN', 'Simulated lost response.', possible_effect=True)
            if path == session.PREFIX + '/runtime/sessions/successor':
                assert method == 'GET' and parse_qs(urlsplit(url).query) == {'executor_id': ['executor']}
                assert stage in ('SUBMISSION_STARTED', 'SUBMITTED') and successor_state is not None
                return {'scope': self.resolution['scope'], 'lifecycle_state': successor_state,
                        'lease_state': 'CLOSED' if successor_state == 'CLOSED' else 'ACTIVE'}
            return super().__call__(method, url, body)

    catalog = SavedCatalog()
    source = {key: value for key, value in BINDING.items() if key != 'endpoint_id'} | {
        'session_id': 'session-b', 'session_owner_generation': 7}
    if existing_review:
        catalog('POST', session.PREFIX + '/runtime/intents:resolve', {
            'client_intent_id': 'saved_resume_' + document_revision(source), 'intent': 'runtime.resume_saved',
            'session_id': 'session-b', 'source_session_generation': 7})
    reviewed = catalog.resolution
    service = SimpleNamespace(operator_http=catalog, inspect=lambda: {'state': 'ready', 'server_id': 'server'})
    monkeypatch.setattr(session, 'resolve_terminal_target', lambda *args: service)
    args = ['session', 'resume', '--id', 'reviewer', '--session-id', 'session-b', '--json']
    assert main(args) == 3
    assert json.loads(capsys.readouterr().out)['code'] == 'SAVED_RESUME_CONFIRMATION_REQUIRED'
    assert catalog.resolution is reviewed and catalog.submissions == 0

    tty = SimpleNamespace(isatty=lambda: True)
    monkeypatch.setattr(session, 'sys', SimpleNamespace(stdin=tty, stdout=tty))
    prompts = []
    answers = iter(('', 'yes'))

    def confirm(prompt):
        assert catalog.resolution is reviewed and catalog.submissions == 0
        prompts.append(prompt)
        return next(answers)

    monkeypatch.setattr('builtins.input', confirm)
    assert main(args[:-1]) == 0
    assert 'Saved resume cancelled.' in capsys.readouterr().out
    assert catalog.resolution is reviewed and catalog.submissions == 0
    assert main(args[:-1]) == 1
    output = capsys.readouterr().out
    assert 'session-b in workspace workspace on host executor' in output
    assert 'Saved resume outcome is unconfirmed' in output and 'Receipt saved-open.' in output
    assert prompts == ['Open a successor for this saved session? [y/N] '] * 2
    if existing_review:
        assert catalog.resolution is reviewed
    assert main(args) == exit_code
    result = json.loads(capsys.readouterr().out)
    assert result['session_id'] == 'successor' and result['source_session_id'] == 'session-b'
    assert result['operation_id'] == 'saved-open' and result['executor_stage'] == stage
    assert result['state'] == result_state
    if result_state == 'resume_unconfirmed':
        assert 'outcome is unconfirmed' in result['message']
    elif result_state == 'resume_closed':
        assert 'Saved resume completed' in result['message'] and 'The successor session is closed.' in result['message']
    assert catalog.submissions == 1 and '/runtime/sessions' not in catalog.routes


def test_saved_resume_reports_a_live_source_without_prompting_or_resolving(monkeypatch, capsys):
    class LiveCatalog(Catalog):
        token = 'synthetic-cookie'

        def __call__(self, method, url, body=None):
            path = urlsplit(url).path
            if path.startswith(session.PREFIX + '/runtime/intents/'):
                assert method == 'GET'
                raise session.ConnectionError('NOT_FOUND', 'Missing intent.', http_status=404)
            reply = super().__call__(method, url, body)
            if path.endswith('/runtime/sessions/session-a'):
                return reply | {'lifecycle_state': 'READY', 'lease_state': 'ACTIVE'}
            return reply

    service = SimpleNamespace(operator_http=LiveCatalog(), inspect=lambda: {'state': 'ready', 'server_id': 'server'})
    tty = SimpleNamespace(isatty=lambda: True)
    monkeypatch.setattr(session, 'sys', SimpleNamespace(stdin=tty, stdout=tty))
    monkeypatch.setattr(session, 'resolve_terminal_target', lambda *args: service)
    monkeypatch.setattr('builtins.input', lambda _: pytest.fail('A live source cannot open a saved successor'))
    assert main(['session', 'resume', '--id', 'reviewer', '--session-id', 'session-a']) == 3
    message = capsys.readouterr().out
    assert 'The source session is still active.' in message
    assert 'Use live attachment when available to leave work with the current executor.' in message

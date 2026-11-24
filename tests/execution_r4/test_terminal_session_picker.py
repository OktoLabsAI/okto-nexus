"""Interactive intent and JSON parity with explicit synthetic work boundaries."""
from copy import deepcopy
from types import SimpleNamespace
import json

import pytest

from okto_nexus.adapters.inbound.cli import work as cli
from okto_nexus.adapters.inbound.cli.session_picker import compatible_sessions
from okto_nexus.adapters.outbound.service_manager.context import atomic_json
from okto_nexus.application.terminal_connection import ConnectionError


def session(name, *, available=True, created='ignored'):
    return dict(scope=dict(session_id=name, executor_id='executor', workspace_id='workspace'),
        lifecycle_state='READY' if available else 'CLOSED', control_available=available, created_at=created)


class Flow:
    def __init__(self, rows=(), document=None):
        self.rows = list(rows)
        self.document = deepcopy(document or {})
        self.calls = []
        self.connection = {'selection': {}}
        self.unavailable = False
    def sessions(self):
        self.calls.append(('sessions',))
        return dict(sessions=self.rows, has_more=False)
    def binding(self):
        return {}
    def session(self, binding, session_id):
        self.calls.append(('session', session_id))
        if self.unavailable:
            raise ConnectionError('SESSION_UNAVAILABLE', 'The selected session closed.')
        return next(row for row in self.rows if row['scope']['session_id'] == session_id)
    def observe(self, **kwargs):
        self.calls.append(('observe', kwargs))
        return dict(state='idle')
    def resume(self, slot='work', *, session_id=None, client_intent_id=None):
        self.calls.append(('resume', slot, session_id, client_intent_id))
        self.document[slot]['state'] = 'admitted'
        self.document['session_id'] = 'original-session'
        return dict(state='admitted')
    def submit(self, text=None, **kwargs):
        if kwargs.get('session_id'):
            self.session({}, kwargs['session_id'])
        self.calls.append(('submit', text, kwargs))
        self.document['session_id'] = kwargs.get('session_id') or 'new-session'
        self.document['work'] = {'state': 'admitted'}
        return dict(state='admitted')


def drive(monkeypatch, flow, answers, *, session_id=None):
    values = iter(answers)
    monkeypatch.setattr('builtins.input', lambda prompt: next(values))
    monkeypatch.setattr(cli, 'watch', lambda *args, **kwargs: flow.calls.append(('watch', kwargs)))
    return cli.chat(flow, session_id=session_id)


def submissions(flow):
    return [call for call in flow.calls if call[0] == 'submit']


def test_zero_sessions_opens_only_after_explicit_request(monkeypatch):
    flow = Flow()
    assert drive(monkeypatch, flow, ['/status', '/quit']) == 0
    assert not submissions(flow)
    flow = Flow()
    assert drive(monkeypatch, flow, ['Work now', '/quit']) == 0
    assert submissions(flow) == [('submit', 'Work now', {'session_id': None, 'new_session': True})]


@pytest.mark.parametrize('choice,expected', [('1', 'single'), ('n', None)])
def test_one_session_requires_continue_or_new_choice(monkeypatch, choice, expected):
    flow = Flow([session('single')], {'session_id': 'single'})
    assert drive(monkeypatch, flow, [choice, 'Explicit work', '/quit']) == 0
    assert submissions(flow)[0][2] == dict(session_id=expected, new_session=expected is None)


def test_multiple_sessions_choose_exact_id_not_timestamp_or_checkpoint(monkeypatch):
    flow = Flow([session('older', created='2000'), session('newest', created='2099')], {'session_id': 'newest'})
    assert drive(monkeypatch, flow, ['1', 'Chosen context', '/quit']) == 0
    assert submissions(flow)[0][2]['session_id'] == 'older'
    assert ('observe', {'session_id': 'older'}) in flow.calls


def test_cancel_session_selection_never_submits(monkeypatch):
    flow = Flow([session('single')])
    assert drive(monkeypatch, flow, ['q']) == 0
    assert not submissions(flow)


def test_pending_observe_or_exit_precedes_session_selection(monkeypatch):
    document = {'work': {'state': 'submit_submitted', 'client_intent_id': 'original'}}
    flow = Flow([session('unrelated')], document)
    assert drive(monkeypatch, flow, ['o', 'q']) == 0
    assert flow.document == document
    assert ('observe', {'slot_name': 'work'}) in flow.calls
    assert not any(call[0] in {'resume', 'submit', 'sessions'} for call in flow.calls)


def test_pending_recovery_uses_original_slot_before_explicit_selection(monkeypatch):
    flow = Flow([session('original-session'), session('other')],
        {'work': {'state': 'resolve_submitted', 'client_intent_id': 'original'}})
    assert drive(monkeypatch, flow, ['r', '1', '/quit']) == 0
    assert flow.calls[0] == ('resume', 'work', None, None)
    assert not submissions(flow)
    assert flow.document['work']['client_intent_id'] == 'original'


def test_control_pending_recovery_does_not_become_productive_work(monkeypatch):
    flow = Flow([], {'control': {'state': 'resolved', 'client_intent_id': 'control-original'}})
    assert drive(monkeypatch, flow, ['r', '/quit']) == 0
    assert flow.calls[0] == ('resume', 'control', None, None) and not submissions(flow)


def test_new_context_cannot_control_or_answer_remembered_sibling(monkeypatch):
    flow = Flow([session('remembered')], {'session_id': 'remembered'})
    assert drive(monkeypatch, flow, ['n', '/interrupt', '/close', '/answer request', '/quit']) == 0
    assert not submissions(flow)
    assert not any(call[0] == 'session' for call in flow.calls)


def test_new_context_cannot_resume_a_remembered_sibling(monkeypatch):
    document = {'session_id': 'original-session', 'work': {'state': 'admitted', 'client_intent_id': 'original'}}
    flow = Flow([session('original-session')], document)
    assert drive(monkeypatch, flow, ['n', '/resume', '/status', '/quit']) == 0
    assert flow.document == document
    assert not any(call[0] in {'resume', 'observe', 'watch', 'submit'} for call in flow.calls)


def test_resume_passes_the_selected_session_and_watches_its_receipt(monkeypatch):
    flow = Flow([session('original-session')], {'work': {'state': 'admitted', 'client_intent_id': 'original'}})
    assert drive(monkeypatch, flow, ['/resume', '/quit'], session_id='original-session') == 0
    assert flow.calls[-2:] == [('resume', 'work', 'original-session', None),
                              ('watch', {'timeout': 300, 'interactive': True})]


def test_control_targets_selected_session(monkeypatch):
    flow = Flow([session('a'), session('b')], {'session_id': 'b'})
    assert drive(monkeypatch, flow, ['1', '/interrupt', '/quit']) == 0
    assert submissions(flow) == [('submit', None, {'action': 'interrupt', 'session_id': 'a'})]


def test_closed_or_partial_session_inventory_is_not_latest_fallback(monkeypatch):
    flow = Flow([session('closed', available=False)])
    assert drive(monkeypatch, flow, ['q']) == 0
    assert not submissions(flow)
    flow = Flow([session('single')])
    flow.sessions = lambda: dict(sessions=flow.rows, has_more=True)
    with pytest.raises(ConnectionError) as error:
        compatible_sessions(flow)
    assert error.value.code == 'SESSION_SELECTION_REQUIRED'


def test_closed_session_requires_explicit_new_context(monkeypatch):
    flow = Flow([session('closed', available=False)], {'session_id': 'closed'})
    assert drive(monkeypatch, flow, ['n', 'New context requested', '/quit']) == 0
    assert submissions(flow) == [('submit', 'New context requested', {'session_id': None, 'new_session': True})]


def test_selected_session_closed_before_submit_refuses_without_replacement(monkeypatch):
    flow = Flow([session('single')])
    flow.unavailable = True
    assert drive(monkeypatch, flow, ['1', 'Work', '/quit']) == 0
    assert not submissions(flow)


def test_explicit_chat_session_bypasses_picker_but_revalidates(monkeypatch):
    flow = Flow([session('a'), session('b')])
    assert drive(monkeypatch, flow, ['/quit'], session_id='b') == 0
    assert flow.calls[0] == ('session', 'b')
    assert not any(call[0] == 'sessions' for call in flow.calls)


@pytest.fixture
def parser_boundary(tmp_path, monkeypatch):
    home = tmp_path / 'home'
    path = home / 'terminal/profiles/project.json'
    path.parent.mkdir(parents=True)
    atomic_json(path, dict(format=1, selection={'project': str(tmp_path)}))
    flow = Flow([session('a'), session('b')])
    flow.connection = {'selection': {'project': str(tmp_path)}}
    service = SimpleNamespace(adapter=SimpleNamespace(home=home), inspect=lambda: {'state': 'ready'})
    monkeypatch.setattr(cli, 'resolve_local_service', lambda args: service)
    monkeypatch.setattr(cli, 'open_work', lambda *args: flow)
    monkeypatch.setattr('builtins.input', lambda p: pytest.fail('JSON must never prompt'))
    def run(*args):
        return cli.run_work([*args, '--home', str(home), '--profile', 'project', '--json'])
    return flow, run


def test_json_send_without_durable_session_requires_explicit_selection(parser_boundary, capsys):
    flow, run = parser_boundary
    assert run('send', '--message', 'Work') == 3
    result = json.loads(capsys.readouterr().out)
    assert result['state'] == 'selection_required' and result['effects_started'] is False
    assert {row['session_id'] for row in result['choices']} == {'a', 'b'}
    assert not submissions(flow)


@pytest.mark.parametrize('options', [('--session-id', 'b'), ('--new-session',)])
def test_json_explicit_session_intents_never_prompt(parser_boundary, options):
    flow, run = parser_boundary
    assert run('send', '--message', 'Work', *options) == 0
    request = submissions(flow)[0][2]
    assert request['session_id'] == ('b' if options[0] == '--session-id' else None)
    assert request['new_session'] == (options[0] == '--new-session')


def test_json_resume_preserves_original_intent_without_session_picker(parser_boundary):
    flow, run = parser_boundary
    flow.document['work'] = {'state': 'submit_submitted', 'client_intent_id': 'original'}
    assert run('resume') == 0
    assert flow.document['work']['client_intent_id'] == 'original'
    assert flow.calls == [('resume', 'work', None, None)]

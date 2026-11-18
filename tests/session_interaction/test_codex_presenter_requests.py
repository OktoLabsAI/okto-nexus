"""Exercise the Codex viewer's two exact reads and reject context overrides."""

import pytest

from okto_nexus.application.codex_presenter_requests import (
    CodexHistoryPage,
    CodexThreadPresentation,
    codex_history_page,
    codex_thread_presentation,
)
from okto_nexus.errors import ErrorCode, OktoNexusError

THREAD = 'bdfe5b81-54cf-43cf-8001-5de670d3dd69'


def request(method, params, expected=THREAD):
    return codex_thread_presentation(method=method, params=params, native_thread_id=expected)


def test_observed_exact_read_and_resume_emit_only_bounded_read_intents():
    assert request('thread/read', {'threadId': THREAD}) == CodexThreadPresentation('read', False)
    assert request('thread/read', {'threadId': THREAD, 'includeTurns': True}) == CodexThreadPresentation('read', True)
    params = dict.fromkeys([
        'approvalPolicy', 'approvalsReviewer', 'baseInstructions', 'config', 'cwd', 'developerInstructions',
        'history', 'initialTurnsPage', 'model', 'modelProvider', 'path', 'permissions', 'personality',
        'runtimeWorkspaceRoots', 'sandbox',
    ])
    params.update(threadId=THREAD, excludeTurns=True)
    assert request('thread/resume', params) == CodexThreadPresentation('initialize_view', False)
    assert request('thread/resume', params | {'excludeTurns': False}) == CodexThreadPresentation('initialize_view', True)


@pytest.mark.parametrize('method', ['thread/list', 'thread/loaded/list', 'thread/start', 'thread/fork',
                                   'thread/unsubscribe', 'turn/start', 'turn/steer', 'turn/interrupt'])
def test_other_methods_have_no_route_through_the_read_parser(method):
    with pytest.raises(OktoNexusError) as refusal:
        request(method, {'threadId': THREAD})
    assert refusal.value.code == ErrorCode.PERMISSION_DENIED


@pytest.mark.parametrize(('params', 'expected'), [
    ({}, THREAD),
    ({'threadId': 'latest'}, THREAD),
    ({'threadId': THREAD.upper()}, THREAD),
    ({'threadId': '310872fd-606c-4467-91a0-c5d41a588712'}, THREAD),
    ({'threadId': 'local-label'}, 'local-label'),
])
def test_picker_and_sibling_ids_are_refused(params, expected):
    with pytest.raises(OktoNexusError, match='exact presentation thread'):
        request('thread/resume', params, expected)


@pytest.mark.parametrize('override', [
    {'cwd': 'other-project'}, {'path': 'session-file'}, {'model': 'model'}, {'sandbox': 'danger-full-access'},
    {'developerInstructions': ''}, {'config': {}}, {'runtimeWorkspaceRoots': []}, {'history': []},
    {'initialTurnsPage': {'limit': 1}}, {'permissions': 'other'}, {'newUnknownField': None}, {'excludeTurns': 1},
])
def test_resume_refuses_any_engine_override(override):
    with pytest.raises(OktoNexusError, match='cannot change'):
        request('thread/resume', {'threadId': THREAD} | override)


def test_bootstrap_history_is_scoped_and_uses_small_first_pages():
    turns = codex_history_page(method='thread/turns/list', native_thread_id=THREAD,
        params={'threadId': THREAD, 'limit': 5, 'sortDirection': 'desc', 'itemsView': 'notLoaded', 'cursor': None})
    assert turns == CodexHistoryPage('turns', 'desc', 5, None, items_view='notLoaded')
    items = codex_history_page(method='thread/items/list', native_thread_id=THREAD,
        params={'threadId': THREAD, 'cursor': None, 'limit': 100, 'sortDirection': 'desc', 'turnId': None})
    assert items == CodexHistoryPage('items', 'desc', 100, None)
    with pytest.raises(OktoNexusError, match='exact presentation thread'):
        codex_history_page(method='thread/items/list', native_thread_id=THREAD, params={'threadId': 'sibling'})


@pytest.mark.parametrize(('method', 'extra'), [
    ('thread/turns/list', {'limit': 21}),
    ('thread/turns/list', {'limit': True}),
    ('thread/turns/list', {'itemsView': 'full'}),
    ('thread/items/list', {'sortDirection': 'sideways'}),
    ('thread/items/list', {'deferOutput': {}}),
    ('thread/items/list', {'turnId': 'latest'}),
    ('thread/items/list', {'cursor': {'itemId': 'external-anchor'}}),
    ('thread/items/list', {'cursor': 'a\n'}),
    ('thread/items/list', {'cursor': 'a' * 513}),
    ('thread/items/list', {'limit': 101}),
])
def test_history_rejects_unbounded_or_unqualified_options(method, extra):
    with pytest.raises(OktoNexusError, match='history page is invalid'):
        codex_history_page(method=method, native_thread_id=THREAD, params={'threadId': THREAD} | extra)

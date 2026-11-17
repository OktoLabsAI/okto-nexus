"""Pure client choices over synthetic authorized references, NOT server uniqueness."""
from copy import deepcopy
import json
from urllib.parse import parse_qs, urlsplit

import pytest

from okto_nexus.adapters.inbound.cli import quick_connect_ids as ids
from okto_nexus.application.project_preset import CLIENTS
from okto_nexus.application.terminal_connection import ConnectionError


def reference(*, server='server-a', workspace='project-a', actor='agent-a', host='host-a', suffix='a'):
    return dict(server_id=server, workspace_id=workspace, agent_id=actor, executor_id=host,
                binding_id='binding-' + suffix, endpoint_id='endpoint-' + suffix,
                workspace_binding_id='workspace-binding-' + suffix)


def row(name='codex', *, harness='codex', state='bound', **scope):
    ref = reference(**scope)
    value = dict(connect_id=name, state=state, workspace_id=ref['workspace_id'], adapter_id=CLIENTS[harness])
    if state == 'bound':
        value['canonical_ref'] = ref
    return value


def page(items=(), *, more=False, cursor=None, total=None, revision='a' * 64,
         workspace='project-a', server='server-a'):
    return dict(version=1, capabilities={'public_connection': 1}, server_id=server,
                scope={'workspace_id': workspace}, revision=revision, items=list(items),
                total=len(items) if total is None else total, total_is_exact=True,
                has_more=more, next_cursor=cursor)


def reads(pages):
    pending = iter(deepcopy(pages))
    calls = []

    def call(method, path):
        assert method == 'GET'
        calls.append((method, path))
        return next(pending)

    return call, calls


def no_read(_):
    pytest.fail('noninteractive path attempted input')


def tty(answers):
    answers = iter(answers)
    output = []
    return lambda prompt: next(answers), output.append, output


def assert_code(code, action):
    with pytest.raises(ConnectionError) as captured:
        action()
    assert captured.value.code == code
    return captured.value


@pytest.mark.parametrize('harness', list(CLIENTS))
def test_unused_default_and_explicit_id_are_proposals_only(harness):
    assert ids.propose_id([], harness) == harness
    assert ids.select_id([], harness=harness, new_connection=True, read=no_read) == ('new', harness, None)
    assert ids.select_id([], harness=harness, connect_id='Reviewer', read=no_read) == ('new', 'reviewer', None)


def test_suffix_uses_requested_family_and_all_occupied_states_without_mutation():
    rows = [row('claude', harness='claude'), row('claude-2', state='reserved'), row('claude-4', state='retired')]
    before = deepcopy(rows)
    assert ids.propose_id(rows, 'claude') == 'claude-3'
    assert ids.select_id(rows, harness='claude', new_connection=True, read=no_read) == ('new', 'claude-3', None)
    assert rows == before


def test_no_suffix_can_be_implicitly_applied_to_explicit_occupied_id():
    rows = [row()]
    error = assert_code('HARNESS_ID_ALREADY_EXISTS', lambda: ids.select_id(
        rows, harness='codex', connect_id='codex', new_connection=True, read=no_read))
    assert error.choices == [dict(connect_id='codex-2', proposed=True)]
    assert rows == [row()]


@pytest.mark.parametrize('state,code', [('reserved', 'HARNESS_ID_PENDING'), ('retired', 'HARNESS_ID_ALREADY_EXISTS')])
def test_pending_and_retired_never_resume_or_release(state, code):
    rows = [row('reviewer', state=state)]
    before = deepcopy(rows)
    assert_code(code, lambda: ids.select_id(rows, harness='codex', connect_id='reviewer', read=no_read))
    assert rows == before


def test_noninteractive_agreeing_exact_reference_resumes_without_new_setup():
    occupant = row('reviewer')
    result = ids.select_id([occupant], harness='codex', connect_id='Reviewer',
                           selectors=reference(), read=no_read)
    assert result == ('resume', 'reviewer', occupant)


def test_noninteractive_cross_family_returns_conflict_not_another_harness():
    occupant = row('implementer', harness='codex')
    error = assert_code('HARNESS_ID_ALREADY_EXISTS', lambda: ids.select_id(
        [occupant], harness='claude', connect_id='implementer', read=no_read))
    assert error.choices == [dict(connect_id='claude', proposed=True)]


@pytest.mark.parametrize('requested,existing', [('codex', 'codex'), ('claude', 'codex')])
def test_tty_resume_requires_explicit_choice_and_returns_actual_family(requested, existing):
    occupant = row('implementer', harness=existing)
    read, write, output = tty(['r'])
    assert ids.select_id([occupant], harness=requested, connect_id='implementer',
                         interactive=True, read=read, write=write) == ('resume', 'implementer', occupant)
    assert any('Resume the existing codex' in text for text in output)
    if requested != existing:
        assert any('requested: claude' in text for text in output)


@pytest.mark.parametrize('answers,expected', [(['i', 'reviewer'], 'reviewer'), (['s'], 'claude')])
def test_tty_cross_family_can_propose_separate_requested_harness_id(answers, expected):
    rows = [row('implementer', harness='codex')]
    before = deepcopy(rows)
    read, write, _ = tty(answers)
    assert ids.select_id(rows, harness='claude', connect_id='implementer', interactive=True,
                         read=read, write=write) == ('new', expected, None)
    assert rows == before


@pytest.mark.parametrize('state,new', [('bound', True), ('reserved', False), ('retired', False)])
def test_tty_nonresumable_has_no_resume_option(state, new):
    read, write, output = tty(['r', 'c'])
    assert_code('CONNECT_CANCELLED', lambda: ids.select_id([row('held', state=state)],
        harness='codex', connect_id='held', new_connection=new, interactive=True, read=read, write=write))
    assert not any('r. Resume' in text for text in output)


@pytest.mark.parametrize('key', ids.IDENTITY)
def test_exact_selector_conflicts_never_offer_override_menu(key):
    occupant = row('reviewer')
    before = deepcopy(occupant)
    assert_code('CONNECTION_SELECTOR_CONFLICT', lambda: ids.select_id([occupant], harness='codex',
        connect_id='reviewer', selectors={key: 'another-private-value'}, interactive=True, read=no_read))
    assert occupant == before


def test_multiple_same_family_connections_require_selection_without_tty():
    rows = [row('first'), row('second', actor='agent-b', host='host-b', suffix='b')]
    error = assert_code('HARNESS_ID_SELECTION_REQUIRED', lambda: ids.select_id(rows, harness='codex', read=no_read))
    assert error.choices == [dict(connect_id='first', harness='codex'), dict(connect_id='second', harness='codex')]


@pytest.mark.parametrize('answer,expected', [('2', 'second'), ('a', 'codex')])
def test_tty_multiple_can_select_exact_connection_or_explicitly_add(answer, expected):
    rows = [row('first'), row('second', actor='agent-b', host='host-b', suffix='b')]
    read, write, _ = tty([answer])
    result = ids.select_id(rows, harness='codex', interactive=True, read=read, write=write)
    assert result[1] == expected
    assert result[0] == ('resume' if answer == '2' else 'new')


def test_exact_selector_filters_multiple_actors_and_hosts_without_latest_heuristic():
    rows = [row('first'), row('second', actor='agent-b', host='host-b', suffix='b')]
    result = ids.select_id(rows, harness='codex', selectors={'executor_id': 'host-b'}, read=no_read)
    assert result == ('resume', 'second', rows[1])


def test_generic_pending_collision_does_not_disclose_unrelated_metadata():
    occupant = row('held', state='reserved') | {'private': 'PRIVATE_SECRET', 'owner': 'PRIVATE_AGENT'}
    error = assert_code('HARNESS_ID_PENDING', lambda: ids.select_id([occupant], harness='codex',
        connect_id='held', read=no_read))
    public = str(error) + json.dumps(error.choices)
    assert 'PRIVATE_' not in public


def test_binding_reference_contains_only_exact_canonical_identity_and_is_copied():
    occupant = row('reviewer')
    occupant['canonical_ref']['private_token'] = 'PRIVATE'
    result = ids.binding_reference(occupant)
    assert result == reference()
    result['binding_id'] = 'changed'
    assert occupant['canonical_ref']['binding_id'] == 'binding-a'


def test_complete_paging_preserves_exact_server_workspace_actor_host():
    first = row('first')
    second = row('second', actor='agent-b', host='host-b', suffix='b')
    call, calls = reads([page([first], more=True, cursor='opaque-a', total=2), page([second], total=2)])
    assert ids.public_ids(call, server_id='server-a', workspace_id='project-a') == (first, second)
    assert len(calls) == 2
    query = parse_qs(urlsplit(calls[1][1]).query)
    assert query == {'workspace_id': ['project-a'], 'limit': ['100'], 'cursor': ['opaque-a']}


@pytest.mark.parametrize('changed', [
    {'version': 2}, {'capabilities': {}}, {'server_id': 'server-b'},
    {'scope': {'workspace_id': 'project-b'}}, {'revision': 'short'}, {'items': None},
    {'items': [{}] * 101}, {'has_more': 1}, {'total_is_exact': False}, {'total': True}, {'total': -1},
    {'total': 1}, {'next_cursor': 'unexpected'},
])
def test_unconfirmed_page_never_becomes_empty_namespace(changed):
    call, _ = reads([page() | changed])
    assert_code('PUBLIC_ID_CATALOG_UNCONFIRMED', lambda: ids.public_ids(
        call, server_id='server-a', workspace_id='project-a'))


@pytest.mark.parametrize('field,value', [('revision', 'b' * 64), ('total', 3)])
def test_page_revision_and_total_drift_fail_closed(field, value):
    call, _ = reads([page([row('first')], more=True, cursor='a', total=2),
                     page([row('second')], total=2) | {field: value}])
    assert_code('PUBLIC_ID_CATALOG_UNCONFIRMED', lambda: ids.public_ids(call, server_id='server-a', workspace_id='project-a'))


def test_nonadjacent_cursor_cycle_is_rejected_without_exhausting_page_budget():
    call, calls = reads([page([], more=True, cursor='a', total=1),
                         page([], more=True, cursor='b', total=1),
                         page([], more=True, cursor='a', total=1)])
    assert_code('PUBLIC_ID_CATALOG_UNCONFIRMED', lambda: ids.public_ids(call, server_id='server-a', workspace_id='project-a'))
    assert len(calls) == 3


def test_duplicate_public_ids_across_actors_hosts_are_not_silently_deduplicated():
    call, _ = reads([page([row('reviewer'), row('reviewer', actor='agent-b', host='host-b', suffix='b')])])
    assert_code('PUBLIC_ID_CATALOG_UNCONFIRMED', lambda: ids.public_ids(call, server_id='server-a', workspace_id='project-a'))


@pytest.mark.parametrize('scope', [dict(server='server-b'), dict(workspace='project-b')])
def test_bound_reference_scope_cannot_cross_server_or_project(scope):
    item = row('reviewer', **scope)
    item['workspace_id'] = 'project-a'  # envelope cannot hide a foreign exact reference
    call, _ = reads([page([item])])
    assert_code('PUBLIC_ID_CATALOG_UNCONFIRMED', lambda: ids.public_ids(call, server_id='server-a', workspace_id='project-a'))


@pytest.mark.parametrize('name', ['Reviewer', '', '../secret', 'bad\x1bname', 'a' * 65, None])
def test_invalid_wire_id_is_catalog_error_not_unhandled_validator_exception(name):
    item = row('reviewer') | {'connect_id': name}
    call, _ = reads([page([item])])
    assert_code('PUBLIC_ID_CATALOG_UNCONFIRMED', lambda: ids.public_ids(call, server_id='server-a', workspace_id='project-a'))


@pytest.mark.parametrize('patch', [{'capabilities': None}, {'scope': None}])
def test_malformed_nested_catalog_shape_has_structured_failure(patch):
    call, _ = reads([page() | patch])
    assert_code('PUBLIC_ID_CATALOG_UNCONFIRMED', lambda: ids.public_ids(call, server_id='server-a', workspace_id='project-a'))


@pytest.mark.parametrize('error_code', ['NOT_FOUND', 'HTTP_ERROR', 'VALIDATION_ERROR'])
def test_old_server_capability_errors_request_upgrade_without_writes(error_code):
    calls = []

    def call(method, path):
        calls.append((method, path))
        raise ConnectionError(error_code, 'legacy response')

    assert_code('CONNECT_ID_UNSUPPORTED_SERVER', lambda: ids.require_public_ids(call, 'server-a'))
    assert len(calls) == 1 and calls[0][0] == 'GET'


def test_capability_probe_is_server_exact_and_no_scope_cache_is_created():
    call, calls = reads([page()])
    ids.require_public_ids(call, 'server-a')
    assert len(calls) == 1
    call, _ = reads([page(server='server-b')])
    assert_code('CONNECT_ID_UNSUPPORTED_SERVER', lambda: ids.require_public_ids(call, 'server-a'))


def test_unauthorized_capability_failure_is_not_reclassified_as_old_server():
    def call(_method, _path):
        raise ConnectionError('FORBIDDEN', 'Not authorized')

    assert_code('FORBIDDEN', lambda: ids.require_public_ids(call, 'server-a'))


def test_eof_cancels_without_new_name_or_resume():
    rows = [row('reviewer')]
    before = deepcopy(rows)

    def eof(_):
        raise EOFError()

    assert_code('CONNECT_CANCELLED', lambda: ids.select_id(rows, harness='codex',
        connect_id='reviewer', interactive=True, read=eof, write=lambda _: None))
    assert rows == before


def test_maximum_public_id_is_never_truncated_into_filename_or_another_id():
    name = 'r' * 64
    assert ids.select_id([], harness='codex', connect_id=name, read=no_read) == ('new', name, None)


def test_same_label_in_distinct_projects_is_resolved_only_in_explicit_scope():
    a = row('reviewer')
    b = row('reviewer', workspace='project-b', actor='agent-b', host='host-b', suffix='b')
    call, _ = reads([page([a]), page([b], workspace='project-b')])
    assert ids.public_ids(call, server_id='server-a', workspace_id='project-a') == (a,)
    assert ids.public_ids(call, server_id='server-a', workspace_id='project-b') == (b,)

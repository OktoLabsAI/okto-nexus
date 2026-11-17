"""CLI choice semantics with controlled GET responses; no provider or authority writes."""
from copy import deepcopy
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest

from okto_nexus.adapters.inbound.cli import quick_connect_selection as selection
from okto_nexus.application.project_preset import CLIENTS
from okto_nexus.application.terminal_connection import ConnectionError, PREFIX


def no_read(_):
    pytest.fail('noninteractive/retained choice attempted stdin')


def assert_code(code, action):
    with pytest.raises(ConnectionError) as caught:
        action()
    assert caught.value.code == code


def candidate(client='codex', key='candidate-a', *, allowed=True):
    return dict(adapter_id=CLIENTS[client], candidate_ref=key, can_configure=allowed,
                technical_state='READY_FOR_RUNTIME', private='PRIVATE_MUST_NOT_PRINT')


def inventory(rows=(), *, freshness='FRESH'):
    return dict(agent_id='operator', executor_id='host-a', inventory_revision='inventory-a',
                options=deepcopy(list(rows)), adapter_freshness={adapter: freshness for adapter in CLIENTS.values()})


def choose(body, **kwargs):
    calls = []

    def get(method, path):
        assert method == 'GET'
        calls.append((method, path))
        return deepcopy(body)

    result = selection.choose_harness(get, agent_id='operator', executor_id='host-a',
        workspace_id='project-a', read=no_read, **kwargs)
    return result, calls


@pytest.mark.parametrize('client', list(CLIENTS))
def test_known_harness_selects_exact_passive_candidate_without_running_it(client):
    result, calls = choose(inventory([candidate(client)]), client=client)
    assert result == (client, 'candidate-a')
    assert len(calls) == 1
    assert parse_qs(urlsplit(calls[0][1]).query) == {'executor_id': ['host-a'], 'workspace_id': ['project-a']}


def test_absent_token_can_use_unique_detected_family_but_typo_requires_choice():
    body = inventory([candidate('claude')])
    assert choose(body)[0] == ('claude', 'candidate-a')
    assert_code('CLIENT_SELECTION_REQUIRED', lambda: choose(body, client='claud'))


@pytest.mark.parametrize('token', ['codxe', 'claude; PRIVATE', '$(PRIVATE)', '../../PRIVATE'])
def test_unknown_noninteractive_is_selection_required_and_never_executes_token(token):
    assert_code('CLIENT_SELECTION_REQUIRED', lambda: choose(inventory([candidate()]), client=token))


def test_unknown_tty_selection_is_explicit_not_fuzzy_or_first_candidate():
    output = []
    answers = iter(['not a number', '2'])
    result = selection.choose_harness(lambda *_: inventory([candidate(), candidate('claude', 'claude-a')]),
        agent_id='operator', executor_id='host-a', workspace_id='project-a', client='codxe',
        interactive=True, read=lambda _: next(answers), write=output.append)
    assert result == ('claude', 'claude-a')
    assert 'PRIVATE_MUST_NOT_PRINT' not in '\n'.join(output)


def test_multiple_families_without_tty_never_choose_first():
    assert_code('CLIENT_SELECTION_REQUIRED', lambda: choose(inventory([candidate(), candidate('claude', 'b')])))


@pytest.mark.parametrize('answer', ['c', ''])
def test_harness_picker_cancel_is_no_effect(answer):
    assert_code('CONNECT_CANCELLED', lambda: selection.choose_harness(
        lambda *_: inventory(), agent_id='operator', executor_id='host-a', workspace_id=None,
        interactive=True, read=lambda _: answer, write=lambda _: None))


def test_supported_but_absent_is_not_installed_automatically():
    assert_code('INSTALLATION_UNAVAILABLE', lambda: choose(inventory(), client='claude'))


@pytest.mark.parametrize('freshness', ['STALE', 'OFFLINE', 'UNKNOWN'])
@pytest.mark.parametrize('present', [False, True])
def test_stale_never_means_absence_or_ready(freshness, present):
    assert_code('INVENTORY_UNCONFIRMED', lambda: choose(inventory(
        [candidate()] if present else [], freshness=freshness), client='codex'))


def test_multiple_installations_require_exact_candidate_noninteractive():
    body = inventory([candidate(key='first'), candidate(key='second')])
    assert_code('INSTALLATION_SELECTION_REQUIRED', lambda: choose(body, client='codex'))
    assert choose(body, client='codex', candidate_ref='second')[0] == ('codex', 'second')
    assert_code('INSTALLATION_UNAVAILABLE', lambda: choose(body, client='codex', candidate_ref='missing'))


def test_tty_installation_picker_never_defaults_to_first():
    result = selection.choose_harness(lambda *_: inventory([candidate(key='first'), candidate(key='second')]),
        agent_id='operator', executor_id='host-a', workspace_id='project-a', client='codex',
        interactive=True, read=lambda _: '2', write=lambda _: None)
    assert result == ('codex', 'second')


@pytest.mark.parametrize('allowed', [False, None, 1, 'true'])
def test_configuration_policy_requires_boolean_true(allowed):
    assert_code('CONFIGURATION_NOT_AUTHORIZED', lambda: choose(inventory([candidate(allowed=allowed)]), client='codex'))


@pytest.mark.parametrize('body', [None, {'options': None, 'adapter_freshness': {}},
                                 {'options': [None], 'adapter_freshness': {}},
                                 {'options': [], 'adapter_freshness': None}])
def test_malformed_inventory_is_structured_unconfirmed(body):
    assert_code('INVENTORY_UNCONFIRMED', lambda: choose(body, client='codex'))


@pytest.mark.parametrize('field,value', [('agent_id', 'foreign-agent'), ('executor_id', 'foreign-host')])
def test_inventory_echo_cannot_cross_agent_or_host(field, value):
    body = inventory([candidate()]) | {field: value}
    assert_code('INVENTORY_UNCONFIRMED', lambda: choose(body, client='codex'))


def args(**changes):
    values = dict(client='codex', candidate_ref=None, connect_id='reviewer', new_connection=False,
                  new_agent=None, agent=None, binding_id=None, workspace_id=None, project_name=None,
                  project=None, profile='stable-local-shortcut', plan=False, provider_home=None,
                  name=None, remote_draft=None, review_current=False)
    return SimpleNamespace(**(values | changes))


def exact_reference():
    return dict(server_id='server-a', executor_id='host-a', agent_id='agent-a', workspace_id='project-a',
                binding_id='binding-a', endpoint_id='endpoint-a', workspace_binding_id='workspace-binding-a')


def bound_id():
    return dict(connect_id='reviewer', state='bound', workspace_id='project-a',
                adapter_id=CLIENTS['codex'], canonical_ref=exact_reference())


class GetOnly:
    def __init__(self, items=()):
        self.items = deepcopy(list(items))
        self.calls = []

    def __call__(self, method, path):
        assert method == 'GET'
        self.calls.append((method, path))
        parsed = urlsplit(path)
        route = parsed.path.removeprefix(PREFIX)
        if route == '/connections/me':
            return dict(server_id='server-a', agent_id='operator')
        if route == '/connections/public-ids':
            return dict(version=1, server_id='server-a', capabilities={'public_connection': 1},
                scope={'workspace_id': 'project-a'}, revision='a' * 64, total=len(self.items),
                total_is_exact=True, items=deepcopy(self.items), has_more=False, next_cursor=None)
        if route.endswith('/runtime-options'):
            return inventory([candidate()])
        if route == '/connections/catalog':
            return dict(version=1, server_id='server-a', scope={'workspace_id': 'project-a'},
                revision='a' * 64, total=0, total_is_exact=True, items=[], has_more=False, next_cursor=None)
        pytest.fail('Unexpected GET (possibly recovery consulted inventory): ' + route)


@pytest.fixture
def project_stub(monkeypatch, tmp_path):
    resolved = dict(project=str(tmp_path), label='Project A', workspace_id='project-a',
        project_revision='sha256:' + 'a' * 64, project_name_source='existing_nexus',
        name_discovery=dict(status='not_needed', reason='existing_nexus'),
        cwd_resolution=dict(invocation_cwd=str(tmp_path), project_root=str(tmp_path), root_explicit=False, source='cwd'))
    monkeypatch.setattr(selection, 'local_executor', lambda *_: 'host-a')
    monkeypatch.setattr(selection, 'resolve_project', lambda *_a, **_kw: deepcopy(resolved))
    return resolved


def prepare(call, namespace, root, **kwargs):
    return selection.prepare(call, namespace, root=str(root), invocation_cwd=str(root), read=no_read, **kwargs)


def test_new_agent_cannot_resume_existing_public_id(project_stub, tmp_path):
    call = GetOnly([bound_id()])
    assert_code('CONNECTION_SELECTOR_CONFLICT', lambda: prepare(call, args(new_agent='brand-new'), tmp_path))
    assert not any('/runtime-options' in path for _, path in call.calls)


def test_add_cannot_turn_into_legacy_binding_association(tmp_path):
    call = GetOnly()
    assert_code('ADDITION_CONFLICT', lambda: prepare(call,
        args(new_connection=True, agent='agent-a', binding_id='binding-a'), tmp_path))
    assert len(call.calls) == 2  # me + capability only; no inventory or setup writes


def test_existing_exact_id_returns_resume_without_installation_probe(project_stub, tmp_path):
    call = GetOnly([bound_id()])
    result = prepare(call, args(), tmp_path)
    assert result['action'] == 'resume' and result['reference'] == exact_reference()
    assert result['selection']['quick_connect']['operation'] == 'reused'
    assert not any('/runtime-options' in path for _, path in call.calls)


@pytest.mark.parametrize('change', [{'agent': 'other-agent'}, {'binding_id': 'other-binding'}, {'workspace_id': 'other-project'}])
def test_prepare_bound_id_does_not_override_exact_selectors(project_stub, tmp_path, change):
    assert_code('CONNECTION_SELECTOR_CONFLICT', lambda: prepare(GetOnly([bound_id()]), args(**change), tmp_path))


@pytest.mark.parametrize('change', [{'agent': 'other-agent'}, {'binding_id': 'other-binding'}])
def test_legacy_completed_profile_must_not_override_explicit_selector(project_stub, tmp_path, change):
    saved = dict(state='done', server_id='server-a',
        selection=dict(agent='agent-a', client='codex', project=str(tmp_path), label='Project A',
            workspace_id='project-a', binding_id='binding-a', candidate_ref=None,
            provider_home=None, create_agent=False, display_name=None),
        result={'binding': {'binding_id': 'binding-a'}})
    assert_code('PROFILE_CONFLICT', lambda: prepare(GetOnly([bound_id()]), args(**change), tmp_path, saved=saved))


def retained(root, *, server='server-a'):
    return dict(state='test_issued', server_id=server,
        selection=dict(agent='agent-a', client='codex', workspace_id='project-a', binding_id=None,
            candidate_ref='candidate-a', provider_home=None, project=str(root), label='Project A',
            create_agent=True, display_name=None,
            quick_connect={'version': 1, 'operation': 'created'},
            public_connection={'version': 1, 'connect_id': 'reviewer'}))


def test_pending_own_intent_recovery_precedes_namespace_collision_and_does_not_discover(tmp_path, monkeypatch):
    monkeypatch.setattr(selection, 'local_executor', lambda *_: pytest.fail('retained read executor inventory'))
    monkeypatch.setattr(selection, 'resolve_project', lambda *_a, **_kw: pytest.fail('retained called project/Git'))
    call = GetOnly([bound_id()])
    saved = retained(tmp_path)
    result = prepare(call, args(), tmp_path, saved=saved)
    assert result['action'] == 'retained' and result['selection'] == saved['selection']
    assert all('?' not in path for _, path in call.calls)
    assert len(call.calls) == 2


@pytest.mark.parametrize('changes', [
    {'connect_id': 'other'}, {'project_name': 'Other'}, {'client': 'claude'}, {'new_agent': 'other'},
    {'agent': 'other'}, {'workspace_id': 'other'}, {'binding_id': 'other'}, {'candidate_ref': 'other'},
    {'provider_home': 'other'}, {'project': 'explicit-other-root'}, {'name': 'other'},
])
def test_retained_exact_flag_mismatch_never_overwrites_or_replays(tmp_path, changes):
    call = GetOnly()
    saved = retained(tmp_path)
    original = deepcopy(saved)
    effective_root = tmp_path / 'other' if changes.get('project') else tmp_path
    assert_code('PROFILE_CONFLICT', lambda: prepare(call, args(**changes), effective_root, saved=saved))
    assert saved == original
    assert not any('/runtime-options' in path for _, path in call.calls)


def test_retained_foreign_server_is_refused_not_relabelled_current(tmp_path):
    assert_code('PROFILE_CONFLICT', lambda: prepare(GetOnly(), args(), tmp_path, saved=retained(tmp_path, server='server-b')))


def test_pending_legacy_setup_is_not_adopted_or_reconfigured(tmp_path):
    assert_code('PROFILE_CONFLICT', lambda: prepare(GetOnly(), args(), tmp_path,
        saved={'state': 'test_issued', 'selection': {'agent': 'legacy'}}))


def test_free_id_new_choice_only_proposes_metadata_no_test_or_reservation(project_stub, tmp_path):
    call = GetOnly()
    result = prepare(call, args(new_connection=True), tmp_path)
    assert result['action'] == 'new'
    value = result['selection']
    assert value['public_connection']['connect_id'] == 'reviewer'
    assert value['public_connection']['reservation_ref'].startswith('pcr_')
    assert value['candidate_ref'] == 'candidate-a' and value['create_agent'] is True
    assert all(method == 'GET' for method, _ in call.calls)

"""B04 passive alternatives: supported is neither installed nor authenticated."""
from copy import deepcopy
import json

import pytest

from okto_nexus.adapters.inbound.cli.quick_connect_selection import choose_harness
from okto_nexus.application.project_preset import CLIENTS
from okto_nexus.application.terminal_connection import ConnectionError


def candidate(harness, *, allowed=True):
    return dict(adapter_id=CLIENTS[harness], candidate_ref=harness + '-candidate',
                technical_state='READY_FOR_RUNTIME', can_configure=allowed,
                private='PRIVATE_NOT_PUBLIC', provider_home_suggestion='PRIVATE_NOT_PUBLIC')


def inventory(*rows, stale=None):
    freshness = dict.fromkeys(CLIENTS.values(), 'FRESH')
    if stale:
        freshness[CLIENTS[stale]] = 'STALE'
    return dict(agent_id='operator', executor_id='host-a', inventory_revision='revision-a',
                options=list(rows), adapter_freshness=freshness)


def run(body, *, client='claude', interactive=False, answers=(), candidate_ref=None):
    calls, prompts, output = [], [], []
    supplied = iter(answers)

    def get(method, path):
        assert method == 'GET' and path.endswith('/runtime-options?executor_id=host-a&workspace_id=project-a')
        calls.append((method, path))
        return deepcopy(body)

    def read(prompt):
        assert interactive, 'noninteractive selection attempted stdin'
        prompts.append(prompt)
        try:
            return next(supplied)
        except StopIteration:
            pytest.fail('Unexpected extra prompt; no default/implicit answer is permitted')

    state = dict(calls=calls, prompts=prompts, output=output)

    def execute():
        return choose_harness(get, agent_id='operator', executor_id='host-a', workspace_id='project-a',
            client=client, candidate_ref=candidate_ref, interactive=interactive, read=read, write=output.append)

    return execute, state


def test_known_missing_harness_tty_can_explicitly_choose_available_supported_family():
    execute, state = run(inventory(candidate('codex')), interactive=True, answers=['1'])
    assert execute() == ('codex', 'codex-candidate')
    assert state['prompts'] and len(state['calls']) == 1
    assert 'PRIVATE_NOT_PUBLIC' not in '\n'.join(state['output'])


@pytest.mark.parametrize('answer', ['c', ''])
def test_known_missing_harness_tty_can_cancel_without_install_or_test(answer):
    execute, state = run(inventory(candidate('codex')), interactive=True, answers=[answer])
    with pytest.raises(ConnectionError) as caught:
        execute()
    assert caught.value.code == 'CONNECT_CANCELLED'
    assert len(state['calls']) == 1 and state['prompts']


def test_known_missing_noninteractive_exposes_three_safe_supported_alternatives():
    execute, state = run(inventory(candidate('codex')))
    with pytest.raises(ConnectionError) as caught:
        execute()
    error = caught.value
    assert error.code == 'INSTALLATION_UNAVAILABLE'
    assert isinstance(error.choices, list)
    assert {choice['harness'] for choice in error.choices} == set(CLIENTS)
    by_name = {choice['harness']: choice for choice in error.choices}
    assert by_name['codex']['observed'] is True and by_name['codex']['freshness'] == 'FRESH'
    assert by_name['claude']['observed'] is False and by_name['claude']['freshness'] == 'FRESH'
    wire = json.dumps(error.choices)
    assert 'PRIVATE_NOT_PUBLIC' not in wire
    for choice in error.choices:
        assert not {'authenticated', 'logged_in', 'model_ready', 'provider_ready'} & set(choice)
    assert not state['prompts'] and len(state['calls']) == 1


def test_stale_requested_harness_is_unconfirmed_not_missing_or_auto_switched():
    execute, state = run(inventory(candidate('codex'), stale='claude'))
    with pytest.raises(ConnectionError) as caught:
        execute()
    assert caught.value.code == 'INVENTORY_UNCONFIRMED'
    assert not state['prompts'] and len(state['calls']) == 1


def test_stale_tty_request_never_switches_harness_without_explicit_answer():
    execute, state = run(inventory(candidate('codex'), stale='claude'), interactive=True, answers=['c'])
    with pytest.raises(ConnectionError) as caught:
        execute()
    assert caught.value.code in {'INVENTORY_UNCONFIRMED', 'CONNECT_CANCELLED'}
    assert len(state['calls']) == 1


def test_denied_requested_candidate_cannot_bypass_policy_noninteractive():
    execute, state = run(inventory(candidate('codex', allowed=False), candidate('claude')), client='codex')
    with pytest.raises(ConnectionError) as caught:
        execute()
    assert caught.value.code == 'CONFIGURATION_NOT_AUTHORIZED'
    assert not state['prompts'] and len(state['calls']) == 1


def test_denied_candidate_can_explicitly_choose_different_fresh_authorized_family():
    execute, state = run(inventory(candidate('codex', allowed=False), candidate('claude')),
        client='codex', interactive=True, answers=['2'])
    assert execute() == ('claude', 'claude-candidate')
    assert state['prompts'] and len(state['calls']) == 1


def test_explicitly_selected_denied_alternative_is_still_refused():
    execute, state = run(inventory(candidate('codex', allowed=False)),
        client='claude', interactive=True, answers=['1', 'c'])
    with pytest.raises(ConnectionError) as caught:
        execute()
    assert caught.value.code in {'CONFIGURATION_NOT_AUTHORIZED', 'CONNECT_CANCELLED'}
    assert len(state['calls']) == 1


def test_explicitly_selected_stale_alternative_is_not_usable():
    execute, state = run(inventory(candidate('codex'), stale='codex'), interactive=True, answers=['1', 'c'])
    with pytest.raises(ConnectionError) as caught:
        execute()
    assert caught.value.code in {'INVENTORY_UNCONFIRMED', 'CONNECT_CANCELLED'}
    assert len(state['calls']) == 1

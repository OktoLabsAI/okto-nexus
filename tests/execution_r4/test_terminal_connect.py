"""Project review and terminal resume use the canonical managed setup."""
from copy import deepcopy
from dataclasses import replace
import json
from types import SimpleNamespace

import pytest

import test_local_realization
import test_local_installation_check
from test_connection_setup_recovery import snapshot
from okto_nexus.application.project_preset import ORIGIN
from okto_nexus.application.terminal_connection import ConnectionError, TerminalConnection
from okto_nexus.adapters.inbound.cli import connect

local_setup = test_local_realization.local_setup
checking = test_local_installation_check.checking


@pytest.fixture
def terminal(checking, local_setup, monkeypatch):
    import nexus_connector_core.availability as availability
    from okto_nexus.bootstrap import embedded_inventory

    deps, app, client, headers, _, _, _, probes = checking
    # This is a synthetic installation, not a provider qualification campaign.
    original_discovery = embedded_inventory.discover_local_candidates
    def observed_build(**kwargs):
        return SimpleNamespace(candidates=tuple(replace(item, architecture='x86_64')
            for item in original_discovery(**kwargs).candidates))
    monkeypatch.setattr(embedded_inventory, 'discover_local_candidates', observed_build)
    monkeypatch.setattr(availability, 'qualified_build', lambda *args, **kwargs: True)
    monkeypatch.setattr(availability, 'can_probe_protocol', lambda *args, **kwargs: True)
    monkeypatch.setattr(availability, 'containment_preflight', lambda **kwargs: {'job_objects': 'ok'})
    client.portal.call(app.state.embedded_inventory_owner.refresh)
    project = str(local_setup[6].resolve())
    calls, turns, saved = [], [], []
    async def simulated_harness(entry, request, candidate):
        turns.append(request['client_intent_id'])
        entry.update(status='succeeded', stage='Connection verified')
    monkeypatch.setattr(app.state.connection_tests, 'run', simulated_harness)
    fault = SimpleNamespace(after=None)
    def call(method, path, body=None):
        calls.append((method, path))
        response = client.request(method, path, json=body, headers={'X-Nexus-UI': '1'})
        value = response.json()
        if response.status_code >= 400:
            error = value['error']
            raise ConnectionError(error['code'], error['message'], stage=error.get('stage', 'http'))
        if fault.after and path.endswith(fault.after):
            fault.after = None
            raise ConnectionError('OUTCOME_UNKNOWN', 'Injected lost response', possible_effect=True)
        return value
    flow = TerminalConnection(call, lambda value: saved.append(deepcopy(value)))
    selection = dict(agent='subject', client=None, project=project, label='Project', workspace_id=None,
                     binding_id=None, candidate_ref=None, provider_home=None)
    return SimpleNamespace(flow=flow, selection=selection, calls=calls, turns=turns, saved=saved,
                           fault=fault, probes=probes, deps=deps, app=app, call=call)


def test_review_requires_exact_consent_then_finish_and_reconnect_preserve_configuration(terminal):
    t = terminal
    before = snapshot(t.deps)
    document = t.flow.review(t.selection)
    assert document['state'] == 'review' and document['version_check_required']
    assert document['selection']['client'] == 'codex'
    assert document['request']['project_preset'] == ORIGIN
    assert document['request']['configuration']['tool_access'] == 'ask'
    assert document['request']['configuration']['harness_settings'] == {}
    assert t.probes == t.turns == [] and snapshot(t.deps) == before
    with pytest.raises(ConnectionError, match='Approve'):
        t.flow.apply(document, approval='wrong')
    result = t.flow.apply(document, approval=document['review_revision'])
    assert result['state'] == 'configured' and result['work_state'] == 'not_submitted'
    assert result['configuration']['project_preset'] == ORIGIN
    assert len(t.probes) == len(t.turns) == 1
    after = snapshot(t.deps)
    assert len(after['execution_bindings']) == len(after['runtime_execution_grants']) == 1
    resumed = t.flow.apply(deepcopy(t.saved[-1]))
    assert resumed == result and snapshot(t.deps) == after
    assert len(t.probes) == len(t.turns) == 1
    assert [item['state'] for item in t.saved] == ['review', 'approved', 'check_submitted', 'approved', 'test_submitted', 'finish', 'done']


@pytest.mark.parametrize('lost', ['installations:check', 'setup:test', 'setup:finish'])
def test_response_loss_resumes_without_repeating_native_effects(terminal, lost):
    t = terminal
    document = t.flow.review(t.selection)
    t.fault.after = lost
    with pytest.raises(ConnectionError, match='Injected'):
        t.flow.apply(document, approval=document['review_revision'])
    if lost == 'setup:finish':
        t.app.state.connection_tests.tests.clear()
    recovered = t.flow.apply(deepcopy(t.saved[-1]))
    assert recovered['state'] == 'configured'
    assert len(t.probes) == len(t.turns) == 1
    assert sum(path.endswith('setup:finish') for _, path in t.calls) == 1
    assert len(snapshot(t.deps)['runtime_execution_grants']) == 1


def test_submitted_test_with_lost_cache_is_not_replayed(terminal):
    t = terminal
    document = t.flow.review(t.selection)
    t.fault.after = 'setup:test'
    with pytest.raises(ConnectionError):
        t.flow.apply(document, approval=document['review_revision'])
    t.app.state.connection_tests.tests.clear()
    with pytest.raises(ConnectionError) as failure:
        t.flow.apply(deepcopy(t.saved[-1]))
    assert failure.value.code == 'SETUP_TEST_UNCONFIRMED'
    assert len(t.turns) == 1 and not snapshot(t.deps)['execution_bindings']


def test_mutated_review_never_starts_a_test(terminal):
    document = terminal.flow.review(terminal.selection)
    document['request']['configuration']['tool_access'] = 'always_allow'
    document['state'] = 'approved'
    with pytest.raises(ConnectionError) as failure:
        terminal.flow.apply(document)
    assert failure.value.code == 'REVIEW_CHANGED'
    assert terminal.turns == terminal.probes == []


def test_cli_plan_apply_and_reconnect_use_saved_profile(terminal, tmp_path, monkeypatch, capsys):
    t = terminal
    actions = []
    service = SimpleNamespace(adapter=SimpleNamespace(home=tmp_path / 'terminal-home', host='127.0.0.1', port=8202),
        inspect=lambda: actions.append('inspect') or {'state': 'ready'},
        ensure_running=lambda **kwargs: actions.append('ensure') or {'state': 'ready'})
    monkeypatch.setattr(connect, 'resolve_local_service', lambda args: service)
    monkeypatch.setattr(connect, 'LocalOperatorHTTP', lambda **kwargs: t.call)
    args = ['--profile', 'project', '--agent', 'subject', '--project', t.selection['project'], '--json']
    assert connect.run_connect(args + ['--plan']) == 0
    review = json.loads(capsys.readouterr().out)
    assert actions == ['inspect'] and t.turns == t.probes == []
    assert connect.run_connect(args + ['--approve', review['review_revision']]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['state'] == 'configured'
    assert connect.run_connect(['--profile', 'project', '--json']) == 0
    assert json.loads(capsys.readouterr().out) == result
    assert actions == ['inspect', 'ensure', 'ensure']
    assert len(t.probes) == len(t.turns) == 1


def test_existing_agent_binding_is_reused_after_canonical_project_match(terminal):
    t = terminal
    review = t.flow.review(t.selection)
    configured = t.flow.apply(review, approval=review['review_revision'])
    before = snapshot(t.deps)
    automatically_reused = t.flow.review(dict(t.selection))
    assert automatically_reused == configured | {'setup_run_id': None}
    with pytest.raises(ConnectionError) as selection:
        t.flow.review(dict(t.selection, workspace_id='another-workspace'))
    assert selection.value.code == 'CONNECTION_SELECTION_REQUIRED'
    reused = t.flow.review(dict(t.selection, binding_id=configured['binding_id']))
    assert reused == configured | {'setup_run_id': None}
    for field in ('workspace_id', 'candidate_ref', 'provider_home'):
        with pytest.raises(ConnectionError) as drift:
            t.flow.review(dict(t.selection, binding_id=configured['binding_id']) | {field: 'another-value'})
        assert drift.value.code == 'PROFILE_DRIFT'
    assert snapshot(t.deps) == before and len(t.turns) == 1


@pytest.mark.parametrize('origin', [{'id': 'unknown', 'revision': 1}, {'id': 'project-generalist', 'revision': 2},
                                  {'id': 'project-generalist', 'revision': True}])
def test_unknown_preset_origin_is_rejected_before_test(terminal, origin):
    document = terminal.flow.review(terminal.selection)
    request = deepcopy(document['request'])
    request['project_preset'] = origin
    with pytest.raises(ConnectionError) as failure:
        terminal.flow.api('POST', '/connections/setup:test', request)
    assert failure.value.code == 'VALIDATION_ERROR'
    assert terminal.turns == terminal.probes == []


def test_reconnect_reads_later_customization_without_reissuing_grants(terminal):
    from okto_nexus.adapters.inbound.mcp.tools.harness import build_endpoint_service
    from okto_nexus.domain.runtime_context import RuntimeRequestContext

    t = terminal
    document = t.flow.review(t.selection)
    t.flow.apply(document, approval=document['review_revision'])
    endpoint = document['result']['binding']['endpoint_id']
    service = build_endpoint_service(t.deps)
    context = RuntimeRequestContext('operator', 'http_loopback', trusted_local_operator=True)
    current = service.tool_permission(context, endpoint_id=endpoint)
    service.tool_permission(context, endpoint_id=endpoint,
                            changes={'expected_revision': current['revision'], 'mode': 'always_allow'})
    before = snapshot(t.deps)
    result = t.flow.apply(document)
    assert result['configuration']['public_config']['nexus_tool_permission'] == 'always_allow'
    assert result['configuration']['project_preset'] == ORIGIN
    assert snapshot(t.deps) == before and len(t.turns) == 1

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
            raise ConnectionError(error['code'], error['message'], stage=error.get('stage', 'http'),
                                  possible_effect=error.get('possible_effect', False))
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
    if lost == 'installations:check':
        # A lost check reply is recovered by observation in the same apply.
        recovered = t.flow.apply(document, approval=document['review_revision'])
        assert recovered['state'] == 'configured'
    else:
        with pytest.raises(ConnectionError, match='Injected'):
            t.flow.apply(document, approval=document['review_revision'])
    if lost == 'setup:finish':
        t.app.state.connection_tests.tests.clear()
    recovered = t.flow.apply(deepcopy(t.saved[-1]))
    assert recovered['state'] == 'configured'
    assert len(t.probes) == len(t.turns) == 1
    assert sum(path.endswith('setup:finish') for _, path in t.calls) == 1
    assert len(snapshot(t.deps)['runtime_execution_grants']) == 1


@pytest.fixture
def check_recovery(terminal):
    """Real setup HTTP fixture; only the lost reply/observation timing is injected."""
    t = terminal
    document = t.flow.review(t.selection)
    state = SimpleNamespace(now=0.0, post_elapsed=0.0, checked=False,
                            options_reads=0, mutate=None, get_error=None, post_error=None)
    original = t.flow.call

    def call(method, path, body=None):
        if method == 'POST' and path.endswith('installations:check'):
            if state.post_error is not None:
                raise state.post_error
            original(method, path, body)
            state.checked = True
            state.now += state.post_elapsed
            raise ConnectionError('OUTCOME_UNKNOWN', 'Lost version-check reply', possible_effect=True)
        if state.checked and method == 'GET' and state.get_error is not None:
            raise state.get_error
        value = original(method, path, body)
        if state.checked and method == 'GET':
            if '/runtime-options?' in path:
                state.options_reads += 1
            if state.mutate is not None:
                value = state.mutate(path, deepcopy(value))
        return value

    def sleep(seconds):
        assert seconds > 0
        state.now += seconds

    t.flow.call = call
    t.flow.monotonic = lambda: state.now
    t.flow.sleep = sleep
    return t, document, state


@pytest.mark.parametrize('delay', [0, 2])
def test_check_reply_loss_observes_same_publication_before_single_test(check_recovery, delay):
    t, document, state = check_recovery

    def delayed(path, value):
        if '/runtime-options?' in path and state.options_reads <= delay:
            # The source selection is unchanged but its publication is not usable yet.
            value['adapter_freshness'][document['request']['configuration']['adapter_id']] = 'STALE'
            for row in value['options']:
                row['can_configure'] = False
        return value

    state.mutate = delayed
    result = t.flow.apply(document, approval=document['review_revision'], timeout=5)
    assert result['state'] == 'configured'
    assert state.options_reads == delay + 1
    assert len(t.probes) == len(t.turns) == 1
    assert sum(method == 'POST' and path.endswith('installations:check') for method, path in t.calls) == 1
    assert sum(method == 'POST' and path.endswith('setup:test') for method, path in t.calls) == 1
    assert [row['state'] for row in t.saved] == ['review', 'approved', 'check_submitted', 'approved', 'test_submitted', 'finish', 'done']


@pytest.mark.parametrize('failure', ['post_deadline', 'get_deadline', 'unreachable', 'stale'])
def test_check_recovery_deadline_retains_checkpoint_without_test(check_recovery, failure):
    t, document, state = check_recovery
    if failure == 'post_deadline':
        state.post_elapsed = 2
    elif failure == 'unreachable':
        state.get_error = ConnectionError('SERVER_UNREACHABLE', 'Observation unavailable')
    else:
        def incomplete(path, value):
            if '/runtime-options?' in path:
                if failure == 'get_deadline':
                    state.now = 2
                else:
                    value['adapter_freshness'][document['request']['configuration']['adapter_id']] = 'STALE'
            return value
        state.mutate = incomplete
    with pytest.raises(ConnectionError) as caught:
        t.flow.apply(document, approval=document['review_revision'], timeout=2)
    assert caught.value.code == 'INSTALLATION_UNCONFIRMED'
    assert caught.value.possible_effect is True
    assert state.now == 2
    assert t.saved[-1]['state'] == 'check_submitted'
    assert not t.saved[-1].get('version_check_confirmed')
    assert len(t.probes) == 1 and t.turns == []
    assert not any(path.endswith('setup:test') for _, path in t.calls)

    # A later explicit invocation observes the same saved selection, never probes again.
    state.get_error = state.mutate = None
    result = t.flow.apply(deepcopy(t.saved[-1]), timeout=2)
    assert result['state'] == 'configured'
    assert len(t.probes) == len(t.turns) == 1
    assert sum(method == 'POST' and path.endswith('installations:check') for method, path in t.calls) == 1


@pytest.mark.parametrize('field', ['server', 'executor', 'adapter', 'candidate'])
def test_check_recovery_rejects_changed_identity_before_test(check_recovery, field):
    t, document, state = check_recovery

    def changed(path, value):
        if field == 'server' and path.endswith('/connections/me'):
            value['server_id'] = 'another-server'
        if '/runtime-options?' in path:
            if field == 'executor':
                value['executor_id'] = 'another-executor'
            elif field in ('adapter', 'candidate'):
                for row in value['options']:
                    row['adapter_id' if field == 'adapter' else 'candidate_ref'] = 'another-selection'
        return value

    state.mutate = changed
    with pytest.raises(ConnectionError):
        t.flow.apply(document, approval=document['review_revision'], timeout=2)
    assert t.saved[-1]['state'] == 'check_submitted'
    assert not document.get('version_check_confirmed')
    assert len(t.probes) == 1 and t.turns == []
    assert not any(path.endswith('setup:test') for _, path in t.calls)


@pytest.mark.parametrize('stage', ['post', 'get'])
def test_check_recovery_does_not_mask_definite_refusal(check_recovery, stage):
    t, document, state = check_recovery
    refusal = ConnectionError('PERMISSION_DENIED', 'Authority revoked', possible_effect=False)
    if stage == 'post':
        state.post_error = refusal
    else:
        state.get_error = refusal
    with pytest.raises(ConnectionError) as caught:
        t.flow.apply(document, approval=document['review_revision'], timeout=2)
    assert caught.value is refusal
    assert state.now == 0
    assert t.saved[-1]['state'] == 'check_submitted'
    assert len(t.probes) == (stage == 'get') and t.turns == []


def test_provider_home_separators_survive_finish_and_read_only_resume(terminal, tmp_path):
    t = terminal
    provider = tmp_path / 'provider-home'
    provider.mkdir()
    t.selection['provider_home'] = provider.as_posix()
    document = t.flow.review(t.selection)
    selected_home = document['selection']['provider_home']
    result = t.flow.apply(document, approval=document['review_revision'])
    assert result['state'] == 'configured'
    assert result['configuration']['folders']['provider_home'] == str(provider.resolve())
    assert document['selection']['provider_home'] == selected_home
    before = snapshot(t.deps)
    t.calls.clear()
    assert t.flow.apply(deepcopy(t.saved[-1])) == result
    assert all(method == 'GET' for method, _ in t.calls)
    assert snapshot(t.deps) == before and len(t.probes) == len(t.turns) == 1

    for different in (str(tmp_path / 'other-home'), 'provider-home',
                      str(provider / '..' / 'provider-home'), None):
        changed = deepcopy(document)
        # A missing canonical path is also a drift, not permission to skip it.
        if different is None:
            original_current = t.flow.current
            t.flow.current = lambda *args, **kwargs: original_current(*args, **kwargs) | {
                'folders': {'provider_home': None, 'workspace_root': t.selection['project']}}
        else:
            changed['selection']['provider_home'] = different
        with pytest.raises(ConnectionError) as failure:
            t.flow.observe(changed)
        assert failure.value.code == 'PROFILE_DRIFT'
    assert all(method == 'GET' for method, _ in t.calls)
    assert snapshot(t.deps) == before and len(t.turns) == 1


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


def test_interactive_connect_enters_work_only_after_configuration(terminal, tmp_path, monkeypatch, capsys):
    from okto_nexus.adapters.inbound.cli import work
    from okto_nexus.adapters.outbound.service_manager.context import read_json

    t = terminal
    service = SimpleNamespace(adapter=SimpleNamespace(home=tmp_path / 'terminal-home', host='127.0.0.1', port=8202),
        inspect=lambda: {'state': 'ready'}, ensure_running=lambda **kwargs: {'state': 'ready'})
    monkeypatch.setattr(connect, 'resolve_local_service', lambda args: service)
    monkeypatch.setattr(connect, 'LocalOperatorHTTP', lambda **kwargs: t.call)
    monkeypatch.setattr(connect.sys, 'stdin', SimpleNamespace(isatty=lambda: True))
    entered = []
    def enter(selected, profile, **kwargs):
        assert read_json(selected.adapter.home / 'terminal/profiles' / (profile + '.json'))['state'] == 'done'
        entered.append(profile)
        return 0
    monkeypatch.setattr(work, 'interactive_work', enter)
    args = ['--profile', 'interactive', '--agent', 'subject', '--project', t.selection['project']]
    assert connect.run_connect(args + ['--plan']) == 0
    assert entered == []
    review = read_json(service.adapter.home / 'terminal/profiles/interactive.json')
    assert connect.run_connect(args + ['--approve', review['review_revision']]) == 0
    assert entered == ['interactive']
    assert connect.run_connect(args + ['--no-chat']) == 0
    assert connect.run_connect(args + ['--json']) == 0
    assert entered == ['interactive']
    assert len(t.turns) == 1

"""QC Terminal facade against owned ASGI/SQLite and inert installation/model peers.

No real executable, provider, personal login, service registration or daemon is
started. Shared R4 fixtures retain their real canonical HTTP handlers.
"""
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest

_FIXTURES = str(Path(__file__).parents[1] / 'execution_r4')
if _FIXTURES not in sys.path:
    sys.path.insert(0, _FIXTURES)

from test_terminal_connect import terminal as terminal, checking as checking, local_setup as local_setup  # noqa: E402,F401
from test_public_connection_ids import public_request  # noqa: E402
from test_binding_operator import onboarding as onboarding, prepare_delegated  # noqa: E402,F401
from shutdown_diagnostics import install_shutdown_diagnostics  # noqa: E402
from okto_nexus.application.terminal_connection import ConnectionError, RemoteTerminalConnection  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_fixture_inventory_and_shutdown(monkeypatch):
    from types import SimpleNamespace
    from okto_nexus.bootstrap import embedded_inventory
    monkeypatch.setattr(embedded_inventory, 'discover_local_candidates', lambda **_: SimpleNamespace(candidates=()))
    install_shutdown_diagnostics(monkeypatch)


TABLES = ('agents', 'execution_bindings', 'agent_endpoints', 'runtime_execution_grants',
    'connection_setup_commits', 'execution_sessions', 'execution_operations',
    'agent_execution_policies', 'agent_runtime_overrides')


def snapshot(deps):
    with deps.connection_factory.unit_of_work(write=False) as uow:
        return {table: [tuple(row) for row in uow.connection.execute('SELECT * FROM ' + table + ' ORDER BY rowid')]
                for table in TABLES}


def rows(deps, table):
    with deps.connection_factory.unit_of_work(write=False) as uow:
        return [dict(row) for row in uow.connection.execute('SELECT * FROM ' + table + ' ORDER BY rowid')]


def public_review(t, setup, *, name='reviewer', workspace_id=None, agent='qc-new-agent'):
    _, request = public_request(setup, name=name, workspace_id=workspace_id)
    selection = deepcopy(t.selection) | dict(agent=agent, create_agent=True,
        setup_intent_id=request['client_intent_id'], workspace_id=workspace_id,
        public_connection=deepcopy(request['public_connection']))
    return t.flow.review(selection)


def posts(t):
    return Counter(path for method, path in t.calls if method == 'POST')


def test_new_public_review_reserve_precedes_single_test_and_resume_is_read_only(terminal, local_setup):
    t = terminal
    before = snapshot(t.deps)
    document = public_review(t, local_setup)
    assert document['request']['public_connection'] == document['review_request']['public_connection']
    assert 'public_connection' not in document['request']['configuration']
    assert snapshot(t.deps) == before and t.turns == t.probes == []
    with pytest.raises(ConnectionError, match='Approve'):
        t.flow.apply(document, approval='not-this-review')
    assert not posts(t) and not rows(t.deps, 'connection_public_ids')
    result = t.flow.apply(document, approval=document['review_revision'])
    assert result['state'] == 'configured' and result['public_connection']['connect_id'] == 'reviewer'
    assert result['public_connection']['state'] == 'bound'
    assert result['public_connection']['canonical_ref']['binding_id'] == result['binding_id']
    assert result['public_connection']['canonical_ref']['agent_id'] == 'qc-new-agent'
    assert result['session_state'] == 'not_checked' and result['work_state'] == 'not_submitted'
    paths = [path for method, path in t.calls if method == 'POST']
    assert next(i for i, path in enumerate(paths) if path.endswith('public-ids/reserve')) < next(i for i, path in enumerate(paths) if path.endswith('setup:test'))
    assert len(t.turns) == len(t.probes) == 1
    assert len(rows(t.deps, 'connection_public_ids')) == len(rows(t.deps, 'runtime_execution_grants')) == 1
    after, count = snapshot(t.deps), posts(t)
    assert t.flow.apply(deepcopy(t.saved[-1])) == result
    assert snapshot(t.deps) == after and posts(t) == count and len(t.turns) == 1


def test_public_collision_refuses_before_another_model_test_or_identity(terminal, local_setup):
    t = terminal
    first = public_review(t, local_setup)
    result = t.flow.apply(first, approval=first['review_revision'])
    before, turn_count = snapshot(t.deps), len(t.turns)
    second = public_review(t, local_setup, workspace_id=result['workspace_id'], agent='qc-second-agent')
    start = len(t.calls)
    with pytest.raises(ConnectionError):
        t.flow.apply(second, approval=second['review_revision'])
    assert not any(method == 'POST' and path.endswith('setup:test') for method, path in t.calls[start:])
    assert snapshot(t.deps) == before and len(t.turns) == turn_count
    assert len(rows(t.deps, 'connection_public_ids')) == 1


def test_lost_reservation_reply_recovers_same_intent_without_another_id(terminal, local_setup):
    t = terminal
    document = public_review(t, local_setup)
    t.fault.after = 'public-ids/reserve'
    with pytest.raises(ConnectionError, match='Injected'):
        t.flow.apply(document, approval=document['review_revision'])
    retained = deepcopy(t.saved[-1])
    assert retained['state'] == 'approved' and t.turns == []
    record = rows(t.deps, 'connection_public_ids')
    assert len(record) == 1 and record[0]['state'] == 'reserved'
    result = t.flow.apply(retained)
    assert result['public_connection']['connect_id'] == 'reviewer'
    final = rows(t.deps, 'connection_public_ids')
    assert len(final) == 1 and final[0]['reservation_ref'] == record[0]['reservation_ref']
    assert final[0]['client_intent_id'] == record[0]['client_intent_id']
    assert len(t.turns) == len(t.probes) == 1


def test_bound_reservation_recovers_existing_commit_before_any_repeated_test(terminal, local_setup):
    t = terminal
    document = public_review(t, local_setup)
    result = t.flow.apply(document, approval=document['review_revision'])
    retained = next(deepcopy(item) for item in reversed(t.saved) if item['state'] == 'approved')
    t.app.state.connection_tests.tests.clear()
    before, count = snapshot(t.deps), posts(t)
    recovered = t.flow.apply(retained)
    assert recovered == result and snapshot(t.deps) == before
    assert len(t.turns) == 1
    for path, number in posts(t).items():
        if path.endswith(('setup:test', 'setup:finish')):
            assert number == count[path] == 1


def test_lost_finish_recovers_same_public_receipt_without_native_replay(terminal, local_setup):
    t = terminal
    document = public_review(t, local_setup)
    t.fault.after = 'setup:finish'
    with pytest.raises(ConnectionError, match='Injected'):
        t.flow.apply(document, approval=document['review_revision'])
    assert t.saved[-1]['state'] == 'finish'
    public = rows(t.deps, 'connection_public_ids')[0]
    assert public['state'] == 'bound'
    t.app.state.connection_tests.tests.clear()
    before, count = snapshot(t.deps), posts(t)
    result = t.flow.apply(deepcopy(t.saved[-1]))
    assert result['public_connection']['connect_id'] == public['connect_id']
    assert result['binding_id'] == json.loads(public['canonical_ref_json'])['binding_id']
    assert snapshot(t.deps) == before and len(t.turns) == len(t.probes) == 1
    assert posts(t) == count


def test_local_disk_failure_after_commit_preserves_partial_metadata_and_repairs_only_shortcut(terminal, local_setup):
    t = terminal
    document = public_review(t, local_setup)
    original = t.flow.save
    def broken(value):
        if value['state'] == 'done':
            raise OSError('Synthetic local disk failure')
        original(value)
    t.flow.save = broken
    with pytest.raises(ConnectionError) as failure:
        t.flow.apply(document, approval=document['review_revision'])
    assert failure.value.code == 'CONFIGURED_SHORTCUT_PENDING' and failure.value.possible_effect is True
    assert failure.value.committed_public_connection['state'] == 'bound'
    assert failure.value.committed_public_connection['connect_id'] == 'reviewer'
    assert t.saved[-1]['state'] == 'finish'
    before, count = snapshot(t.deps), posts(t)
    t.flow.save = original
    recovered = t.flow.apply(deepcopy(t.saved[-1]))
    assert recovered['public_connection']['connect_id'] == 'reviewer'
    assert snapshot(t.deps) == before and posts(t) == count and len(t.turns) == 1


def test_legacy_association_requires_exact_review_and_changes_only_public_metadata(terminal):
    t = terminal
    first = t.flow.review(t.selection)
    result = t.flow.apply(first, approval=first['review_revision'])
    selection = deepcopy(first['selection']) | dict(binding_id=result['binding_id'], workspace_id=result['workspace_id'], public_connection={'connect_id': 'adopted'})
    document = t.flow.review_public_association(selection)
    before, count = snapshot(t.deps), posts(t)
    assert document['kind'] == 'public_id_association' and document['version_check_required'] is False
    changed = deepcopy(document)
    changed['request']['connect_id'] = 'different'
    with pytest.raises(ConnectionError, match='changed'):
        t.flow.apply(changed, approval=document['review_revision'])
    with pytest.raises(ConnectionError, match='Approve'):
        t.flow.apply(document, approval='not-this-review')
    assert snapshot(t.deps) == before and posts(t) == count
    adopted = t.flow.apply(document, approval=document['review_revision'])
    assert adopted['public_connection']['connect_id'] == 'adopted'
    assert adopted['binding_id'] == result['binding_id'] and snapshot(t.deps) == before
    assert len(t.turns) == len(t.probes) == 1
    assert sum(path.endswith('public-ids/associate-existing') for method, path in t.calls if method == 'POST') == 1


@pytest.mark.parametrize('onboarding', ['human-operator'], indirect=True)
def test_remote_adoption_and_observation_preserve_exact_scope_without_operator_root_authority(onboarding, tmp_path, monkeypatch):
    deps, client, headers, prepare = onboarding
    _, apply, approval_id = prepare_delegated(client, headers, prepare)
    approved = client.post('/api/v1/approvals/' + approval_id + '/decision', json={'decision': 'approve'})
    assert approved.status_code == 200, approved.text
    response = client.post('/v1/connections/bindings:apply', json=apply, headers=headers['subject'])
    assert response.status_code == 200, response.text
    binding = response.json()
    calls, saved = [], []
    def call(method, path, body=None):
        calls.append((method, path, deepcopy(body)))
        response = client.request(method, path, json=body, headers={'X-Nexus-UI': '1'})
        value = response.json()
        if response.status_code >= 400:
            error = value['error']
            raise ConnectionError(error['code'], error['message'], stage=error.get('stage', 'http'))
        return value
    flow = RemoteTerminalConnection(call, lambda value: saved.append(deepcopy(value)))
    root = str(tmp_path / 'operator-local-path-not-created')
    selection = dict(agent='subject', client='codex', project=root, label='Remote project', workspace_id=binding['workspace_id'],
        binding_id=binding['binding_id'], candidate_ref=binding['candidate_ref'], provider_home=None, public_connection={'connect_id': 'remote-reviewer'})
    def forbidden(*args, **kwargs):
        pytest.fail('Operator CWD and Git cannot establish remote execution root authority')
    monkeypatch.setattr('okto_nexus.application.connection_project_context.directory_identity', forbidden)
    monkeypatch.setattr('okto_nexus.application.terminal_connection._same_local_path', forbidden)
    before = snapshot(deps)
    document = flow.review_public_association(selection)
    assert document['remote_scope']['binding_id'] == binding['binding_id']
    result = flow.apply(document, approval=document['review_revision'])
    assert result['execution_location'] == 'remote' and result['public_connection']['connect_id'] == 'remote-reviewer'
    assert result['public_connection']['canonical_ref']['binding_id'] == binding['binding_id']
    assert snapshot(deps) == before and document['selection']['project'] == root
    assert root not in json.dumps([(path, body) for _, path, body in calls])
    previous = len(calls)
    assert flow.apply(deepcopy(saved[-1])) == result
    assert all(method == 'GET' for method, _, _ in calls[previous:]) and snapshot(deps) == before

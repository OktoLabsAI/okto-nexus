"""Reviewed terminal renewal keeps canonical grants, leases and receipts distinct."""
import json
from types import SimpleNamespace
import time

import pytest

import test_terminal_work as work_fixtures
from okto_nexus.application.terminal_connection import ConnectionError, PREFIX
from okto_nexus.application.terminal_work import TerminalWork

work = work_fixtures.work
connected_local = work_fixtures.connected_local
local_setup = work_fixtures.local_setup
qualified_contract = work_fixtures.qualified_contract


def rows(t, table):
    with t.deps.connection_factory.unit_of_work(write=False) as uow:
        return [dict(row) for row in uow.connection.execute('SELECT * FROM ' + table)]


def disable_grants(t, state):
    change = {'expired': "expires_at='2020-01-01T00:00:00.000000Z',no_expiry=0",
              'exhausted': 'used_executions=max_executions,unlimited_actions=0',
              'revoked': "revoked_at='2020-01-01T00:00:00.000000Z',revision=revision+1",
              'limited': "actions='[\"open\"]'"}[state]
    with t.deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute('UPDATE runtime_execution_grants SET ' + change)


@pytest.mark.parametrize('state', ['expired', 'exhausted', 'revoked', 'limited'])
def test_renewal_is_explicit_bounded_and_new_opening_uses_new_grant(work, state):
    t = work
    disable_grants(t, state)
    before = rows(t, 'runtime_execution_grants')
    binding = rows(t, 'execution_bindings')
    review = t.flow.authorization_review(minutes=12, max_executions=3)
    assert review['can_issue'] and {g['state'] for g in review['current_grants']} == {'available' if state == 'limited' else state}
    assert rows(t, 'runtime_execution_grants') == before and t.native.opens == 0
    assert 'credential_binding' not in json.dumps(review) and 'api_key_hash' not in json.dumps(review)
    with pytest.raises(ConnectionError, match='Approve'):
        t.flow.authorize(approval='wrong')
    receipt = t.flow.authorize(approval=review['review_revision'])
    grant = receipt['result']['grant']
    assert grant['max_executions'] == 3 and grant['expires_at'] == review['request']['expires_at']
    assert len(rows(t, 'runtime_execution_grants')) == 2
    assert rows(t, 'runtime_execution_grants')[0] == before[0]
    assert rows(t, 'execution_bindings') == binding and t.native.opens == 0
    operation = t.flow.submit('Explicit renewed work', new_session=True)
    work_fixtures.complete(t, operation)
    assert t.flow.observe()['state'] == 'completed'
    with t.deps.connection_factory.unit_of_work(write=False) as uow:
        opened = uow.connection.execute('SELECT grant_id FROM execution_leases WHERE session_id=? ORDER BY lease_serial DESC',
                                        (operation['scope']['session_id'],)).fetchone()
        assert opened[0] == grant['grant_id']


def test_available_grant_is_observed_without_duplicate_authority(work):
    t = work
    before = rows(t, 'runtime_execution_grants')
    review = t.flow.authorization_review()
    assert not review['can_issue']
    with pytest.raises(ConnectionError) as refused:
        t.flow.authorize(approval=review['review_revision'])
    assert refused.value.code == 'AUTHORIZATION_AVAILABLE'
    with pytest.raises(ConnectionError, match='already has'):
        t.call('POST', PREFIX + '/connections/authorizations:issue', review['request'])
    assert rows(t, 'runtime_execution_grants') == before and t.native.opens == 0


def test_unclassified_issue_failure_keeps_effect_uncertain_until_receipt_recovery(work):
    t = work
    disable_grants(t, 'expired')
    review = t.flow.authorization_review()
    def failure(method, path, body=None):
        result = t.call(method, path, body)
        if path.endswith('authorizations:issue'):
            raise ConnectionError('DB_ERROR', 'Injected failure after commit')
        return result
    t.flow.call = failure
    with pytest.raises(ConnectionError) as unknown:
        t.flow.authorize(approval=review['review_revision'])
    assert unknown.value.possible_effect and t.saved[-1]['authorization']['state'] == 'submitted'
    t.flow.call = t.call
    assert t.flow.authorize()['state'] == 'authorization_committed'
    assert len(rows(t, 'runtime_execution_grants')) == 2


@pytest.mark.parametrize('lost', ['before', 'after'])
def test_uncertain_issue_recovers_same_receipt_even_after_later_revocation(work, lost):
    t = work
    disable_grants(t, 'expired')
    review = t.flow.authorization_review()
    setattr(t.fault, lost, 'authorizations:issue')
    with pytest.raises(ConnectionError):
        t.flow.authorize(approval=review['review_revision'])
    assert t.saved[-1]['authorization']['state'] == 'submitted'
    reopened = TerminalWork(t.call, t.save, t.connection, t.saved[-1])
    receipt = reopened.authorization_review()
    assert receipt['state'] == 'authorization_committed'
    assert len(rows(t, 'runtime_execution_grants')) == 2
    assert len(rows(t, 'connection_authorization_receipts')) == 1
    disable_grants(t, 'revoked')
    before = rows(t, 'runtime_execution_grants')
    assert reopened.authorize() == receipt
    assert rows(t, 'runtime_execution_grants') == before and t.native.opens == 0


@pytest.mark.parametrize('change', ['endpoint', 'credential', 'grant', 'policy'])
def test_changed_review_cannot_issue_new_authority(work, change):
    t = work
    disable_grants(t, 'expired')
    review = t.flow.authorization_review()
    with t.deps.connection_factory.unit_of_work() as uow:
        if change == 'endpoint':
            uow.connection.execute('UPDATE agent_endpoints SET revision=revision+1')
        elif change == 'credential':
            uow.connection.execute("UPDATE agents SET api_key_hash='rotated' WHERE agent_id='subject'")
        elif change == 'grant':
            uow.connection.execute('UPDATE runtime_execution_grants SET revision=revision+1')
        else:
            uow.connection.execute('UPDATE runtime_policy_defaults SET revision=revision+1,runtime_enabled=0')
    before = rows(t, 'runtime_execution_grants')
    with pytest.raises(ConnectionError):
        t.call('POST', PREFIX + '/connections/authorizations:issue', review['request'])
    assert rows(t, 'runtime_execution_grants') == before
    assert rows(t, 'connection_authorization_receipts') == [] and t.native.opens == 0


def test_two_distinct_reviews_and_changed_request_id_do_not_stack_grants(work):
    t = work
    disable_grants(t, 'exhausted')
    first = t.flow.authorization_review()
    second = t.flow.authorization_review()
    receipt = t.call('POST', PREFIX + '/connections/authorizations:issue', first['request'])
    with pytest.raises(ConnectionError, match='changed'):
        t.call('POST', PREFIX + '/connections/authorizations:issue', second['request'])
    changed = dict(first['request'], max_executions=100)
    with pytest.raises(ConnectionError, match='different content'):
        t.call('POST', PREFIX + '/connections/authorizations:issue', changed)
    assert t.call('POST', PREFIX + '/connections/authorizations:recover', first['request']) == receipt
    assert len(rows(t, 'runtime_execution_grants')) == 2


def test_late_receipt_failure_rolls_back_grant_and_same_request_can_retry(work):
    t = work
    disable_grants(t, 'expired')
    review = t.flow.authorization_review()
    before = rows(t, 'runtime_execution_grants')
    with t.deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("CREATE TRIGGER refuse_authorization BEFORE INSERT ON connection_authorization_receipts "
                               "BEGIN SELECT RAISE(ABORT, 'injected receipt failure'); END")
    with pytest.raises(ConnectionError):
        t.flow.authorize(approval=review['review_revision'])
    assert rows(t, 'runtime_execution_grants') == before
    with t.deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute('DROP TRIGGER refuse_authorization')
    assert t.flow.authorize()['state'] == 'authorization_committed'
    assert len(rows(t, 'runtime_execution_grants')) == 2


def test_concurrent_same_request_issues_one_grant(work):
    from concurrent.futures import ThreadPoolExecutor
    t = work
    disable_grants(t, 'expired')
    review = t.flow.authorization_review()
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(t.call, 'POST', PREFIX + '/connections/authorizations:issue', review['request']) for _ in range(2)]
        receipts = [future.result(timeout=20) for future in futures]
    assert receipts[0] == receipts[1]
    assert len(rows(t, 'runtime_execution_grants')) == 2
    assert len(rows(t, 'connection_authorization_receipts')) == 1


def test_recovery_after_project_drift_reads_receipt_without_reapplying_profile(work):
    t = work
    disable_grants(t, 'expired')
    review = t.flow.authorization_review()
    t.fault.after = 'authorizations:issue'
    with pytest.raises(ConnectionError):
        t.flow.authorize(approval=review['review_revision'])
    with t.deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE execution_local_realizations SET local_record_json="
                               "json_set(local_record_json,'$.root.path','/changed/project')")
    before = rows(t, 'runtime_execution_grants'), rows(t, 'execution_local_realizations')
    with pytest.raises(ConnectionError) as drift:
        t.flow.binding()
    assert drift.value.code == 'PROFILE_DRIFT'
    reopened = TerminalWork(t.call, t.save, t.connection, t.saved[-1])
    assert reopened.authorize()['state'] == 'authorization_committed'
    assert (rows(t, 'runtime_execution_grants'), rows(t, 'execution_local_realizations')) == before


def test_expired_review_does_not_extend_authorization_deadline(work, monkeypatch):
    from okto_nexus.domain.base import iso_plus
    t = work
    disable_grants(t, 'expired')
    review = t.flow.authorization_review(minutes=1)
    future = iso_plus(review['request']['expires_at'], 1)
    monkeypatch.setattr(t.deps.clock, 'now_iso', lambda: future)
    with pytest.raises(ConnectionError):
        t.call('POST', PREFIX + '/connections/authorizations:issue', review['request'])
    assert len(rows(t, 'runtime_execution_grants')) == 1
    assert rows(t, 'connection_authorization_receipts') == []


def test_participant_cannot_review_issue_or_recover_project_authority(work):
    t = work
    disable_grants(t, 'expired')
    review = t.flow.authorization_review()
    for stage in ('review', 'issue', 'recover'):
        body = dict(binding_id=t.binding['binding_id'], client_request_id='participant') if stage == 'review' else review['request']
        response = t.setup[2].post(PREFIX + '/connections/authorizations:' + stage,
                                  json=body, headers=t.setup[3]['subject'])
        assert response.status_code == 403, response.text
    assert len(rows(t, 'runtime_execution_grants')) == 1 and rows(t, 'connection_authorization_receipts') == []


def test_renewal_does_not_rebind_or_close_an_exhausted_live_session(work):
    t = work
    operation = t.flow.submit('First work')
    work_fixtures.complete(t, operation)
    deadline = time.monotonic() + 10
    while t.flow.observe()['state'] != 'completed':
        assert time.monotonic() < deadline
        time.sleep(.03)
    disable_grants(t, 'exhausted')
    before = rows(t, 'execution_leases'), rows(t, 'execution_sessions')
    review = t.flow.authorization_review()
    t.flow.authorize(approval=review['review_revision'])
    assert (rows(t, 'execution_leases'), rows(t, 'execution_sessions')) == before
    assert t.native.opens == 1 and not t.native.native.stopped
    # The original lease still identifies the exhausted source grant.
    from okto_nexus.bootstrap.execution_authority import build_execution_access
    from okto_nexus.domain.runtime_context import RuntimeRequestContext
    from okto_nexus.errors import OktoNexusError
    with t.deps.connection_factory.unit_of_work() as uow:
        actor = t.deps.repos.agents.get(uow, 'subject')
        context = RuntimeRequestContext('subject', 'agent_key', credential_binding=actor.api_key_hash,
                                        execution_grant_id=before[0][0]['grant_id'])
        with pytest.raises(OktoNexusError):
            build_execution_access(t.deps).authorize(context, action='send', endpoint_id=t.binding['endpoint_id'], uow=uow)
    closed = t.flow.submit(action='close')
    work_fixtures.wait_receipt(t.setup, closed, stages=('SUCCEEDED',))
    assert t.native.native.stopped


def test_cli_review_accept_and_recover_share_saved_request(work, tmp_path, monkeypatch, capsys):
    from okto_nexus.adapters.inbound.cli import work as cli
    from okto_nexus.adapters.outbound.service_manager.context import atomic_json
    t = work
    disable_grants(t, 'expired')
    home = tmp_path / 'cli'
    profile = home / 'terminal/profiles/project.json'
    profile.parent.mkdir(parents=True)
    atomic_json(profile, t.connection)
    service = SimpleNamespace(adapter=SimpleNamespace(home=home, host='127.0.0.1', port=8202),
                              inspect=lambda: {'state': 'ready'})
    monkeypatch.setattr(cli, 'resolve_local_service', lambda args: service)
    monkeypatch.setattr(cli, 'LocalOperatorHTTP', lambda **kwargs: t.call)
    assert cli.run_work(['authorize', '--profile', 'project', '--json', '--minutes', '30', '--actions', '5']) == 0
    review = json.loads(capsys.readouterr().out)
    assert review['can_issue'] and len(rows(t, 'runtime_execution_grants')) == 1
    args = ['authorize', '--profile', 'project', '--json', '--review', review['review_revision']]
    t.fault.after = 'authorizations:issue'
    assert cli.run_work(args) == 3
    assert json.loads(capsys.readouterr().out)['possible_effect']
    assert cli.run_work(['authorize', '--profile', 'project', '--json']) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['state'] == 'authorization_committed' and result['result']['grant']['max_executions'] == 5
    assert len(rows(t, 'runtime_execution_grants')) == 2

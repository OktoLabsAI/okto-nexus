"""Real canonical reads distinguish setup, authority and completed work."""
from copy import deepcopy
import json

import pytest

import test_terminal_work
import test_terminal_connect
import test_remote_operator_terminal
from test_connection_setup_recovery import snapshot
from okto_nexus.application.project_diagnostics import ProjectDiagnostics, DiagnosticReads, inspect_project
from okto_nexus.application.terminal_connection import ConnectionError

work = test_terminal_work.work
connected_local = test_terminal_work.connected_local
local_setup = test_terminal_work.local_setup
qualified_contract = test_terminal_work.qualified_contract
remote = test_remote_operator_terminal.remote
terminal = test_terminal_connect.terminal
checking = test_terminal_connect.checking


def inspect(t, checkpoint=None):
    report = ProjectDiagnostics('project')
    inspect_project(report, DiagnosticReads(t.call, timeout=30), t.connection, checkpoint)
    return report.result(), {key: value for key, value in report.checks.items()}


def test_ready_connection_does_not_prove_provider_login_participation_or_work(work):
    t = work
    before, calls = snapshot(t.deps), len(t.calls)
    report, rows = inspect(t)
    assert rows['project_identity']['status'] == rows['managed_connection']['status'] == 'PASS'
    assert rows['runtime_eligibility']['status'] == 'UNKNOWN'
    assert rows['runtime_eligibility']['evidence']['technical_state'] == 'NOT_PROBED'
    assert rows['runtime_eligibility']['evidence']['technical_reasons'] == ['no_build_observation']
    for key in ('provider_login', 'mcp_negotiation', 'coordination_participation', 'handoff_test', 'work_result'):
        assert rows[key]['status'] == 'UNKNOWN'
    assert rows['client_configuration']['status'] == 'NOT_APPLICABLE'
    assert snapshot(t.deps) == before and t.native.opens == 0
    assert all(method == 'GET' for method, _ in t.calls[calls:])


def test_current_open_eligibility_does_not_run_another_probe_or_turn(terminal):
    t = terminal
    document = t.flow.review(t.selection)
    t.flow.apply(document, approval=document['review_revision'])
    before, calls = snapshot(t.deps), len(t.calls)
    report = ProjectDiagnostics('project')
    inspect_project(report, DiagnosticReads(t.call, timeout=30), t.saved[-1])
    assert report.checks['runtime_eligibility']['status'] == 'PASS', report.result()
    assert report.checks['work_result']['status'] == report.checks['provider_login']['status'] == 'UNKNOWN'
    assert snapshot(t.deps) == before and len(t.probes) == len(t.turns) == 1
    assert all(method == 'GET' for method, _ in t.calls[calls:])


def test_pending_new_identity_is_not_created_or_inferred_from_a_missing_receipt(terminal):
    t = terminal
    document = t.flow.review(dict(t.selection, agent='new-project', create_agent=True))
    before, calls = snapshot(t.deps), len(t.calls)
    report = ProjectDiagnostics('project')
    inspect_project(report, DiagnosticReads(t.call, timeout=30), document)
    assert report.checks['project_identity']['code'] == 'IDENTITY_CREATION_UNCONFIRMED'
    assert report.checks['managed_connection']['code'] == 'SETUP_INCOMPLETE'
    assert snapshot(t.deps) == before and t.probes == t.turns == []
    assert all(method == 'GET' for method, _ in t.calls[calls:])


def test_revoked_grant_is_refused_and_never_renewed_by_diagnosis(work):
    t = work
    with t.deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE runtime_execution_grants SET revoked_at=?", (t.deps.clock.now_iso(),))
    before = snapshot(t.deps)
    _, rows = inspect(t)
    assert rows['managed_connection']['status'] == 'PASS'
    assert rows['runtime_eligibility']['status'] == 'FAIL'
    assert 'AUTHORIZATION_REQUIRED' in rows['runtime_eligibility']['evidence']['policy_reasons']
    assert snapshot(t.deps) == before and t.native.opens == 0


def test_completed_work_uses_exact_receipt_without_printing_content_or_mutating_checkpoint(work):
    t = work
    operation = t.flow.submit('nxs_private-request')
    test_terminal_work.complete(t, operation, 'nxs_private-result')
    checkpoint = deepcopy(t.saved[-1])
    before, saved_count, calls = snapshot(t.deps), len(t.saved), len(t.calls)
    report, rows = inspect(t, checkpoint)
    assert rows['work_result']['status'] == 'PASS', json.dumps(rows['work_result'])
    assert rows['managed_session']['status'] == 'PASS'
    assert 'nxs_private' not in json.dumps(report)
    assert rows['mcp_negotiation']['status'] == rows['handoff_test']['status'] == 'UNKNOWN'
    assert snapshot(t.deps) == before and len(t.saved) == saved_count and checkpoint == t.saved[-1]
    assert all(method == 'GET' for method, _ in t.calls[calls:]) and t.native.opens == 1


def test_ready_session_open_is_not_a_productive_result(work):
    t = work
    operation = t.flow.submit()
    test_terminal_work.wait_receipt(t.setup, operation)
    checkpoint = deepcopy(t.saved[-1])
    before, calls = snapshot(t.deps), len(t.calls)
    report, rows = inspect(t, checkpoint)
    assert rows['managed_session']['status'] == 'PASS', report
    assert rows['work_result']['status'] == 'UNKNOWN'
    assert rows['work_result']['evidence']['operation_ids'] == []
    assert snapshot(t.deps) == before and checkpoint == t.saved[-1]
    assert all(method == 'GET' for method, _ in t.calls[calls:])
    assert t.native.opens == 1 and t.native.native.sent == []


def test_lost_submission_is_only_observed_never_recovered_or_submitted(work):
    t = work
    t.fault.before = '/runtime/operations'
    with pytest.raises(ConnectionError):
        t.flow.submit('Unsent private work')
    checkpoint = deepcopy(t.saved[-1])
    before, calls = snapshot(t.deps), len(t.calls)
    report, rows = inspect(t, checkpoint)
    assert rows['work_result']['status'] == 'UNKNOWN', report
    assert rows['work_result']['evidence']['state'] == 'submission_unconfirmed'
    assert snapshot(t.deps) == before and t.native.opens == 0 and checkpoint == t.saved[-1]
    assert all(method == 'GET' for method, _ in t.calls[calls:])


def test_remote_cli_reads_current_human_authority_and_binding_without_local_lifecycle(remote, monkeypatch, capsys):
    from okto_nexus.adapters.inbound.cli import doctor
    r = remote
    document = test_remote_operator_terminal.project(r) | {'format': 1}
    path = r.profile.home / 'terminal/profiles/project.json'
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(document), encoding='utf-8')
    before, profile_bytes, vault = snapshot(r.t.deps), path.read_bytes(), dict(r.vault.values)
    monkeypatch.setattr(doctor, 'resolve_local_service', lambda *a, **k: pytest.fail('remote diagnosis used local service'))
    r.bridge.calls.clear()
    assert doctor.run_doctor(['--profile', 'project', '--home', str(r.profile.home), '--check-server', '--json']) == 0
    report = json.loads(capsys.readouterr().out)
    rows = {row['id']: row for row in report['checks']}
    assert rows['local_service']['status'] == 'NOT_APPLICABLE'
    assert rows['operator_authentication']['status'] == rows['managed_connection']['status'] == 'PASS'
    assert all(request.method == 'GET' for request in r.bridge.calls)
    assert snapshot(r.t.deps) == before and path.read_bytes() == profile_bytes and r.vault.values == vault
    assert r.t.native.opens == 0
    assert all(secret not in json.dumps(report) for secret in vault.values())
    r.profile.client()('POST', '/api/v1/operator-auth/logout')
    r.bridge.calls.clear()
    assert doctor.run_doctor(['--profile', 'project', '--home', str(r.profile.home), '--check-server', '--json']) == 3
    refused = json.loads(capsys.readouterr().out)
    assert next(row for row in refused['checks'] if row['id'] == 'operator_authentication')['status'] == 'FAIL'
    assert next(row for row in refused['checks'] if row['id'] == 'server_reachability')['status'] == 'PASS'
    assert all(request.method == 'GET' for request in r.bridge.calls)
    assert path.read_bytes() == profile_bytes and r.vault.values == vault

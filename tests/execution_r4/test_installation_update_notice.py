"""Installation succession: operator notice and execution log history (#89)."""
from test_open_bootstrap import opening  # noqa: F401

from okto_nexus.adapters.inbound.mcp.tools.messages import build_service
from okto_nexus.application.execution_log import read_execution_log
from okto_nexus.application.execution_release_notifications import (
    InstallationUpdate, notify_installation_update)


def bound(deps):
    with deps.connection_factory.unit_of_work(write=False) as uow:
        return dict(uow.connection.execute(
            "SELECT b.server_id,b.executor_id,b.candidate_ref,ep.agent_id,ep.workspace_id,ep.adapter_id,b.endpoint_id "
            "FROM execution_bindings b JOIN agent_endpoints ep USING(endpoint_id) LIMIT 1").fetchone())


def update_for(row, **fields):
    values = dict(server_id=row['server_id'], executor_id=row['executor_id'], stable_ref=row['candidate_ref'],
        decision='held', reason='downgrade', from_version='2.1.309', to_version='2.1.306',
        from_build_identity='sha256:' + 'a' * 64, to_build_identity='sha256:' + 'b' * 64)
    values.update(fields)
    return InstallationUpdate(**values)


def ensure_operator(deps):
    with deps.connection_factory.unit_of_work() as uow:
        if deps.repos.agents.get(uow, 'operator') is None:
            uow.connection.execute("PRAGMA foreign_keys=OFF")
            cols = [c[1] for c in uow.connection.execute("PRAGMA table_info(agents)")]
            sample = dict(uow.connection.execute("SELECT * FROM agents LIMIT 1").fetchone())
            sample.update(agent_id='operator')
            uow.connection.execute(f"INSERT INTO agents({','.join(cols)}) VALUES({','.join('?' * len(cols))})",
                [sample[c] for c in cols])


def operator_notices(deps):
    with deps.connection_factory.unit_of_work(write=False) as uow:
        return [dict(r) for r in uow.connection.execute(
            "SELECT m.message_id,m.workspace_id,m.body FROM message_deliveries d JOIN messages m USING(message_id) "
            "WHERE d.recipient_agent_id='operator' AND m.message_id LIKE 'msg_installation_update_%'")]


def test_two_runs_give_one_message_and_one_delivery_per_workspace(opening):
    deps = opening[0]
    row = bound(deps)
    ensure_operator(deps)
    messages = build_service(deps)
    update = update_for(row)
    assert notify_installation_update(deps, messages, update) == 1
    assert notify_installation_update(deps, messages, update) == 0
    found = operator_notices(deps)
    assert len(found) == 1 and found[0]['workspace_id'] == row['workspace_id']
    body = found[0]['body']
    for text in (row['agent_id'], '2.1.309', '2.1.306', 'a' * 12, 'b' * 12, 'held', 'downgrade'):
        assert text in body
    assert 'a' * 13 not in body and 'sha256' not in body
    accepted = update_for(row, decision='accepted', reason=None)
    assert notify_installation_update(deps, messages, accepted) == 1
    assert len(operator_notices(deps)) == 2


def test_log_union_shows_succession_history(opening):
    deps = opening[0]
    row = bound(deps)
    with deps.connection_factory.unit_of_work() as uow:
        for decision, reason in (('held', 'downgrade'), ('accepted', 'newer_version')):
            uow.connection.execute(
                "INSERT INTO execution_installation_succession(server_id,executor_id,adapter_id,stable_ref,decision,"
                "reason,policy,policy_source,decided_by,from_version,to_version,to_build_identity,decided_at) "
                "VALUES(?,?,?,?,?,?,'follow','hub','hub','2.1.309','2.1.310',?,'2030-01-01T00:00:00Z')",
                (row['server_id'], row['executor_id'], row['adapter_id'], row['candidate_ref'],
                 decision, reason, decision))
    items = read_execution_log(deps.connection_factory, agent_id=row['agent_id'])['items']
    mine = {i['code']: i for i in items if i['source'] == 'installation update'}
    assert set(mine) == {'INSTALLATION_UPDATE_HELD', 'INSTALLATION_UPDATE_ACCEPTED'}
    assert mine['INSTALLATION_UPDATE_HELD']['severity'] == 'warning'
    assert mine['INSTALLATION_UPDATE_ACCEPTED']['severity'] == 'info'
    assert 'downgrade' in mine['INSTALLATION_UPDATE_HELD']['details']['message']
    assert mine['INSTALLATION_UPDATE_HELD']['workspace_id'] == row['workspace_id']

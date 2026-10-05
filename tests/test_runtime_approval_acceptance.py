"""Repeated human decisions cannot create multiple transport executions."""
import threading
from concurrent.futures import ThreadPoolExecutor

from test_governance import _attach, _rule
from test_pr34_remediation import runtime as runtime_fixture, send_message
from test_runtime_commands import codex_session
from test_runtime_handoff_dispatch import wait_result

runtime = runtime_fixture


def test_pending_message_and_concurrent_approval_have_one_native_execution(runtime):
    deps, client, _, _, operator, _ = runtime
    deps.config.feature_hitl = True
    sid = codex_session(runtime)
    _attach(deps, "caller", governance=[_rule("message_create", "require_approval")])
    pending = send_message(runtime, body="approval barrier fixture")
    assert pending["status"] == "pending_approval", pending
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT count(*) FROM delivery_outbox").fetchone()[0] == 0
        assert uow.connection.execute("SELECT count(*) FROM messages WHERE body='approval barrier fixture'").fetchone()[0] == 0
    assert not any(e.native_event == "turn/started" for e in deps.harness_supervisor.replay_events(sid))

    barrier = threading.Barrier(3)
    path = f"/api/v1/approvals/{pending['approval_id']}/decision"

    def decide():
        barrier.wait(timeout=5)
        return client.post(path, headers={"x-api-key": operator}, json={"decision": "approve"})

    with ThreadPoolExecutor(max_workers=3) as pool:
        replies = list(pool.map(lambda _: decide(), range(3)))
    assert sorted(reply.status_code for reply in replies) == [200, 409, 409], [r.text for r in replies]
    executed = next(r.json()["data"]["executed_result"] for r in replies if r.status_code == 200)
    op = executed["runtime_operations"][0]
    assert "approval barrier fixture" in wait_result(runtime, op)["output_text"]
    repeat = client.post(path, headers={"x-api-key": operator}, json={"decision": "approve"})
    assert repeat.status_code == 409, repeat.text
    deps.runtime_dispatcher.scan_once()
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT count(*) FROM delivery_outbox").fetchone()[0] == 1
        assert uow.connection.execute("SELECT count(*) FROM messages WHERE body='approval barrier fixture'").fetchone()[0] == 1
        assert uow.connection.execute("SELECT count(*) FROM runtime_results WHERE operation_id=?", (op,)).fetchone()[0] == 1
    assert sum(e.native_event == "turn/started" for e in deps.harness_supervisor.replay_events(sid)) == 1

"""Transport capacity cannot grow forever or silently drop canonical delivery."""
from test_pr34_remediation import runtime as runtime_fixture, open_rest, send_message, tool
from concurrent.futures import ThreadPoolExecutor
import threading

runtime = runtime_fixture


def test_outbox_recipient_backlog_is_bounded_without_partial_message_commit(runtime, monkeypatch):
    deps, client, root, peers, operator, caller = runtime
    assert open_rest(runtime).status_code == 200
    monkeypatch.setattr(deps.runtime_dispatcher, "scan_once", lambda: None)
    # Keep the independent causal rate limit from masking accumulated backlog.
    deps.config.max_new_roots_per_agent_per_minute = 256
    queued = [send_message(runtime) for _ in range(32)]
    overflow = tool(client, caller, "message_create", {"project_root": root, "from_agent_id": "caller",
        "subject": "overflow", "body": "not accepted", "target": {"strategy": "direct", "agent_id": "worker"}})
    assert not overflow["ok"], "Unbounded executable inbox backlog was admitted"
    assert overflow["error"]["code"] == "QUOTA_EXCEEDED"
    with deps.connection_factory.unit_of_work(write=False) as uow:
        for table in ("messages", "message_deliveries", "delivery_outbox"):
            assert uow.connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 32
        assert uow.connection.execute("SELECT count(*) FROM message_deliveries WHERE consumer_kind='push'").fetchone()[0] == 32
    # Pure logical delivery without an executor still works; no silent native
    # fallback or dropped accepted message is used to obtain capacity.
    send_message(runtime, target={"strategy": "direct", "agent_id": "caller"})
    assert all(not peer.sent for peer in peers)
    from test_runtime_operation_reconciliation import recovery
    with deps.connection_factory.unit_of_work(write=False) as uow:
        row = deps.runtime_dispatcher.repo.get(uow, queued[0]["runtime_operations"][0])
    released = client.post("/api/v1/harness/outbox", headers={"x-api-key": operator},
        json=recovery(row, action="cancel_pending", acknowledge_duplicate_risk=False))
    assert released.status_code == 200, released.text
    assert send_message(runtime)["runtime_operations"], "Explicit safe cancellation must release capacity"


def test_outbox_byte_budget_rejects_before_any_canonical_commit(runtime):
    deps, client, root, _, _, caller = runtime
    assert open_rest(runtime).status_code == 200
    deps.runtime_dispatcher.quiesce()
    deps.config.max_inline_bytes = 8 * 1024 * 1024
    result = tool(client, caller, "message_create", {"project_root": root, "from_agent_id": "caller",
        "subject": "byte budget", "body": "x" * (4 * 1024 * 1024),
        "target": {"strategy": "direct", "agent_id": "worker"}})
    assert not result["ok"] and result["error"]["code"] == "QUOTA_EXCEEDED", result
    assert "backlog capacity" in result["error"]["message"]
    with deps.connection_factory.unit_of_work(write=False) as uow:
        for table in ("messages", "message_deliveries", "delivery_outbox"):
            assert uow.connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0


def test_full_transport_backlog_rolls_back_managed_claim_and_grant(runtime, monkeypatch):
    from test_runtime_handoff_dispatch import work, claim
    from test_runtime_grants import issue
    deps, _, _, _, _, caller = runtime
    assert open_rest(runtime).status_code == 200
    monkeypatch.setattr(deps.runtime_dispatcher, "scan_once", lambda: None)
    deps.config.max_new_roots_per_agent_per_minute = 256
    for _ in range(32):
        send_message(runtime)
    hid, _ = work(runtime)
    grant = issue(runtime, ["execute_work"], endpoint_id="endpoint-codex")
    response = claim(runtime, hid, grant, caller)
    assert not response["ok"] and response["error"]["code"] == "QUOTA_EXCEEDED", response
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT status FROM handoffs WHERE handoff_id=?", (hid,)).fetchone()[0] == "OPEN"
        assert uow.connection.execute("SELECT used_executions FROM runtime_execution_grants WHERE grant_id=?",
            (grant["grant_id"],)).fetchone()[0] == 0
        assert not uow.connection.execute("SELECT 1 FROM runtime_handoff_bindings WHERE handoff_id=?", (hid,)).fetchone()
        assert uow.connection.execute("SELECT count(*) FROM delivery_outbox").fetchone()[0] == 32


def test_concurrent_admission_reserves_only_the_last_available_slot(runtime, monkeypatch):
    deps, client, root, _, _, caller = runtime
    assert open_rest(runtime).status_code == 200
    monkeypatch.setattr(deps.runtime_dispatcher, "scan_once", lambda: None)
    deps.config.max_new_roots_per_agent_per_minute = 256
    for _ in range(31):
        send_message(runtime)
    barrier = threading.Barrier(2)

    def compete(index):
        barrier.wait(timeout=5)
        return tool(client, caller, "message_create", {"project_root": root, "from_agent_id": "caller",
            "subject": "concurrent " + str(index), "body": "last slot",
            "target": {"strategy": "direct", "agent_id": "worker"}})

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(compete, range(2)))
    assert sum(result["ok"] for result in results) == 1
    assert next(result for result in results if not result["ok"])["error"]["code"] == "QUOTA_EXCEEDED"
    with deps.connection_factory.unit_of_work(write=False) as uow:
        for table in ("messages", "message_deliveries", "delivery_outbox"):
            assert uow.connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 32


def test_unconfirmed_attempt_keeps_capacity_reserved(runtime, monkeypatch):
    from test_runtime_outbox import wait_status
    deps, client, root, _, _, caller = runtime
    assert open_rest(runtime).status_code == 200
    first = send_message(runtime)["runtime_operations"][0]
    wait_status(runtime, first, "SENT_UNCONFIRMED")
    monkeypatch.setattr(deps.runtime_dispatcher, "scan_once", lambda: None)
    deps.config.max_new_roots_per_agent_per_minute = 256
    for _ in range(31):
        send_message(runtime)
    result = tool(client, caller, "message_create", {"project_root": root, "from_agent_id": "caller",
        "subject": "unconfirmed is not free", "body": "capacity",
        "target": {"strategy": "direct", "agent_id": "worker"}})
    assert not result["ok"] and result["error"]["code"] == "QUOTA_EXCEEDED"
    assert wait_status(runtime, first, "SENT_UNCONFIRMED")["reconciliation_id"] is None

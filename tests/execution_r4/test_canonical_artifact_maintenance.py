"""Operator recovery of private files never repeats native inference."""
from pathlib import Path

import pytest
from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, qualified_contract
from test_canonical_delivery import connected_local
from test_canonical_result_artifact import large_result
from test_canonical_result_publication import wait_result, workspace


@pytest.fixture
def runtime(connected_local, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1]))
    connected_local[0][2].headers["host"] = "127.0.0.1:8000"
    yield connected_local
    native = connected_local[2]
    assert native.opens == 1 and len(native.native.sent) == 1


def result(runtime, operation_id, state):
    row = wait_result(runtime[0], state)
    assert row["canonical_operation_id"] == operation_id
    return row


def policy(runtime, rules):
    from test_hitl import _attach
    _attach(runtime[0][0], "subject", governance=rules)


def tool_call(runtime, actor, args):
    from test_pr34_remediation import tool
    setup = runtime[0]
    return tool(setup[2], setup[3][actor]["Authorization"].removeprefix("Bearer "), "harness_list", args)


def request(runtime, **body):
    _, _, client, headers, *_ = runtime[0]
    return client.post("/api/v1/harness/artifacts", headers=headers["operator"], json=body)


def rejected_artifact(runtime, monkeypatch):
    from test_hitl import _rule
    deps, _, client, headers, *_ = runtime[0]
    deps.config.feature_hitl = True
    policy(runtime, [_rule("message_create", "require_approval")])
    op = large_result(runtime, monkeypatch)["operation_id"]
    pending = result(runtime, op, "PENDING_APPROVAL")
    response = client.post(f"/api/v1/approvals/{pending['publication_approval_id']}/decision",
        headers=headers["operator"], json={"decision": "reject"})
    assert response.status_code == 200, response.text
    deps.runtime_dispatcher.wake()
    return op, result(runtime, op, "BLOCKED")


def test_cleanup_is_idempotent_and_retry_uses_new_artifact_generation_without_native_replay(runtime, monkeypatch):
    deps = runtime[0][0]
    op, blocked = rejected_artifact(runtime, monkeypatch)
    blobs = list(deps.repos.artifact_store.root.rglob("runtime-result.txt"))
    assert len(blobs) == 1
    staging = blobs[0].parent.parent / ("." + blobs[0].parent.name + ".tmp-" + "a" * 32)
    staging.mkdir()
    (staging / "partial.txt").write_text("fixture incomplete staging")
    unrelated = blobs[0].parent.parent / (".unrelated.tmp-" + "b" * 32)
    unrelated.mkdir()
    (unrelated / "keep.txt").write_text("unrelated fixture")
    body = dict(action="cleanup", result_id=blocked["result_id"], idempotency_key="cleanup-fixture", reason="Rejected test output")
    first = request(runtime, **body)
    assert first.status_code == 200, first.text
    assert first.json()["data"]["released_bytes"] == 90000
    assert request(runtime, **body).json()["data"] == first.json()["data"]
    assert not blobs[0].exists()
    assert not staging.exists() and (unrelated / "keep.txt").read_text() == "unrelated fixture"
    after = result(runtime, op, "BLOCKED")
    assert after["artifact_generation"] == 1 and after["artifact_reserved_bytes"] == 0
    assert after["output_text"] == "L" * 90000
    assert request(runtime, **(body | {"reason": "changed"})).status_code == 409
    policy(runtime, [])
    retry = request(runtime, action="retry", result_id=blocked["result_id"], idempotency_key="retry-fixture", reason="Publication now allowed by fixture policy")
    assert retry.status_code == 200, retry.text
    published = result(runtime, op, "PUBLISHED")
    assert published["output_artifact_id"] not in str(blobs[0])
    assert request(runtime, **body).json()["data"] == first.json()["data"], "old cleanup request touched a new artifact generation"
    assert len(list(deps.repos.artifact_store.root.rglob("runtime-result.txt"))) == 1
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT count(*) FROM delivery_outbox").fetchone()[0] == 1
        assert uow.connection.execute("SELECT count(*) FROM artifacts").fetchone()[0] == 1


def test_cleanup_lost_response_retains_reservation_until_same_key_reconciliation(runtime, monkeypatch):
    deps = runtime[0][0]
    op, blocked = rejected_artifact(runtime, monkeypatch)
    discard = deps.repos.artifact_store.discard_unpublished
    def cut(**kwargs):
        discard(**kwargs)
        raise OSError("fixture cut after file removal")
    body = dict(action="cleanup", result_id=blocked["result_id"], idempotency_key="cleanup-cut", reason="Fixture deletion response cut")
    with monkeypatch.context() as patch:
        patch.setattr(deps.repos.artifact_store, "discard_unpublished", cut)
        failed = request(runtime, **body)
        assert failed.status_code == 409, failed.text
    uncertain = result(runtime, op, "ARTIFACT_CLEANUP")
    assert uncertain["artifact_reserved_bytes"] == 90000
    report = request(runtime).json()["data"]
    assert report["pending_maintenance"][0]["idempotency_key"] == body["idempotency_key"]
    assert request(runtime, **body).status_code == 200
    final = result(runtime, op, "BLOCKED")
    assert final["artifact_reserved_bytes"] == 0 and final["artifact_generation"] == 1
    assert final["output_text"] == "L" * 90000


def test_quota_recovery_retries_publication_once_and_published_files_cannot_be_collected(runtime, monkeypatch):
    deps, _, client, headers, *_ = runtime[0]
    small = dict(action="quota", quota_bytes=262144, idempotency_key="small", reason="Fixture capacity limit")
    assert request(runtime, **small).status_code == 200
    op = large_result(runtime, monkeypatch)["operation_id"]
    blocked = result(runtime, op, "BLOCKED")
    assert blocked["publication_reason"] == "QUOTA_EXCEEDED"
    denied = client.post("/api/v1/harness/artifacts", headers=headers["subject"], json={})
    assert denied.status_code == 403
    assert not tool_call(runtime, "subject", {"view": "artifacts"})["ok"]
    increased = tool_call(runtime, "operator", {"view": "artifacts", "maintenance": {
        "action": "quota", "quota_bytes": 1048576, "idempotency_key": "increase", "reason": "Fixture approved capacity"}})
    assert increased["ok"], increased
    retry = dict(action="retry", result_id=blocked["result_id"], idempotency_key="publish-again", reason="Capacity restored")
    assert request(runtime, **retry).status_code == 200
    published = result(runtime, op, "PUBLISHED")
    assert request(runtime, **retry).status_code == 200
    assert request(runtime, action="cleanup", result_id=published["result_id"], idempotency_key="unsafe-cleanup", reason="Must refuse published payload").status_code == 409
    assert request(runtime, **(small | {"idempotency_key": "below-existing"})).status_code == 409
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT count(*) FROM delivery_outbox").fetchone()[0] == 1
        row = uow.connection.execute("SELECT storage_path FROM artifacts WHERE artifact_id=?", (published["output_artifact_id"],)).fetchone()
    assert Path(deps.repos.artifact_store.root / row[0]).exists()


def test_owner_recovery_removes_abandoned_staging_before_creating_result_artifact(runtime, monkeypatch):
    from okto_nexus.application.runtime_results import RuntimeResultService
    deps = runtime[0][0]
    publish = deps.runtime_dispatcher.publish_results
    deps.runtime_dispatcher.publish_results = None
    try:
        turn = large_result(runtime, monkeypatch)
        row = result(runtime, turn["operation_id"], "PENDING_AUTHORIZATION")
        artifact_id = RuntimeResultService.artifact_id(row)
        abandoned = deps.repos.artifact_store.root / workspace(runtime[0]) / "subject" / ("." + artifact_id + ".tmp-" + "c" * 32)
        abandoned.mkdir(parents=True)
        (abandoned / "partial.txt").write_text("fixture old process partial bytes")
    finally:
        deps.runtime_dispatcher.publish_results = publish
        deps.runtime_dispatcher.wake()
    published = result(runtime, turn["operation_id"], "PUBLISHED")
    assert published["output_artifact_id"] == artifact_id
    assert not abandoned.exists()


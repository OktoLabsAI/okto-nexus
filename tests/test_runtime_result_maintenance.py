"""Operator recovery of private files never repeats native inference."""
from pathlib import Path

from test_pr34_remediation import runtime as runtime_fixture, send_message, tool
from test_runtime_artifact_durability import large_output_session
from test_runtime_result_publication import result
from test_governance import _attach, _rule

runtime = runtime_fixture


def request(runtime, **body):
    _, client, _, _, operator, _ = runtime
    return client.post("/api/v1/harness/artifacts", headers={"x-api-key": operator}, json=body)


def rejected_artifact(runtime):
    deps, client, _, _, operator, _ = runtime
    deps.config.feature_hitl = True
    large_output_session(runtime)
    _attach(deps, "worker", governance=[_rule("message_create", "require_approval")])
    source = send_message(runtime, body="unpublished artifact recovery fixture")
    op = source["runtime_operations"][0]
    pending = result(runtime, op, "PENDING_APPROVAL")
    response = client.post(f"/api/v1/approvals/{pending['publication_approval_id']}/decision",
        headers={"x-api-key": operator}, json={"decision": "reject"})
    assert response.status_code == 200, response.text
    deps.runtime_dispatcher.wake()
    return op, result(runtime, op, "BLOCKED")


def test_cleanup_is_idempotent_and_retry_uses_new_artifact_generation_without_native_replay(runtime):
    deps = runtime[0]
    op, blocked = rejected_artifact(runtime)
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
    assert first.json()["data"]["released_bytes"] == 70000
    assert request(runtime, **body).json()["data"] == first.json()["data"]
    assert not blobs[0].exists()
    assert not staging.exists() and (unrelated / "keep.txt").read_text() == "unrelated fixture"
    after = result(runtime, op, "BLOCKED")
    assert after["artifact_generation"] == 1 and after["artifact_reserved_bytes"] == 0
    assert after["output_text"] == "L" * 70000
    assert request(runtime, **(body | {"reason": "changed"})).status_code == 409
    _attach(deps, "worker", governance=[])
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
    deps = runtime[0]
    op, blocked = rejected_artifact(runtime)
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
    assert uncertain["artifact_reserved_bytes"] == 70000
    report = request(runtime).json()["data"]
    assert report["pending_maintenance"][0]["idempotency_key"] == body["idempotency_key"]
    assert request(runtime, **body).status_code == 200
    final = result(runtime, op, "BLOCKED")
    assert final["artifact_reserved_bytes"] == 0 and final["artifact_generation"] == 1
    assert final["output_text"] == "L" * 70000


def test_quota_recovery_retries_publication_once_and_published_files_cannot_be_collected(runtime):
    deps, client, _, _, operator, caller = runtime
    small = dict(action="quota", quota_bytes=262144, idempotency_key="small", reason="Fixture capacity limit")
    assert request(runtime, **small).status_code == 200
    large_output_session(runtime)
    source = send_message(runtime, body="quota recovery fixture")
    op = source["runtime_operations"][0]
    blocked = result(runtime, op, "BLOCKED")
    assert blocked["publication_reason"] == "QUOTA_EXCEEDED"
    denied = client.post("/api/v1/harness/artifacts", headers={"x-api-key": caller}, json={})
    assert denied.status_code == 403
    assert not tool(client, caller, "harness_list", {"view": "artifacts"})["ok"]
    increased = tool(client, operator, "harness_list", {"view": "artifacts", "maintenance": {
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


def test_owner_recovery_removes_abandoned_staging_before_creating_result_artifact(runtime):
    from okto_nexus.application.runtime_results import RuntimeResultService
    deps = runtime[0]
    large_output_session(runtime)
    publish = deps.runtime_dispatcher.publish_results
    deps.runtime_dispatcher.publish_results = None
    try:
        source = send_message(runtime, body="fixture abandoned staging recovery")
        row = result(runtime, source["runtime_operations"][0], "PENDING_AUTHORIZATION")
        artifact_id = RuntimeResultService.artifact_id(row)
        abandoned = deps.repos.artifact_store.root / source["workspace_id"] / "worker" / ("." + artifact_id + ".tmp-" + "c" * 32)
        abandoned.mkdir(parents=True)
        (abandoned / "partial.txt").write_text("fixture old process partial bytes")
    finally:
        deps.runtime_dispatcher.publish_results = publish
        deps.runtime_dispatcher.wake()
    published = result(runtime, source["runtime_operations"][0], "PUBLISHED")
    assert published["output_artifact_id"] == artifact_id
    assert not abandoned.exists()

"""Governed publication contracts exercised through canonical Core execution."""
from pathlib import Path
import threading

import pytest
from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, qualified_contract, wait_receipt
from test_canonical_delivery import connected_local, enable
from test_canonical_result_publication import current_turn, emit, wait_result, workspace


@pytest.fixture
def runtime(connected_local, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1]))
    setup, binding, native = connected_local
    setup[2].headers["host"] = "127.0.0.1:8000"
    setup[0].runtime_dispatcher.recovery_seconds = .2
    setup[0].runtime_dispatcher.wake()
    enable(setup, binding)
    yield connected_local
    assert native.opens == 1 and len(native.native.sent) == 1


def send_message(runtime, *, body, before_output=None):
    from test_pr34_remediation import tool
    setup, _, native = runtime
    _, _, client, headers, *_ = setup
    sent = tool(client, headers["operator"]["Authorization"].removeprefix("Bearer "),
        "message_create", dict(workspace_id=workspace(setup), from_agent_id="operator",
        body=body, subject="Publication contract", target=dict(strategy="direct", agent_id="subject")))
    assert sent["ok"], sent
    turn = current_turn(setup)
    wait_receipt(setup, turn)
    if before_output:
        before_output()
    emit(setup, native, turn, body)
    return sent["data"]


def result(runtime, operation_id, state):
    row = wait_result(runtime[0], state)
    assert row["operation_id"] == operation_id
    return row


def test_result_publication_is_private_correlated_and_idempotent(runtime):
    from okto_nexus.adapters.inbound.mcp.tools.messages import build_service
    deps = runtime[0][0]
    source = send_message(runtime, body="private fixture result")
    row = result(runtime, source["runtime_operations"][0], "PUBLISHED")
    messages = build_service(deps)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        bound = messages._runtime_results.row(uow, row["result_id"])
        published = uow.connection.execute("SELECT * FROM messages WHERE message_id=?", (row["publication_message_id"],)).fetchone()
        assert published["from_agent_id"] == "subject"
        assert published["parent_message_id"] == source["message_id"]
        recipients = uow.connection.execute("SELECT recipient_agent_id FROM message_deliveries WHERE message_id=?", (published["message_id"],)).fetchall()
        assert [r[0] for r in recipients] == [bound["recipient_id"]]
        assert uow.connection.execute("SELECT count(*) FROM delivery_outbox").fetchone()[0] == 1
    again = messages.create_message(**messages._runtime_results.arguments(bound), _runtime_result_id=row["result_id"])
    assert again["message_id"] == row["publication_message_id"]
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT count(*) FROM messages WHERE subject='Runtime result'").fetchone()[0] == 1


def test_result_obeys_current_sender_permissions_without_erasing_output(runtime):
    deps = runtime[0][0]
    def revoke_publication():
        with deps.connection_factory.unit_of_work() as uow:
            uow.connection.execute("UPDATE agents SET permissions=? WHERE agent_id='subject'", ('{"messages":{"send_direct":false}}',))
    source = send_message(runtime, body="retained despite denied publication", before_output=revoke_publication)
    row = result(runtime, source["runtime_operations"][0], "BLOCKED")
    assert "retained despite denied publication" in row["output_text"]
    assert not row["publication_message_id"]
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT count(*) FROM messages WHERE subject='Runtime result'").fetchone()[0] == 0


def test_publication_and_canonical_message_commit_together(runtime, monkeypatch):
    from okto_nexus.application.runtime_results import RuntimeResultService
    deps = runtime[0][0]
    finish = RuntimeResultService.finish
    failed = threading.Event()
    def fail(uow, **kwargs):
        finish(uow, **kwargs)
        failed.set()
        raise OSError("fixture result/message commit cut")
    with monkeypatch.context() as patch:
        patch.setattr(RuntimeResultService, "finish", staticmethod(fail))
        source = send_message(runtime, body="durable publication retry")
        result(runtime, source["runtime_operations"][0], "PENDING_AUTHORIZATION")
        # Explicitly exercise the failure barrier rather than a scheduling delay.
        assert failed.wait(5)
        with deps.connection_factory.unit_of_work(write=False) as uow:
            assert uow.connection.execute("SELECT count(*) FROM messages WHERE subject='Runtime result'").fetchone()[0] == 0
    deps.runtime_dispatcher.wake()
    row = result(runtime, source["runtime_operations"][0], "PUBLISHED")
    assert row["publication_message_id"]


@pytest.mark.parametrize("decision", ["approve", "reject"])
def test_publication_uses_canonical_approval_and_never_grants_itself_permission(runtime, decision):
    from test_hitl import _attach, _rule
    deps, _, client, headers, *_ = runtime[0]
    deps.config.feature_hitl = True
    _attach(deps, "subject", governance=[_rule("message_create", "require_approval")])
    source = send_message(runtime, body="approval-controlled reply")
    row = result(runtime, source["runtime_operations"][0], "PENDING_APPROVAL")
    aid = row["publication_approval_id"]
    assert aid and not row["publication_message_id"]
    path = f"/api/v1/approvals/{aid}/decision"
    assert client.post(path, headers=headers["subject"], json={"decision": decision}).status_code == 403
    response = client.post(path, headers=headers["operator"], json={"decision": decision})
    assert response.status_code == 200, response.text
    deps.runtime_dispatcher.wake()
    final = result(runtime, source["runtime_operations"][0], "PUBLISHED" if decision == "approve" else "BLOCKED")
    assert final["publication_approval_id"] == aid
    assert "approval-controlled reply" in final["output_text"]
    if decision == "approve":
        assert final["publication_message_id"] == response.json()["data"]["executed_result"]["message_id"]
    else:
        assert not final["publication_message_id"]
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT count(*) FROM delivery_outbox").fetchone()[0] == 1, "approval notification became a new native turn"


def test_result_identity_and_audience_cannot_be_replaced(runtime):
    from okto_nexus.adapters.inbound.mcp.tools.messages import build_service
    from okto_nexus.errors import OktoNexusError
    deps = runtime[0][0]
    source = send_message(runtime, body="bound identity")
    row = result(runtime, source["runtime_operations"][0], "PUBLISHED")
    messages = build_service(deps)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        bound = messages._runtime_results.row(uow, row["result_id"])
    args = messages._runtime_results.arguments(bound)
    for changed in ({"from_agent_id": "operator"}, {"target": {"strategy": "broadcast"}}, {"body": "replacement"}):
        with pytest.raises(OktoNexusError, match="source or audience"):
            messages.create_message(**(args | changed), _runtime_result_id=row["result_id"])


def test_guardrail_blocks_only_publication_and_retains_the_private_native_result(runtime):
    from okto_nexus.adapters.outbound.sqlite.guardrails_repo import SqliteAgentGroupRepo, SqliteGuardrailRepo, SqliteGuardrailAssignmentRepo
    from okto_nexus.domain import guardrails as gr
    deps = runtime[0][0]
    groups, rules, assignments = SqliteAgentGroupRepo(), SqliteGuardrailRepo(), SqliteGuardrailAssignmentRepo()
    with deps.connection_factory.unit_of_work() as uow:
        groups.create(uow, group_id="publication-subjects", name="Publication subjects")
        groups.add_member(uow, group_id="publication-subjects", agent_id="subject")
        rules.create(uow, guardrail_id="publication-fixture", name="Fixture output gate")
        rules.add_version(uow, guardrail_id="publication-fixture", status=gr.VERSION_STATUS_ACTIVE,
            evaluator_kind=gr.EVALUATOR_KIND_DETERMINISTIC,
            evaluator_config={"kind": "regex", "patterns": ["fixture-secret-output"]},
            surfaces=["message"], field_targets=["body"])
        assignments.create(uow, assignment_id="publication-assignment", scope_kind=gr.SCOPE_KIND_AGENT_GROUP,
            group_id="publication-subjects", guardrail_id="publication-fixture", version_mode=gr.VERSION_MODE_LATEST,
            mode=gr.ENFORCEMENT_MODE_ENFORCE, priority=10)
    source = send_message(runtime, body="fixture-secret-output")
    row = result(runtime, source["runtime_operations"][0], "BLOCKED")
    assert "fixture-secret-output" in row["output_text"]
    assert not row["publication_message_id"]


def test_pending_publication_revalidates_endpoint_and_requires_actual_approval(runtime):
    from test_hitl import _attach, _rule
    from okto_nexus.adapters.inbound.mcp.tools.messages import build_service
    from okto_nexus.errors import OktoNexusError
    deps, _, client, headers, *_ = runtime[0]
    deps.config.feature_hitl = True
    _attach(deps, "subject", governance=[_rule("message_create", "require_approval")])
    source = send_message(runtime, body="pending scoped result")
    row = result(runtime, source["runtime_operations"][0], "PENDING_APPROVAL")
    messages = build_service(deps)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        bound = messages._runtime_results.row(uow, row["result_id"])
    with pytest.raises(OktoNexusError, match="canonical decision"):
        messages.create_message(**messages._runtime_results.arguments(bound),
            _runtime_result_id=row["result_id"], _approved_execution=True)
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agent_endpoints SET enabled=0 WHERE endpoint_id=?", (runtime[1]["endpoint_id"],))
    response = client.post(f"/api/v1/approvals/{row['publication_approval_id']}/decision",
        headers=headers["operator"], json={"decision": "approve"})
    assert response.status_code == 403, response.text
    still_pending = result(runtime, source["runtime_operations"][0], "PENDING_APPROVAL")
    assert not still_pending["publication_message_id"]


def test_disabled_feature_preserves_pending_result_and_strict_mode_uses_captured_principal(runtime):
    deps = runtime[0][0]
    publish = deps.runtime_dispatcher.publish_results
    deps.runtime_dispatcher.publish_results = None
    try:
        source = send_message(runtime, body="captured authenticated principal")
        result(runtime, source["runtime_operations"][0], "PENDING_AUTHORIZATION")
        deps.config.feature_harness_integrations = False
        # Canonical consumption may record its processing receipt while output
        # publication is disabled. Only the output must remain unpublished.
        publish()
        result(runtime, source["runtime_operations"][0], "PENDING_AUTHORIZATION")
        with deps.connection_factory.unit_of_work(write=False) as uow:
            assert uow.connection.execute("SELECT COUNT(*) FROM messages WHERE subject='Runtime result'").fetchone()[0] == 0
        deps.config.trust_mode = "strict"
        deps.config.feature_harness_integrations = True
        publish()
        assert result(runtime, source["runtime_operations"][0], "PUBLISHED")["publication_message_id"]
    finally:
        deps.config.feature_harness_integrations = True
        deps.runtime_dispatcher.publish_results = publish

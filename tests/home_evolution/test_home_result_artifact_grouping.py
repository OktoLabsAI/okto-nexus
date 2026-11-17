"""Historical SQL facts, not complete runtime receipt chains or provider turns."""

# ruff: noqa: F401,F811 -- pytest fixtures imported explicitly by name
from datetime import datetime, timedelta
import json

from .fixtures import home_scenario, WORKSPACES
from .test_home_queries import service, link_handoff
from .test_home_http import http
from .test_home_final_scope import copy_row, read_http


def test_http_result_collects_same_claim_files_once_and_excludes_foreign_claim_and_workspace(
    http, service, home_scenario
):
    s = home_scenario
    link_handoff(s)
    with s.factory.unit_of_work() as uow:
        uow.connection.execute(
            "UPDATE handoffs SET claim_epoch=2 WHERE handoff_id='fixture-handoff-0000'"
        )
        uow.connection.execute(
            "UPDATE runtime_handoff_bindings SET claim_epoch=2 WHERE operation_id='domain-work'"
        )
    original_id = read_http(http, service, "results", workspace_id=WORKSPACES[0])[
        "items"
    ][0]["id"]
    links = []
    with s.factory.unit_of_work() as uow:
        c = uow.connection
        now = s.clock.now_iso()
        c.execute(
            "UPDATE handoffs SET status='VERIFYING' WHERE handoff_id='fixture-handoff-0000'"
        )
        operation = c.execute(
            "SELECT * FROM execution_operations WHERE operation_id='fixture-success'"
        ).fetchone()
        receipt = c.execute(
            "SELECT * FROM execution_receipts WHERE operation_id='fixture-success'"
        ).fetchone()
        domain = c.execute(
            "SELECT * FROM delivery_outbox WHERE operation_id='domain-work'"
        ).fetchone()
        binding = c.execute(
            "SELECT * FROM runtime_handoff_bindings WHERE operation_id='domain-work'"
        ).fetchone()
        delivery = c.execute(
            "SELECT * FROM message_deliveries WHERE delivery_id=?",
            (domain["delivery_id"],),
        ).fetchone()
        message = c.execute(
            "SELECT * FROM messages WHERE message_id=?", (domain["message_id"],)
        ).fetchone()
        copy_row(c, "messages", message, message_id="other-claim-message")
        copy_row(
            c,
            "message_deliveries",
            delivery,
            delivery_id="other-claim-delivery",
            message_id="other-claim-message",
        )
        copy_row(
            c,
            "delivery_outbox",
            domain,
            operation_id="other-claim-domain",
            delivery_id="other-claim-delivery",
            message_id="other-claim-message",
            root_operation_id="other-claim-domain",
        )
        copy_row(
            c,
            "runtime_handoff_bindings",
            binding,
            operation_id="other-claim-domain",
            claim_epoch=1,
            idempotency_key="other-claim",
        )
        for i, (
            artifact,
            artifact_workspace,
            operation_workspace,
            claim_domain,
        ) in enumerate(
            (
                ("file-0", WORKSPACES[0], WORKSPACES[0], "domain-work"),
                ("file-1", WORKSPACES[0], WORKSPACES[0], "domain-work"),
                ("file-2", WORKSPACES[0], WORKSPACES[0], "domain-work"),
                ("file-0", WORKSPACES[0], WORKSPACES[0], "domain-work"),
                (
                    "other-claim-file",
                    WORKSPACES[0],
                    WORKSPACES[0],
                    "other-claim-domain",
                ),
                ("other-project-file", WORKSPACES[1], WORKSPACES[0], "domain-work"),
                ("foreign-operation-file", WORKSPACES[0], WORKSPACES[1], "domain-work"),
                ("foreign-workspace-pair", WORKSPACES[1], WORKSPACES[1], "domain-work"),
            )
        ):
            op = "fixture-success" if i == 0 else "artifact-operation-" + str(i)
            if i:
                copy_row(
                    c,
                    "execution_operations",
                    operation,
                    operation_id=op,
                    workspace_id=operation_workspace,
                )
                copy_row(c, "execution_receipts", receipt, operation_id=op)
                c.execute(
                    "INSERT INTO execution_domain_deliveries VALUES('fixture-server','fixture-executor',?,?)",
                    (op, claim_domain),
                )
            c.execute(
                "INSERT OR IGNORE INTO artifacts(artifact_id,workspace_id,artifact_type,name,path,content_type,created_at) VALUES(?,?,'file',?,'unexposed-private-path','text/plain',?)",
                (artifact, artifact_workspace, artifact + ".txt", now),
            )
            c.execute(
                "INSERT INTO execution_event_ingress VALUES('fixture-server','fixture-executor','fixture-native-session','current-stream',?,?,'turn.completed','{}',?)",
                (2 + i, "artifact-event-" + str(i), now),
            )
            c.execute(
                "INSERT INTO execution_results VALUES('fixture-server','fixture-executor',?,'fixture-native-session','current-stream',?,'Synthetic terminal read fact',0,1,'success',?)",
                (op, 2 + i, now),
            )
            links.append(("file-result-" + str(i), now, claim_domain, op, artifact))
    baseline = next(
        item
        for item in read_http(
            http, service, "results", workspace_id=WORKSPACES[0], limit=100
        )["items"]
        if item["id"] == original_id
    )
    with s.factory.unit_of_work() as uow:
        uow.connection.executemany(
            "INSERT INTO runtime_results(result_id,payload,captured_at,operation_id,canonical_server_id,canonical_executor_id,canonical_operation_id,output_artifact_id) VALUES(?,'{}',?,?,'fixture-server','fixture-executor',?,?)",
            links,
        )
    before = s.counts()
    page = read_http(http, service, "results", workspace_id=WORKSPACES[0], limit=100)
    current = next(item for item in page["items"] if item["id"] == baseline["id"])
    assert [a["artifact_id"] for a in current["artifacts"]] == [
        "file-0",
        "file-1",
        "file-2",
    ]
    assert (
        current["source_ref"]["id"]
        == baseline["source_ref"]["id"]
        == "fixture-handoff-0000"
    )
    assert current["view_state"] == baseline["view_state"]
    assert current["verification_state"] == "VERIFYING"
    assert sum(item["id"] == baseline["id"] for item in page["items"]) == 1
    assert "unexposed-private-path" not in str(page)
    assert s.counts() == before
    global_result = next(
        item
        for item in read_http(http, service, "results", limit=100)["items"]
        if item["id"] == baseline["id"]
    )
    assert [a["artifact_id"] for a in global_result["artifacts"]] == [
        "file-0",
        "file-1",
        "file-2",
    ]
    with s.factory.unit_of_work(write=False) as uow:
        assert (
            uow.connection.execute(
                "SELECT status FROM handoffs WHERE handoff_id='fixture-handoff-0000'"
            ).fetchone()[0]
            == "VERIFYING"
        )
    # Other claim remains its own historical result, never enriches the current
    # result. Existing workspace authorization still fences its operation.
    historical = next(
        item
        for item in page["items"]
        if item["id"] != baseline["id"]
        and item["source_ref"]["id"] == "fixture-handoff-0000"
    )
    assert [a["artifact_id"] for a in historical["artifacts"]] == ["other-claim-file"]
    foreign = read_http(http, service, "results", workspace_id=WORKSPACES[1], limit=100)
    assert not any(
        a["artifact_id"] in {"file-0", "file-1", "file-2"}
        for item in foreign["items"]
        for a in item["artifacts"]
    )


def test_http_artifact_group_uses_authorized_terminal_relation_with_history_and_other_executor(
    http, service, home_scenario
):
    s = home_scenario
    link_handoff(s)
    with s.factory.unit_of_work() as uow:
        c = uow.connection
        now = s.clock.now_iso()
        operation = c.execute(
            "SELECT * FROM execution_operations WHERE operation_id='fixture-success'"
        ).fetchone()
        receipt = c.execute(
            "SELECT * FROM execution_receipts WHERE operation_id='fixture-success'"
        ).fetchone()
        executor = c.execute(
            "SELECT * FROM execution_executors WHERE executor_id='fixture-executor'"
        ).fetchone()
        binding = c.execute(
            "SELECT * FROM execution_bindings WHERE binding_id=?",
            (operation["binding_id"],),
        ).fetchone()
        workspace_binding = c.execute(
            "SELECT * FROM execution_workspace_bindings WHERE workspace_binding_id=?",
            (operation["workspace_binding_id"],),
        ).fetchone()
        endpoint = c.execute(
            "SELECT * FROM agent_endpoints WHERE endpoint_id=?",
            (binding["endpoint_id"],),
        ).fetchone()
        copy_row(c, "execution_executors", executor, executor_id="second-executor")
        copy_row(
            c,
            "execution_workspace_bindings",
            workspace_binding,
            executor_id="second-executor",
            workspace_binding_id="second-wxb",
        )
        copy_row(c, "agent_endpoints", endpoint, endpoint_id="second-artifact-endpoint")
        copy_row(
            c,
            "execution_bindings",
            binding,
            executor_id="second-executor",
            binding_id="second-binding",
            workspace_binding_id="second-wxb",
            endpoint_id="second-artifact-endpoint",
        )
        session = c.execute(
            "SELECT * FROM execution_sessions WHERE session_id='fixture-native-session'"
        ).fetchone()
        copy_row(
            c,
            "execution_sessions",
            session,
            executor_id="second-executor",
            binding_id="second-binding",
            workspace_binding_id="second-wxb",
        )
        for index, kind in enumerate(
            ("history", "cross-executor", "latest-nonterminal", "different-agent")
        ):
            op = "artifact-" + kind
            ex = "second-executor" if kind == "cross-executor" else "fixture-executor"
            changes = {"operation_id": op, "executor_id": ex}
            if kind == "cross-executor":
                changes.update(
                    binding_id="second-binding", workspace_binding_id="second-wxb"
                )
            if kind == "different-agent":
                changes["subject_agent_id"] = "C"
            copy_row(c, "execution_operations", operation, **changes)
            copy_row(c, "execution_receipts", receipt, operation_id=op, executor_id=ex)
            if kind == "latest-nonterminal":
                copy_row(
                    c,
                    "execution_receipts",
                    receipt,
                    operation_id=op,
                    executor_id=ex,
                    receipt_revision=2,
                    stage="RUNNING",
                )
            if kind == "history":
                c.execute(
                    "INSERT INTO execution_delivery_attempt_history VALUES('fixture-server',?,?, 'domain-work',1,?,?,1,?)",
                    (ex, op, binding["endpoint_id"], op, now),
                )
            else:
                c.execute(
                    "INSERT INTO execution_domain_deliveries VALUES('fixture-server',?,?,'domain-work')",
                    (ex, op),
                )
            c.execute(
                "INSERT INTO execution_event_ingress VALUES('fixture-server',?,'fixture-native-session','current-stream',?,?,'turn.completed','{}',?)",
                (ex, index + 20, "extra-artifact-event-" + kind, now),
            )
            c.execute(
                "INSERT INTO execution_results VALUES('fixture-server',?,?,'fixture-native-session','current-stream',?,'Synthetic historical result',0,1,'success',?)",
                (ex, op, index + 20, now),
            )
            c.execute(
                "INSERT INTO artifacts(artifact_id,workspace_id,artifact_type,name,path,created_at) VALUES(?,?,'file',?,'never-projected-path',?)",
                (kind, WORKSPACES[0], kind + ".txt", now),
            )
            c.execute(
                "INSERT INTO runtime_results(result_id,payload,captured_at,operation_id,canonical_server_id,canonical_executor_id,canonical_operation_id,output_artifact_id) VALUES(?,'{}',?,'domain-work','fixture-server',?,?,?)",
                ("extra-result-" + kind, now, ex, op, kind),
            )
    page = read_http(http, service, "results", workspace_id=WORKSPACES[0], limit=100)
    grouped = next(
        item
        for item in page["items"]
        if item["source_ref"]["id"] == "fixture-handoff-0000"
    )
    assert {a["artifact_id"] for a in grouped["artifacts"]} == {
        "history",
        "cross-executor",
        "different-agent",
    }
    filtered = read_http(
        http,
        service,
        "results",
        workspace_id=WORKSPACES[0],
        agent_id=operation["subject_agent_id"],
        limit=100,
    )
    grouped_filtered = next(
        item for item in filtered["items"] if item["id"] == grouped["id"]
    )
    assert {a["artifact_id"] for a in grouped_filtered["artifacts"]} == {
        "history",
        "cross-executor",
    }


def test_newest_foreign_workspace_operation_stays_direct_and_cannot_hide_legitimate_handoff(
    http, service, home_scenario
):
    s = home_scenario
    link_handoff(s)
    legitimate_workspace, foreign_workspace = WORKSPACES
    with s.factory.unit_of_work() as uow:
        c, now = uow.connection, s.clock.now_iso()
        operation = c.execute(
            "SELECT * FROM execution_operations WHERE operation_id='fixture-success'"
        ).fetchone()
        receipt = c.execute(
            "SELECT * FROM execution_receipts WHERE operation_id='fixture-success'"
        ).fetchone()
        session = c.execute(
            "SELECT * FROM execution_sessions WHERE session_id='fixture-native-session'"
        ).fetchone()
        opening = c.execute(
            "SELECT * FROM execution_operations WHERE operation_id=?",
            (session["open_operation_id"],),
        ).fetchone()
        wxb = c.execute(
            "SELECT * FROM execution_workspace_bindings WHERE workspace_binding_id=?",
            (operation["workspace_binding_id"],),
        ).fetchone()
        binding = c.execute(
            "SELECT * FROM execution_bindings WHERE binding_id=?",
            (operation["binding_id"],),
        ).fetchone()
        endpoint = c.execute(
            "SELECT * FROM agent_endpoints WHERE endpoint_id=?",
            (binding["endpoint_id"],),
        ).fetchone()
        copy_row(
            c,
            "execution_workspace_bindings",
            wxb,
            workspace_binding_id="foreign-result-wxb",
            workspace_id=foreign_workspace,
        )
        copy_row(
            c,
            "agent_endpoints",
            endpoint,
            endpoint_id="foreign-result-endpoint",
            workspace_id=foreign_workspace,
        )
        copy_row(
            c,
            "execution_bindings",
            binding,
            binding_id="foreign-result-binding",
            workspace_binding_id="foreign-result-wxb",
            endpoint_id="foreign-result-endpoint",
        )
        scope = dict(
            json.loads(opening["expected_revisions_json"]),
            workspace_id=foreign_workspace,
            workspace_binding_id="foreign-result-wxb",
            binding_id="foreign-result-binding",
            session_id="foreign-result-session",
        )
        context = {
            "workspace_id": foreign_workspace,
            "workspace_binding_id": "foreign-result-wxb",
            "binding_id": "foreign-result-binding",
            "session_id": "foreign-result-session",
            "expected_revisions_json": json.dumps(scope),
        }
        copy_row(
            c,
            "execution_operations",
            opening,
            operation_id="foreign-result-open",
            **context,
        )
        copy_row(
            c,
            "execution_sessions",
            session,
            session_id="foreign-result-session",
            workspace_id=foreign_workspace,
            workspace_binding_id="foreign-result-wxb",
            binding_id="foreign-result-binding",
            open_operation_id="foreign-result-open",
        )
        copy_row(
            c,
            "execution_operations",
            operation,
            operation_id="foreign-result-turn",
            **context,
        )
        latest = (
            (
                datetime.fromisoformat(receipt["received_at"].replace("Z", "+00:00"))
                + timedelta(seconds=10)
            )
            .isoformat()
            .replace("+00:00", "Z")
        )
        copy_row(
            c,
            "execution_receipts",
            receipt,
            operation_id="foreign-result-turn",
            received_at=latest,
        )
        # Persisted link points at another project's domain operation. Retain
        # the authorized direct terminal fact; this link cannot confer origin.
        c.execute(
            "INSERT INTO execution_domain_deliveries VALUES('fixture-server','fixture-executor','foreign-result-turn','domain-work')"
        )
        for index, (op, sid, workspace, artifact) in enumerate(
            (
                (
                    "fixture-success",
                    "fixture-native-session",
                    legitimate_workspace,
                    "legitimate-file",
                ),
                (
                    "foreign-result-turn",
                    "foreign-result-session",
                    foreign_workspace,
                    "foreign-file",
                ),
            )
        ):
            c.execute(
                "INSERT INTO execution_event_ingress VALUES('fixture-server','fixture-executor',?,'current-stream',?,?,'turn.completed','{}',?)",
                (sid, index + 50, "foreign-scope-event-" + str(index), now),
            )
            c.execute(
                "INSERT INTO execution_results VALUES('fixture-server','fixture-executor',?,?,'current-stream',?,'Synthetic terminal read fact',0,1,'success',?)",
                (op, sid, index + 50, now),
            )
            c.execute(
                "INSERT INTO artifacts(artifact_id,workspace_id,artifact_type,name,path,created_at) VALUES(?,?,'file',?,'never-read-private-path',?)",
                (artifact, workspace, artifact + ".txt", now),
            )
            c.execute(
                "INSERT INTO runtime_results(result_id,payload,captured_at,operation_id,canonical_server_id,canonical_executor_id,canonical_operation_id,output_artifact_id) VALUES(?,'{}',?,'domain-work','fixture-server','fixture-executor',?,?)",
                ("result-" + artifact, now, op, artifact),
            )
    before = s.counts()
    legitimate = read_http(
        http, service, "results", workspace_id=legitimate_workspace, limit=100
    )["items"]
    original = next(
        row for row in legitimate if row["source_ref"]["id"] == "fixture-handoff-0000"
    )
    foreign = read_http(
        http, service, "results", workspace_id=foreign_workspace, limit=100
    )["items"]
    direct = next(
        row
        for row in foreign
        if row["detail_target"].get("operation_id") == "foreign-result-turn"
    )
    assert direct["source_ref"]["type"] == "execution_result"
    assert direct["source_ref"]["id"] == "foreign-result-turn"
    assert direct["workspace_id"] == foreign_workspace
    assert [item["artifact_id"] for item in direct["artifacts"]] == ["foreign-file"]
    assert [item["artifact_id"] for item in original["artifacts"]] == [
        "legitimate-file"
    ]
    all_results = read_http(http, service, "results", limit=100)["items"]
    assert next(row for row in all_results if row["id"] == original["id"]) == original
    assert next(row for row in all_results if row["id"] == direct["id"]) == direct
    assert original["id"] != direct["id"]
    assert not any(row["source_ref"]["id"] == "fixture-handoff-0000" for row in foreign)
    assert "never-read-private-path" not in str(all_results)
    assert s.counts() == before

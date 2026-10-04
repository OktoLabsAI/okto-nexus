import json
import sqlite3

from okto_nexus.application.execution_native_recipient import native_question_recipient


def test_operator_question_route_is_available_in_dashboard_adapter():
    from okto_nexus.adapters.inbound.http.dashboard_runtime import build_router
    routes = {route.path: route.methods for route in build_router().routes}
    assert routes["/runtime/input-requests"] == {"GET"}


def test_shared_session_questions_follow_each_originating_message():
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
      CREATE TABLE execution_operations(server_id, executor_id, operation_id, action, actor_agent_id);
      CREATE TABLE execution_domain_deliveries(server_id, executor_id, operation_id, domain_operation_id);
      CREATE TABLE delivery_outbox(operation_id, message_id);
      CREATE TABLE messages(message_id, from_agent_id);
      INSERT INTO execution_operations VALUES ('s','e','turn-a','turn.submit','C'), ('s','e','turn-b','turn.submit','C');
      INSERT INTO execution_domain_deliveries VALUES ('s','e','turn-a','delivery-a'), ('s','e','turn-b','delivery-b');
      INSERT INTO delivery_outbox VALUES ('delivery-a','message-a'), ('delivery-b','message-b');
      INSERT INTO messages VALUES ('message-a','A'), ('message-b','B');
    """)
    request = dict(server_id="s", executor_id="e", session_id="shared-C", kind="native_input",
        operational_frame_json=json.dumps({"operational_request": {"method": "item/tool/requestUserInput"}}))
    assert native_question_recipient(conn, dict(request, source_operation_id="turn-a")) == "A"
    assert native_question_recipient(conn, dict(request, source_operation_id="turn-b")) == "B"
    conn.execute("DELETE FROM messages WHERE message_id='message-a'")
    assert native_question_recipient(conn, dict(request, source_operation_id="turn-a")) is None
    # A permission request is distinct from an interlocutor question.
    assert native_question_recipient(conn, dict(request, kind="native_approval")) == "operator"
    request["operational_frame_json"] = json.dumps({"operational_request": {
        "method": "mcpServer/elicitation/request", "params": {"_meta": {"codex_approval_kind": "mcp_tool_call"}}}})
    assert native_question_recipient(conn, request) == "operator"

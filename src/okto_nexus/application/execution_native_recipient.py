"""Resolve native question recipients from admitted work, never client hints."""
import json


def native_question_recipient(conn, request):
    """Return the interlocutor of this exact turn, including shared sessions.

    A native MCP permission elicitation remains an operator decision. A domain
    turn's actor is the runtime subject, so its immutable message supplies the
    interlocutor. Broken domain provenance must not fall back to that actor.
    """
    if request["kind"] != "native_input":
        return "operator"
    frame = json.loads(request["operational_frame_json"])
    native = frame["operational_request"]
    params = native.get("params", {})
    metadata = params.get("_meta")
    if (native.get("method") == "mcpServer/elicitation/request" and
            isinstance(metadata, dict) and metadata.get("codex_approval_kind") == "mcp_tool_call"):
        return "operator"
    source = conn.execute(
        "SELECT actor_agent_id FROM execution_operations WHERE server_id=? "
        "AND executor_id=? AND operation_id=? AND action='turn.submit'",
        (request["server_id"], request["executor_id"], request["source_operation_id"])).fetchone()
    if source is None:
        return None
    delivery = conn.execute(
        "SELECT m.from_agent_id FROM execution_domain_deliveries x "
        "LEFT JOIN delivery_outbox d ON d.operation_id=x.domain_operation_id "
        "LEFT JOIN messages m ON m.message_id=d.message_id "
        "WHERE x.server_id=? AND x.executor_id=? AND x.operation_id=?",
        (request["server_id"], request["executor_id"], request["source_operation_id"])).fetchone()
    return delivery[0] if delivery is not None else source[0]

"""Resolve native question recipients from admitted work, never client hints."""
import json

from ..adapters.outbound.sqlite.execution_native_sources import read_native_turn_source


def native_permission(kind, method, metadata):
    return kind != 'native_input' or (method == 'mcpServer/elicitation/request'
        and isinstance(metadata, dict) and metadata.get('codex_approval_kind') == 'mcp_tool_call')


def recipient_from_facts(*, permission, source_exists, source_actor, domain_link_exists, domain_sender):
    if permission:
        return 'operator'
    if not source_exists:
        return None
    return domain_sender if domain_link_exists else source_actor


def native_question_recipient(conn, request):
    """Return the interlocutor of this exact turn, including shared sessions.

    A native MCP permission elicitation remains an operator decision. A domain
    turn's actor is the runtime subject, so its immutable message supplies the
    interlocutor. Broken domain provenance must not fall back to that actor.
    """
    if request['kind'] != 'native_input':
        return recipient_from_facts(permission=True, source_exists=False, source_actor=None,
            domain_link_exists=False, domain_sender=None)
    frame = json.loads(request["operational_frame_json"])
    native = frame["operational_request"]
    params = native.get("params", {})
    metadata = params.get("_meta")
    permission = native_permission(request['kind'], native.get('method'), metadata)
    if permission:
        return recipient_from_facts(permission=True, source_exists=False, source_actor=None,
            domain_link_exists=False, domain_sender=None)
    source = read_native_turn_source(conn, server_id=request["server_id"], executor_id=request["executor_id"],
        session_id=request["session_id"], operation_id=request["source_operation_id"],
        owner_generation=request["session_owner_generation"], stream_epoch=request["stream_epoch"])
    delivery = conn.execute(
        "SELECT m.from_agent_id FROM execution_domain_deliveries x "
        "LEFT JOIN delivery_outbox d ON d.operation_id=x.domain_operation_id "
        "LEFT JOIN messages m ON m.message_id=d.message_id "
        "WHERE x.server_id=? AND x.executor_id=? AND x.operation_id=?",
        (request["server_id"], request["executor_id"], request["source_operation_id"])).fetchone()
    return recipient_from_facts(permission=False, source_exists=source is not None,
        source_actor=source["actor_agent_id"] if source else None, domain_link_exists=delivery is not None,
        domain_sender=delivery[0] if delivery else None)

"""Read a bounded transcript projection from committed R4 events."""

import hashlib
import re

from nexus_connector_core.event_artifacts import REFERENCE_KEY
from nexus_connector_core.native.codex_chat_facts import CODEX_CHAT_DELTA, is_codex_chat_id, valid_codex_chat_delta
from nexus_connector_core.native.pi_chat_facts import PI_CHAT_EVENT, valid_pi_chat_fact
from nexus_connector_core.protocol import canonical_json

from ..adapters.outbound.harness.event_journal import redact
from ..domain.session_interaction import InputScope
from ..errors import ErrorCode, OktoNexusError
from .execution_event_views import read_execution_events

MAX_SCAN_EVENTS = 50
MAX_PART_BYTES = 4096
MAX_ITEM_PARTS = 8
_MAX_BODY_CHARS = 4 * MAX_PART_BYTES
_TERMINAL_CONTROLS = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")


def _native_id(value: object) -> bool:
    return (
        isinstance(value, str)
        and 1 <= len(value) <= 160
        and value.isprintable()
        and redact(value) == value
        and "[REDACTED]" not in value
        and "[NATIVE_TEXT_REDACTED]" not in value
    )


def _identity(*values: str | int) -> str:
    return hashlib.sha256(canonical_json(list(values))).hexdigest()


def _text_parts(event: dict, payload: dict):
    """Allowlist chat shapes with a retained item identifier and origin."""
    kind = (event.get("native_type"), event.get("category"))
    if kind == ("item/agentMessage/delta", "text_delta"):
        yield "assistant", "append", payload.get("itemId"), 0, payload.get("delta")
        return
    if kind != ("item/completed", "tool_activity"):
        return
    item = payload.get("item")
    if not isinstance(item, dict):
        return
    if item.get("type") == "agentMessage":
        yield "assistant", "replace", item.get("id"), 0, item.get("text")
    elif item.get("type") == "userMessage" and isinstance(item.get("content"), list):
        for index, part in enumerate(item["content"][:MAX_ITEM_PARTS]):
            if isinstance(part, dict) and part.get("type") == "text":
                yield "user", "replace", item.get("id"), index, part.get("text")


def _bounded_body(body: str) -> tuple[str | None, bool]:
    # Do not process an entire hydrated artifact or redact a cut-off token.
    if len(body) > _MAX_BODY_CHARS:
        return None, True
    cleaned = redact(_TERMINAL_CONTROLS.sub("", body.replace("\r\n", "\n")))
    encoded = cleaned.encode("utf-8")
    return encoded[:MAX_PART_BYTES].decode("utf-8", errors="ignore"), len(encoded) > MAX_PART_BYTES


def _updates(event: dict):
    payload = event.get("payload")
    if not isinstance(payload, dict):
        return
    stream = (event["server_id"], event["executor_id"], event["session_id"], event["stream_epoch"])
    sequence = event["sequence"]
    event_id = _identity(*stream, sequence)
    if event.get("native_type") == PI_CHAT_EVENT:
        if event.get("category") != "tool_activity" or not valid_pi_chat_fact(payload):
            return
        native = payload["native_session_id"]
        operation = event.get("operation_id")
        if not _native_id(native) or not _native_id(operation):
            return
        body = payload["text"]
        text, truncated = (None, True) if body is None else _bounded_body(body)
        message_id = _identity(*stream, "pi", native, payload["entry_id"], payload["role"])
        yield {
            "event_id": event_id, "update_id": _identity(event_id, message_id), "message_id": message_id,
            "sequence": sequence, "role": payload["role"], "change": "replace",
            "origin": {"kind": "native_session", "session_id": native}, "operation_id": operation,
            "text": text, "text_truncated": truncated,
        }
        return
    thread = payload.get("thread_id")
    if CODEX_CHAT_DELTA in payload:
        fact = payload[CODEX_CHAT_DELTA]
        operation = event.get("operation_id")
        if (event.get("native_type") != "item/agentMessage/delta" or event.get("category") != "text_delta"
                or not valid_codex_chat_delta(fact) or fact["thread_id"] != thread
                or not all(_native_id(value) for value in (thread, fact["item_id"], operation))
                or not is_codex_chat_id(payload.get("turn_id"))):
            return
        text, truncated = _bounded_body(fact["text"])
        message_id = _identity(*stream, thread, fact["item_id"], "assistant", 0)
        yield {
            "event_id": event_id, "update_id": _identity(event_id, message_id), "message_id": message_id,
            "sequence": sequence, "role": "assistant", "change": "append",
            "origin": {"kind": "native_thread", "thread_id": thread}, "operation_id": operation,
            "text": text, "text_truncated": truncated or fact["truncated"],
        }
        return
    if not _native_id(thread) or payload.get("threadId") != thread:
        return
    for role, change, item_id, index, body in _text_parts(event, payload):
        if not _native_id(item_id) or not isinstance(body, str):
            continue
        try:
            text, truncated = _bounded_body(body)
        except UnicodeEncodeError:
            continue
        message_id = _identity(*stream, thread, item_id, role, index)
        yield {
            "event_id": event_id,
            "update_id": _identity(event_id, message_id),
            "message_id": message_id,
            "sequence": sequence,
            "role": role,
            "change": change,
            "origin": {"kind": "native_thread", "thread_id": thread},
            "text": text,
            "text_truncated": truncated,
        }


def read_session_interaction_transcript(
    factory, *, scope: InputScope, context, access, stream_epoch=None,
    after_sequence=0, limit=MAX_SCAN_EVENTS,
) -> dict:
    """Return an ordered page of message updates on the canonical event cursor.

    A page can have no chat updates and still advance. Replay cannot prove a
    complete native transcript, thread parentage, or an input-to-echo link.
    A truncated body can be a prefix or entirely absent (``text=None``).
    Current Core emits scoped, scrubbed Codex fragments alongside masked raw
    fields. Only reviewed hosted Pi snapshots carry a retained native entry ID.
    """
    if type(limit) is not int or not 1 <= limit <= MAX_SCAN_EVENTS:
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Invalid transcript scan limit.", {})
    if after_sequence != 0 and stream_epoch is None:
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "A transcript cursor requires its stream epoch.", {})

    page = read_execution_events(
        factory, server_id=scope.session.server_id, executor_id=scope.session.executor_id,
        session_id=scope.session.session_id, context=context, access=access,
        stream_epoch=stream_epoch, after_sequence=after_sequence, limit=limit,
        hydrate_artifacts=False,
    )
    actual_scope = page["scope"]
    if (
        actual_scope["binding_id"] != scope.binding_id
        or actual_scope["workspace_id"] != scope.workspace_id
        or actual_scope["workspace_binding_id"] != scope.workspace_binding_id
        or actual_scope["agent_id"] != scope.agent_id
        or actual_scope["session_owner_generation"] != scope.generation.value
    ):
        raise OktoNexusError(ErrorCode.NOT_FOUND, "The session was not found in this scope.", {})

    return {
        "scope": actual_scope,
        "stream_epoch": page["stream_epoch"],
        "updates": [update for event in page["events"] for update in _updates(event)],
        "next_after_sequence": page["next_after_sequence"],
        "committed_contiguous": page["committed_contiguous"],
        "gap_pending": page["gap_pending"],
        "has_more": page["has_more"],
        "omitted_artifact_events": sum(REFERENCE_KEY in event["payload"] for event in page["events"]),
        "history_complete": False,
    }

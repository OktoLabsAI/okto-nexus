"""Exercise transcript projection through the read-only canonical event reader."""

import hashlib
import sqlite3
from contextlib import contextmanager
from dataclasses import replace
from types import SimpleNamespace

import pytest
from nexus_connector_core.native.adapter_types import HarnessEvent
from nexus_connector_core.native.event_ingest import translate_native_event
from nexus_connector_core.native.pi_chat_facts import PI_CHAT_EVENT
from nexus_connector_core.native.redaction import NativeSecretRedactor
from nexus_connector_core.protocol import canonical_json

from okto_nexus.application import execution_event_views
from okto_nexus.application.codex_presenter_history import read_codex_history_snapshot, read_codex_history_updates
from okto_nexus.application.codex_presenter_requests import codex_history_page
from okto_nexus.application.execution_native_session_mapping import ManagedNativeSession
from okto_nexus.application.session_interaction_transcript import (
    MAX_PART_BYTES,
    MAX_SCAN_EVENTS,
    read_session_interaction_transcript,
)
from okto_nexus.domain.execution.keys import SessionKey, SessionOwnerGeneration
from okto_nexus.domain.session_interaction import InputScope
from okto_nexus.errors import ErrorCode, OktoNexusError


@pytest.fixture
def stream(monkeypatch):
    scope = InputScope(SessionKey("server", "executor", "session"), SessionOwnerGeneration(1),
                       "binding", "workspace", "workspace-binding", "agent")
    keys = {"server_id": "server", "executor_id": "executor", "session_id": "session"}
    stored_scope = {**keys, "binding_id": "binding", "workspace_id": "workspace",
                    "workspace_binding_id": "workspace-binding", "agent_id": "agent",
                    "session_owner_generation": 1}
    context, access = object(), object()
    with sqlite3.connect(":memory:") as db:
        db.row_factory = sqlite3.Row
        db.executescript("""
            CREATE TABLE execution_sessions (server_id, executor_id, session_id, stream_epoch);
            CREATE TABLE execution_event_watermarks (
                server_id, executor_id, session_id, stream_epoch, committed_contiguous, gap_state
            );
            CREATE TABLE execution_event_ingress (
                server_id, executor_id, session_id, stream_epoch, sequence,
                event_hash, payload_json, received_at
            );
            INSERT INTO execution_sessions VALUES ('server', 'executor', 'session', 'epoch');
        """)

        @contextmanager
        def unit_of_work(*, write):
            assert write is False
            db.execute("PRAGMA query_only = ON")
            try:
                yield SimpleNamespace(connection=db)
            finally:
                db.execute("PRAGMA query_only = OFF")

        factory = SimpleNamespace(unit_of_work=unit_of_work)

        def authorize(actual_factory, *, server_id, session_id, executor_id,
                      context: object, access: object, _uow):
            assert (server_id, executor_id, session_id) == tuple(keys.values())
            assert actual_factory is factory and _uow.connection is db
            assert _uow.connection.execute("PRAGMA query_only").fetchone()[0] == 1
            if (context, access) != authority:
                raise OktoNexusError(ErrorCode.NOT_FOUND, "Fixture access denied.", {})
            return {"scope": stored_scope}

        # Existing replay tests exercise the canonical authorization itself.
        authority = (context, access)
        monkeypatch.setattr(execution_event_views, "read_execution_session", authorize)

        def store(sequence, kind, category, payload, *, epoch="epoch", operation_id=None):
            event = {**keys, "stream_epoch": epoch, "sequence": sequence,
                     "category": category, "payload": payload}
            if kind is not None:
                event["native_type"] = kind
            if operation_id is not None:
                event["operation_id"] = operation_id
            raw = canonical_json(event)
            digest = "sha256:" + hashlib.sha256(raw).hexdigest()
            db.execute("INSERT INTO execution_event_ingress VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                       (*keys.values(), epoch, sequence, digest, raw.decode(), "2026-11-18T00:00:00Z"))

        def watermark(committed, gap="none", *, epoch="epoch"):
            db.execute("DELETE FROM execution_event_watermarks WHERE stream_epoch=?", (epoch,))
            db.execute("INSERT INTO execution_event_watermarks VALUES (?, ?, ?, ?, ?, ?)",
                       (*keys.values(), epoch, committed, gap))

        def read(**query):
            options = {"scope": scope, "context": context, "access": access, **query}
            return read_session_interaction_transcript(factory, **options)

        def history(thread_id, *, position=None, **changes):
            mapping = ManagedNativeSession(
                scope=scope, opening_operation_id="open", adapter_id="codex_app_server",
                native_session_id="adapter-session", stream_epoch="epoch", launch_candidate_ref="candidate",
                launch_inventory_revision="inventory", launch_profile_revision=1, launch_build=None,
                receipt_connection_id="connection", receipt_connection_generation=1, codex_thread_id=thread_id,
                codex_configuration_hash="event-digest",
            )
            mapping = replace(mapping, **changes)
            if position is not None:
                sequence, active_turn = position
                return read_codex_history_updates(factory, mapping=mapping, context=context, access=access,
                                                  after_sequence=sequence, active_turn=active_turn)
            return read_codex_history_snapshot(factory, mapping=mapping, context=context, access=access)

        yield SimpleNamespace(store=store, watermark=watermark, read=read, scope=scope, history=history)
    db.close()


def _delta(stream, sequence, item_id, text, *, thread="thread", epoch="epoch"):
    stream.store(sequence, "item/agentMessage/delta", "text_delta", {
        "thread_id": thread, "threadId": thread, "itemId": item_id, "delta": text,
    }, epoch=epoch)


def _completed(stream, sequence, item, *, thread="thread"):
    stream.store(sequence, "item/completed", "tool_activity", {
        "thread_id": thread, "threadId": thread, "item": item,
    })


def test_deltas_and_snapshots_share_item_identity_but_equal_text_does_not_merge(stream):
    _delta(stream, 1, "first", "same")
    _completed(stream, 2, {"id": "first", "type": "agentMessage", "text": "same"})
    _delta(stream, 3, "second", "same")
    _delta(stream, 4, "first", "same", thread="other-thread")
    _delta(stream, 1, "first", "same", epoch="other-epoch")
    stream.watermark(4)
    stream.watermark(1, epoch="other-epoch")

    first = stream.read(limit=1)
    assert first["has_more"] and first["next_after_sequence"] == 1
    remainder = stream.read(stream_epoch=first["stream_epoch"], after_sequence=first["next_after_sequence"])
    old_epoch = stream.read(stream_epoch="other-epoch")
    updates = first["updates"] + remainder["updates"]
    assert [item["change"] for item in updates] == ["append", "replace", "append", "append"]
    assert [item["text"] for item in updates] == ["same"] * 4
    assert updates[0]["message_id"] == updates[1]["message_id"]
    assert len({item["message_id"] for item in updates + old_epoch["updates"]}) == 4
    assert len({item["update_id"] for item in updates + old_epoch["updates"]}) == 5
    assert updates[-1]["origin"] == {"kind": "native_thread", "thread_id": "other-thread"}
    assert stream.read(limit=1) == first


def test_artifact_reference_advances_cursor_without_hydrating_body(stream, monkeypatch):
    from nexus_connector_core.event_artifacts import REFERENCE_KEY

    from okto_nexus.application import execution_event_views

    def unexpected_read(*args):
        pytest.fail("The transcript projection attempted to hydrate an artifact.")

    monkeypatch.setattr(execution_event_views, "resolve_event", unexpected_read)
    stream.store(1, "item/agentMessage/delta", "text_delta", {REFERENCE_KEY: {"size_bytes": 16000000}})
    _delta(stream, 2, "inline", "Available inline text")
    stream.watermark(2)
    page = stream.read()
    assert page["next_after_sequence"] == 2
    assert page["omitted_artifact_events"] == 1
    assert [update["text"] for update in page["updates"]] == ["Available inline text"]


def test_hosted_pi_transcript_requires_retained_ids_and_keeps_equal_messages_distinct(stream):
    fact = {"revision": 1, "native_session_id": "native-pi-session", "entry_id": "abcdef01",
            "role": "assistant", "text": "same\x00 response"}
    stream.store(1, "message_end", "tool_activity", {"message": fact})
    stream.store(2, PI_CHAT_EVENT, "tool_activity", fact, operation_id="first-turn")
    stream.store(3, PI_CHAT_EVENT, "tool_activity", fact | {"entry_id": "abcdef02"}, operation_id="second-turn")
    stream.store(4, PI_CHAT_EVENT, "tool_activity", fact | {"entry_id": "abcdef03", "text": None},
                 operation_id="second-turn")
    stream.store(5, PI_CHAT_EVENT, "tool_activity", fact | {"role": "thinking"}, operation_id="second-turn")
    stream.store(6, PI_CHAT_EVENT, "tool_activity", fact | {"entry_id": "abcdef04"})
    stream.store(7, PI_CHAT_EVENT, "tool_activity", fact, operation_id="first-turn")
    stream.watermark(7)

    page = stream.read()
    assert page["next_after_sequence"] == 7 and not page["history_complete"]
    first, second, omitted, repeated = page["updates"]
    assert first["message_id"] == repeated["message_id"] != second["message_id"]
    assert first["update_id"] != repeated["update_id"]
    assert first["text"] == second["text"] == "same response"
    assert first["origin"] == {"kind": "native_session", "session_id": "native-pi-session"}
    assert [item["operation_id"] for item in (first, second)] == ["first-turn", "second-turn"]
    assert omitted["text"] is None and omitted["text_truncated"]


def test_omitted_events_advance_canonical_cursor_without_hiding_a_gap(stream):
    stream.store(1, "item/reasoning/textDelta", "text_delta", {
        "thread_id": "thread", "threadId": "thread", "itemId": "hidden",
        "delta": "private thinking", "output_text": "private thinking",
    })
    _delta(stream, 3, "later", "hidden past the gap")
    stream.watermark(1, "pending")
    page = stream.read()
    assert page["updates"] == [] and page["gap_pending"]
    assert page["next_after_sequence"] == page["committed_contiguous"] == 1
    assert page["history_complete"] is False

    stream.store(2, "item/agentMessage/delta", "text_delta", {
        "thread_id": "thread", "threadId": "different-thread", "itemId": "unproven",
        "delta": "wrong origin",
    })
    stream.store(4, None, "text_delta", {
        "thread_id": "thread", "threadId": "thread", "itemId": "untyped", "delta": "untyped",
    })
    stream.watermark(4)
    page = stream.read(stream_epoch=page["stream_epoch"], after_sequence=page["next_after_sequence"])
    assert [item["text"] for item in page["updates"]] == ["hidden past the gap"]
    assert page["next_after_sequence"] == 4 and not page["gap_pending"]


def test_only_text_parts_are_projected_and_their_size_is_bounded(stream):
    _completed(stream, 1, {"id": "prompt", "type": "userMessage", "content": [
        {"type": "text", "text": "same"},
        {"type": "image", "url": "https://irrelevant.invalid/"},
        {"type": "text", "text": "same"},
        {"type": "text", "text": "Bearer fixture-token-123\x00\r\n" + "あ" * MAX_PART_BYTES},
    ]})
    _completed(stream, 2, {"id": "tool", "type": "commandExecution", "text": "Tool output"})
    stream.store(3, "assistant", "text_snapshot", {"output_text": "Uncorrelated snapshot"})
    stream.watermark(3)
    first, second, long = stream.read()["updates"]
    assert first["text"] == second["text"] == "same"
    assert first["role"] == second["role"] == long["role"] == "user"
    assert first["event_id"] == second["event_id"] == long["event_id"]
    assert len({part["message_id"] for part in (first, second, long)}) == 3
    assert long["text"].startswith("[REDACTED]\n")
    assert len(long["text"].encode("utf-8")) <= MAX_PART_BYTES
    assert long["text_truncated"] is True


def test_oversized_body_is_explicitly_absent_from_the_update(stream):
    _completed(stream, 1, {"id": "large", "type": "agentMessage", "text": "x" * (5 * MAX_PART_BYTES)})
    stream.watermark(1)
    page = stream.read()
    update, = page["updates"]
    assert update["change"] == "replace" and update["text"] is None
    assert update["text_truncated"] and page["next_after_sequence"] == 1


def test_pi_and_claude_text_without_retained_identity_is_omitted(stream):
    content = [{"type": "text", "text": "Completed assistant response."}]
    claude_message = {"id": "msg_001", "type": "message", "role": "assistant"}
    claude_origin = {"session_id": "claude-session", "parent_tool_use_id": "toolu_subagent"}
    redactor = NativeSecretRedactor()

    def store(sequence, harness, kind, native_type, payload, *, snapshot=False, thread_id=None):
        native = HarnessEvent(
            session_id="native-session", harness_kind=harness, kind=kind, native_event=native_type,
            occurred_at="2026-11-18T00:00:00Z", payload=payload, thread_id=thread_id,
            output_snapshot=snapshot,
        )
        event = translate_native_event(
            redactor.scrub(native), server_id="server", executor_id="executor", session_id="session",
            stream_epoch="epoch", native_session_id="native-session",
        )
        stream.store(sequence, event.native_type, event.category, event.payload)
        return event.payload

    claude_start = store(1, "claude_code", "tool_activity", "stream_event:message_start", {
        **claude_origin, "type": "stream_event",
        "event": {"type": "message_start", "message": {**claude_message, "content": []}},
    })
    claude_delta = store(2, "claude_code", "output_delta", "stream_event:content_block_delta", {
        "text": content[0]["text"], "index": 0,
    })
    claude_snapshot = store(3, "claude_code", "output_delta", "assistant", {
        "final": True, "text": content[0]["text"],
        "raw": {**claude_origin, "type": "assistant", "message": {**claude_message, "content": content}},
    }, snapshot=True)
    pi_snapshot = store(4, "pi", "tool_activity", "message_end", {
        "type": "message_end", "message": {"role": "assistant", "content": content, "timestamp": 1789928310150},
    })
    codex_delta = store(5, "codex", "output_delta", "item/agentMessage/delta", {
        "threadId": "codex-thread", "itemId": "codex-item", "delta": content[0]["text"],
    }, thread_id="codex-thread")
    store(6, "codex", "tool_activity", "item/completed", {
        "threadId": "codex-thread",
        "item": {"id": "codex-item", "type": "agentMessage", "text": content[0]["text"]},
    }, thread_id="codex-thread")
    stream.watermark(6)

    assert claude_start["event"]["message"]["id"] == "msg_001"
    assert claude_start["parent_tool_use_id"] == "toolu_subagent"
    assert claude_delta["output_text"]
    assert claude_snapshot["output_text"] and claude_snapshot["raw"]["message"]["id"] == "[NATIVE_TEXT_REDACTED]"
    assert pi_snapshot["message"]["content"] == content and "id" not in pi_snapshot["message"]
    assert codex_delta["output_text"] and codex_delta["itemId"] == "[NATIVE_TEXT_REDACTED]"
    page = stream.read()
    assert page["next_after_sequence"] == 6
    assert [(update["sequence"], update["text"]) for update in page["updates"]] == [(6, content[0]["text"])]


def test_redaction_marker_does_not_become_native_identity(stream):
    mask = "[NATIVE_TEXT_REDACTED]"
    _delta(stream, 1, mask, "unidentified item")
    _delta(stream, 2, "item-with-redacted-origin", "unidentified origin", thread=mask)
    stream.watermark(2)
    assert stream.read()["updates"] == []


@pytest.mark.parametrize("field", ["binding_id", "workspace_id", "workspace_binding_id", "agent_id", "generation"])
def test_scope_mismatch_does_not_return_any_events(stream, field):
    stream.watermark(1)
    _delta(stream, 1, "item", "restricted")
    different = SessionOwnerGeneration(2) if field == "generation" else "different"
    with pytest.raises(OktoNexusError) as err:
        stream.read(scope=replace(stream.scope, **{field: different}))
    assert err.value.code == ErrorCode.NOT_FOUND


def test_canonical_authorization_and_cursor_validation(stream):
    with pytest.raises(OktoNexusError, match="Fixture access denied"):
        stream.read(access=object())
    with pytest.raises(OktoNexusError, match="requires its stream epoch"):
        stream.read(after_sequence=1)
    with pytest.raises(OktoNexusError, match="Invalid transcript scan limit"):
        stream.read(limit=MAX_SCAN_EVENTS + 1)
    with pytest.raises(OktoNexusError, match="stream was not found"):
        stream.read(stream_epoch="unknown")


def test_codex_history_pages_share_a_scope_and_contiguous_snapshot(stream):
    thread = "bdfe5b81-54cf-43cf-8001-5de670d3dd69"
    turn = "f1577a8a-c99a-4677-91e3-459ba893eaed"
    data = {"thread_id": thread, "threadId": thread, "turnId": turn}
    stream.store(1, "turn/started", "turn_state", data | {"turn": {"id": turn, "status": "inProgress"}})
    stream.store(2, "item/completed", "tool_activity", data | {"item": {
        "id": "question", "type": "userMessage", "content": [{"type": "text", "text": "Question"}]}})
    stream.store(3, "item/completed", "tool_activity", data | {"item": {
        "id": "answer", "type": "agentMessage", "text": "Answer\x1b", "private_field": "not exposed"}})
    stream.store(4, "item/completed", "tool_activity", data | {"item": {
        "id": "tool", "type": "commandExecution", "command": "not exposed"}})
    stream.store(5, "item/completed", "tool_activity", data | {"threadId": "sibling", "item": {
        "id": "sibling", "type": "agentMessage", "text": "not exposed"}})
    stream.store(6, "turn/completed", "turn_state", data | {"turn": {"id": turn, "status": "completed"}})
    stream.watermark(6)
    history = stream.history(thread)
    assert history.committed_through == 6 and history.omitted_items == 1

    def request(method, **params):
        return codex_history_page(method=f"thread/{method}/list",
                                  params={"threadId": thread, **params}, native_thread_id=thread)

    page = history.page(request("items", limit=1, turnId=turn))
    assert page["data"] == [{"turnId": turn, "item": {
        "id": "question", "type": "userMessage", "content": [
            {"type": "text", "text": "Question", "text_elements": []}]}}]
    cursor = page["nextCursor"]
    last = history.page(request("items", limit=1, turnId=turn, cursor=cursor))
    assert last["nextCursor"] is None
    assert last["data"] == [{"turnId": turn, "item": {"id": "answer", "type": "agentMessage", "text": "Answer"}}]
    assert history.page(request("items", limit=1, turnId=turn, sortDirection="desc",
        cursor=page["backwardsCursor"]))["data"] == page["data"]
    assert history.page(request("turns"))["data"] == [
        {"id": turn, "status": "completed", "itemsView": "notLoaded", "items": []}]
    with pytest.raises(OktoNexusError, match="cursor is unavailable"):
        history.page(request("turns", cursor=cursor))
    with pytest.raises(OktoNexusError, match="cursor is unavailable"):
        stream.history(thread).page(request("items", cursor=cursor, turnId=turn))
    with pytest.raises(OktoNexusError, match="outside this presentation"):
        history.page(request("items", turnId=thread))
    with pytest.raises(OktoNexusError, match="outside this presentation"):
        stream.history(thread, scope=replace(stream.scope, generation=SessionOwnerGeneration(2)))


def test_codex_history_requires_a_complete_bounded_range(stream):
    stream.watermark(0, gap="gap")
    with pytest.raises(OktoNexusError, match="complete history range"):
        stream.history("bdfe5b81-54cf-43cf-8001-5de670d3dd69")
    for sequence in range(1, 514):
        stream.store(sequence, "unrelated", "lifecycle", {})
    stream.watermark(513)
    with pytest.raises(OktoNexusError, match="complete history range"):
        stream.history("bdfe5b81-54cf-43cf-8001-5de670d3dd69")


def test_codex_viewer_updates_continue_exact_snapshot_without_private_events(stream):
    thread = 'owned-thread'
    turn = 'active-turn'
    scope = {'threadId': thread, 'thread_id': thread, 'turnId': turn}
    started = {'id': turn, 'status': 'inProgress'}
    stream.store(1, 'turn/started', 'turn_state', scope | {'turn': started})
    stream.watermark(1)
    snapshot = stream.history(thread)
    assert snapshot.active_turn == turn

    stream.store(2, 'item/completed', 'tool_activity', scope | {'item': {
        'type': 'agentMessage', 'id': 'answer', 'text': 'Result\x1b', 'private_field': 'private'}})
    stream.store(3, 'item/completed', 'tool_activity', scope | {'turn_id': 'sibling-turn', 'item': {
        'type': 'agentMessage', 'id': 'sibling', 'text': 'private'}})
    stream.store(4, 'item/completed', 'tool_activity', scope | {'item': {
        'type': 'commandExecution', 'id': 'tool', 'command': 'private'}})
    stream.store(5, 'turn/completed', 'turn_state', scope | {'turn': started | {'status': 'completed', 'error': 'private'}})
    stream.watermark(5)
    sequence, active_turn, batch = stream.history(thread, position=(snapshot.committed_through, snapshot.active_turn))
    assert (sequence, active_turn) == (5, None)
    assert batch == {'has_more': False, 'notifications': [
        {'method': 'item/completed', 'params': {'threadId': thread, 'turnId': turn,
                                               'item': {'type': 'agentMessage', 'id': 'answer', 'text': 'Result'}}},
        {'method': 'turn/completed', 'params': {'threadId': thread, 'turn': {
            'id': turn, 'status': 'completed', 'items': [], 'itemsView': 'notLoaded', 'error': None}}},
    ]}
    assert stream.history(thread, position=(sequence, active_turn)) == (5, None, {'notifications': [], 'has_more': False})
    assert snapshot.committed_through == 1 and snapshot.active_turn == turn
    stream.watermark(5, gap='gap')
    with pytest.raises(OktoNexusError, match='lost its history position'):
        stream.history(thread, position=(sequence, active_turn))

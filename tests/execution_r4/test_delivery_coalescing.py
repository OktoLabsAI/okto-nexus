"""Stale deliveries: sent_at in the prompt, and optional same-sender coalescing (#93)."""
import json
import threading
import time
from pathlib import Path

import pytest

from test_agent_recovery_isolation import eventually
from test_canonical_relay import relay_pair, connected_local, local_setup  # noqa: F401  (fixtures)


def test_prompt_is_unchanged_without_sent_at_and_names_it_when_set():
    from okto_nexus.application.runtime_bootstrap import delivery_prompt
    from okto_nexus.domain.delivery import DeliveryEnvelope
    base = DeliveryEnvelope("op", "a", "b", "w", "conversation", ({"type": "text", "text": "hi"},), "root")
    old = delivery_prompt(base.to_dict())
    assert "sent_at" not in old and "queued_before" not in old and "was sent at" not in old
    assert old.startswith("NEXUS DELIVERY: respond to the sender's request using your available capabilities.\n{")
    # Old envelopes keep their request hash.
    assert "sent_at" not in base.canonical_json()
    stamped = DeliveryEnvelope("op", "a", "b", "w", "conversation", ({"type": "text", "text": "hi"},), "root",
                               sent_at="2026-10-25T10:00:00Z", queued_before=2)
    new = delivery_prompt(stamped.to_dict())
    assert ("This message was sent at 2026-10-25T10:00:00Z. If a newer message from the same sender is in this "
            "turn or in your inbox, answer the newest one.") in new
    assert '"queued_before": 2' in new or '"queued_before":2' in new


def test_supersedes_block_lists_earlier_texts_once():
    from okto_nexus.application.runtime_bootstrap import delivery_prompt
    prompt = delivery_prompt({"content": [], "runtime_context": {"supersedes": [
        {"message_id": "m1", "subject": "first", "body": "body one"}]}})
    assert prompt.count("body one") == 1 and "\nSUPERSEDES:" in prompt


def test_coalesce_setting_defaults_off_and_fails_closed():
    from okto_nexus.config import load_config, NexusConfig
    from okto_nexus.errors import OktoNexusError
    assert NexusConfig().delivery_coalesce == "off" and load_config({}).delivery_coalesce == "off"
    assert load_config({"OKTO_NEXUS_DELIVERY_COALESCE": "same_sender"}).delivery_coalesce == "same_sender"
    with pytest.raises(OktoNexusError):
        load_config({"OKTO_NEXUS_DELIVERY_COALESCE": "all"})
    from okto_nexus.application.settings import SETTING_SPECS
    spec = next(s for s in SETTING_SPECS if s.key == "delivery_coalesce")
    assert spec.type == "enum" and spec.choices == ("off", "same_sender")


@pytest.fixture
def held_turn(relay_pair, monkeypatch):
    """The first turn stays open until the test releases it. Records each sent turn text."""
    setup, _, _, peers, factory = relay_pair
    gate, texts = threading.Event(), []
    factory.before_result = lambda: gate.wait(30)
    from test_vertical_inventory import _Native
    original = _Native.send

    async def record(self, verb, payload, operation_id, **kwargs):
        if verb == 'send_turn':
            texts.append(json.dumps(payload))
        return await original(self, verb, payload, operation_id, **kwargs)
    monkeypatch.setattr(_Native, 'send', record)
    yield setup, gate, texts
    gate.set()


def post(setup, monkeypatch, subject, body):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1]))
    from test_pr34_remediation import tool
    setup[2].headers['host'] = '127.0.0.1:8000'
    out = tool(setup[2], setup[3]['caller']['Authorization'].removeprefix('Bearer '), 'message_create',
        dict(project_root=str(setup[-1]), from_agent_id='caller', subject=subject, body=body,
             target=dict(strategy='direct', agent_id='subject')))
    assert out['ok'], out
    return out


def operations(setup):
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        return [dict(r) for r in uow.connection.execute(
            "SELECT o.message_id,o.status,o.reason,m.subject FROM delivery_outbox o JOIN messages m USING(message_id) "
            "WHERE o.recipient_agent_id='subject' ORDER BY o.created_at,o.operation_id")]


@pytest.mark.parametrize('mode', ['same_sender', 'off'])
def test_busy_recipient_coalesces_only_when_enabled(held_turn, monkeypatch, mode):
    setup, gate, texts = held_turn
    setup[0].config.delivery_coalesce = mode
    post(setup, monkeypatch, 'first', 'body one')
    eventually(lambda: len(texts) == 1)
    post(setup, monkeypatch, 'second', 'body two')
    post(setup, monkeypatch, 'third', 'body three')
    ops = operations(setup)
    assert [o['subject'] for o in ops] == ['first', 'second', 'third']
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        # The inbox keeps every row, and the turn in flight is never cancelled.
        assert uow.connection.execute("SELECT COUNT(*) FROM messages WHERE subject IN ('first','second','third')").fetchone()[0] == 3
        stamped = [json.loads(r[0]) for r in uow.connection.execute(
            "SELECT envelope FROM delivery_outbox WHERE recipient_agent_id='subject' ORDER BY created_at,operation_id")]
    assert [e['queued_before'] for e in stamped] == [0, 1, 2] and all(e['sent_at'] for e in stamped)
    if mode == 'off':
        assert [o['status'] for o in ops].count('CANCELLED') == 0
        gate.set()
        eventually(lambda: len(texts) == 3, seconds=20)
        assert not any('SUPERSEDES' in t for t in texts)
        return
    assert ops[0]['status'] != 'CANCELLED'
    assert ops[1]['status'] == 'CANCELLED' and ops[1]['reason'] == 'superseded_by:' + ops[2]['message_id']
    assert ops[2]['status'] != 'CANCELLED'
    gate.set()
    eventually(lambda: len(texts) == 2, seconds=20)
    assert 'SUPERSEDES' in texts[1] and 'body two' in texts[1] and 'body three' in texts[1] and 'body one' not in texts[1]
    assert 'SUPERSEDES' not in texts[0]
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        code = uow.connection.execute(
            "SELECT json_extract(last_error,'$.code') FROM execution_dispatch_outbox WHERE json_extract(last_error,'$.code')='SUPERSEDED_BY_NEWER'").fetchall()
        assert len(code) == 1
    # The refusal projector runs on every pump pass. It must keep the superseded row (#93).
    from okto_nexus.application.execution_domain_delivery import project_delivery_refusals
    with setup[0].connection_factory.unit_of_work() as uow:
        for scope in uow.connection.execute(
                "SELECT DISTINCT server_id,executor_id FROM execution_domain_deliveries").fetchall():
            project_delivery_refusals(uow.connection, server_id=scope[0], executor_id=scope[1])
    after = operations(setup)
    assert after[1]['status'] == 'CANCELLED' and after[1]['reason'] == 'superseded_by:' + ops[2]['message_id']
    # The superseded text travels in the newer turn, so its inbox row is read, not unread.
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        row = uow.connection.execute(
            "SELECT status,delivered_at,read_at,consumer_kind FROM message_deliveries "
            "WHERE message_id=? AND recipient_agent_id='subject'", (ops[1]['message_id'],)).fetchone()
    assert row['status'] == 'read' and row['delivered_at'] and row['read_at'] and row['consumer_kind'] == 'push'


def test_operation_with_a_receipt_is_never_cancelled(held_turn, monkeypatch):
    """The first turn already crossed the send fence, so a newer message cannot cancel it."""
    setup, gate, texts = held_turn
    setup[0].config.delivery_coalesce = 'same_sender'
    post(setup, monkeypatch, 'first', 'body one')
    eventually(lambda: len(texts) == 1)
    post(setup, monkeypatch, 'second', 'body two')
    ops = operations(setup)
    assert ops[0]['status'] != 'CANCELLED' and ops[0]['reason'] is None
    gate.set()
    eventually(lambda: len(texts) == 2, seconds=20)
    assert 'SUPERSEDES' not in texts[1]

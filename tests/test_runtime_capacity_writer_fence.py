"""An already-open writer-v1 producer may still use the pre-capacity enqueue."""
from test_pr34_remediation import runtime as runtime_fixture, open_rest, send_message, tool
from okto_nexus.adapters.outbound.sqlite.runtime_outbox_repo import SqliteRuntimeOutboxRepo

runtime = runtime_fixture


def legacy_enqueue(self, uow, *, envelope, context, endpoint, profile, session_id, now, authorization_revision):
    """The new-message SQL path from43388c8, without the later Python capacity check.

    This uses the real canonical envelope/delivery/UoW, not fabricated FK rows or
    success responses. Writer-v1 markers are shared by the two package versions.
    Idempotency lookup is irrelevant here because every input is a new message.
    """
    assert uow.connection.execute("UPDATE message_deliveries SET consumer_kind='push',consumer_operation_id=? "
        "WHERE delivery_id=? AND status='unread' AND consumer_kind IS NULL",
        (envelope.operation_id, envelope.delivery_id)).rowcount == 1
    values = dict(operation_id=envelope.operation_id, delivery_id=envelope.delivery_id,
        message_id=envelope.message_id, workspace_id=envelope.workspace_id,
        actor_agent_id=context.actor_agent_id, credential_binding=context.credential_binding,
        recipient_agent_id=envelope.recipient_agent_id, endpoint_id=endpoint["endpoint_id"],
        endpoint_revision=endpoint["revision"], profile_revision=profile["revision"] if profile else None,
        runtime_session_id=session_id, envelope=envelope.canonical_json(), request_hash=envelope.request_hash(),
        root_operation_id=envelope.root_operation_id, created_at=now, updated_at=now,
        authorization_revision=authorization_revision)
    uow.connection.execute("INSERT INTO delivery_outbox(" + ",".join(values) + ") VALUES(" +
        ",".join("?" for _ in values) + ")", tuple(values.values()))


def test_store_capacity_fences_the_legacy_enqueue_of_a_compatible_writer(runtime, monkeypatch):
    deps, client, root, _, _, caller = runtime
    assert open_rest(runtime).status_code == 200
    monkeypatch.setattr(deps.runtime_dispatcher, "scan_once", lambda: None)
    deps.config.max_new_roots_per_agent_per_minute = 256
    for _ in range(32):
        send_message(runtime)
    monkeypatch.setattr(SqliteRuntimeOutboxRepo, "enqueue", legacy_enqueue)
    overflow = tool(client, caller, "message_create", {"project_root": root, "from_agent_id": "caller",
        "subject": "legacy writer", "body": "must remain bounded",
        "target": {"strategy": "direct", "agent_id": "worker"}})
    assert not overflow["ok"], "Writer contract v1 allowed an older enqueue to bypass the capacity bound"
    with deps.connection_factory.unit_of_work(write=False) as uow:
        for table in ("messages", "message_deliveries", "delivery_outbox"):
            assert uow.connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 32

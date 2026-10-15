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

"""Use the real SQLite writer fence with synthetic presenter transports."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from okto_nexus.adapters.outbound.sqlite.session_interaction import accept_input
from okto_nexus.application import codex_presenter_channel
from okto_nexus.application.codex_presenter_history import CodexHistorySnapshot
from okto_nexus.application.session_attachment_broker import SessionAttachmentBroker
from okto_nexus.domain.execution.keys import SessionOwnerGeneration
from okto_nexus.domain.session_interaction import InputDeliveryState
from okto_nexus.errors import ErrorCode, OktoNexusError
from tests.session_interaction.test_queue_storage import ALICE, BOB
from tests.session_interaction.test_queue_storage import database as queue_database

database = queue_database
AUDIENCE = 'local-terminal-fixture'


@pytest.fixture
def attachment_store(database):
    factory, scopes = database
    with factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE execution_sessions SET lease_state='ACTIVE'")
    actor = SimpleNamespace(valid={ALICE.authority_ref, BOB.authority_ref}, revision='capability-1', time=100.0)

    @contextmanager
    def fence():
        yield actor.valid.__contains__

    def broker_for():
        return SessionAttachmentBroker(factory, authority_fence=fence,
            current_capability=lambda *_: actor.revision, clock=lambda: actor.time)

    return factory, scopes, actor, broker_for


def offer(broker, scope, intent, *, epoch=None, author=ALICE, takeover=False):
    return broker.prepare(scope=scope, author=author, audience=AUDIENCE, capability_revision='capability-1',
        client_intent_id=intent, access='read' if epoch is None else 'write',
        expected_writer_epoch=epoch, takeover=takeover)


def peer(offer, scope, channel, author=ALICE):
    return {'scope': scope, 'author': author, 'attachment_id': offer.attachment_id,
            'audience': AUDIENCE, 'channel_id': channel, 'ticket': offer.ticket}


def open_presenter(broker, arguments):
    return broker.attach(**arguments, challenge=broker.challenge(**arguments))


def use(broker, scope, attachment, channel, *, author=ALICE, writing=False):
    return broker.require_active(scope=scope, author=author, attachment=attachment,
                                 audience=AUDIENCE, channel_id=channel, writing=writing)


def review(broker, scope):
    return broker.review_writer(scope=scope, author=ALICE, audience=AUDIENCE)


def test_ticket_is_exact_one_use_and_never_materialized_from_a_receipt(attachment_store):
    factory, (scope, sibling), actor, broker_for = attachment_store
    broker = broker_for()
    prepared = offer(broker, scope, 'read-1')
    assert prepared.ticket and prepared.ticket not in repr(prepared)
    retained = offer(broker, scope, 'read-1')
    assert retained.attachment_id == prepared.attachment_id and retained.ticket is None
    with pytest.raises(OktoNexusError) as collision:
        offer(broker, scope, 'read-1', epoch=0)
    assert collision.value.code == ErrorCode.CONFLICT

    context = peer(prepared, scope, 'channel-a')
    for changed in ({'scope': sibling}, {'scope': replace(scope, generation=SessionOwnerGeneration(2))},
                    {'author': BOB}, {'audience': 'foreign-origin'}, {'ticket': 'incorrect-ticket'}):
        with pytest.raises(OktoNexusError):
            broker.challenge(**(context | changed))
    challenge = broker.challenge(**context)
    with pytest.raises(OktoNexusError):
        broker.challenge(**context)
    with pytest.raises(OktoNexusError):
        broker.attach(**(context | {'channel_id': 'new-channel'}), challenge=challenge)
    with factory.unit_of_work(write=False) as uow:
        proof = uow.connection.execute('SELECT ticket_hash,challenge_hash FROM session_attachments').fetchone()
        assert all(len(digest) == 64 for digest in proof)
        assert prepared.ticket not in proof and challenge not in proof
    attachment = broker.attach(**context, challenge=challenge)
    with pytest.raises(OktoNexusError):
        broker.attach(**context, challenge=challenge)
    use(broker, scope, attachment, 'channel-a')
    with pytest.raises(OktoNexusError, match='cannot perform'):
        use(broker, scope, attachment, 'channel-a', writing=True)
    actor.valid.clear()
    with pytest.raises(OktoNexusError, match='login'):
        use(broker, scope, attachment, 'channel-a')
    assert not broker.disconnect(scope=scope, attachment_id=attachment.attachment_id, channel_id='sibling')
    assert broker.disconnect(scope=scope, attachment_id=attachment.attachment_id, channel_id='channel-a')
    assert not broker.disconnect(scope=scope, attachment_id=attachment.attachment_id, channel_id='channel-a')
    with factory.unit_of_work(write=False) as uow:
        conn = uow.connection
        assert tuple(conn.execute('SELECT ticket_hash,challenge_hash FROM session_attachments').fetchone()) == (None, None)
        assert conn.execute('SELECT COUNT(*) FROM execution_operations').fetchone()[0] == 0


def test_concurrent_writers_require_one_current_epoch_and_explicit_takeover(attachment_store):
    _, (scope, _), _, broker_for = attachment_store
    broker = broker_for()
    assert review(broker, scope).epoch == 0 and not review(broker, scope).occupied
    pending = [peer(offer(broker, scope, 'terminal-' + str(i), epoch=0), scope, 'channel-' + str(i))
               for i in range(2)]
    nonces = [broker.challenge(**request) for request in pending]

    def attach(index):
        try:
            return index, broker.attach(**pending[index], challenge=nonces[index])
        except OktoNexusError as error:
            assert error.code == ErrorCode.CONFLICT
            return index, None

    with ThreadPoolExecutor(max_workers=2) as workers:
        winners = [(i, grant) for i, grant in workers.map(attach, range(2)) if grant is not None]
    assert len(winners) == 1
    winner, original = winners[0]
    assert original.writer_epoch == 1 and review(broker, scope).occupied
    reader = open_presenter(broker, peer(offer(broker, scope, 'reader'), scope, 'reader'))
    with pytest.raises(OktoNexusError, match='writer changed'):
        offer(broker, scope, 'without-consent', epoch=1, author=BOB)
    replacement_offer = offer(broker, scope, 'takeover', epoch=1, author=BOB, takeover=True)
    use(broker, scope, original, pending[winner]['channel_id'], writing=True)
    replacement = open_presenter(broker, peer(replacement_offer, scope, 'new-writer', BOB))
    assert replacement.writer_epoch == 2
    with pytest.raises(OktoNexusError):
        use(broker, scope, original, pending[winner]['channel_id'], writing=True)
    use(broker, scope, reader, 'reader')
    broker.detach(scope=scope, author=BOB, attachment_id=replacement.attachment_id, channel_id='new-writer')
    assert review(broker, scope).epoch == 2 and not review(broker, scope).occupied
    assert open_presenter(broker, peer(offer(broker, scope, 'after-detach', epoch=2), scope,
                                      'after-detach')).writer_epoch == 3


def test_expiration_revision_changes_and_restart_fence_the_old_presentation(attachment_store):
    _, (scope, _), actor, broker_for = attachment_store
    broker = broker_for()
    expired = peer(offer(broker, scope, 'expires', epoch=0), scope, 'expired')
    nonce = broker.challenge(**expired)
    actor.time += 31
    with pytest.raises(OktoNexusError):
        broker.attach(**expired, challenge=nonce)
    original = open_presenter(broker, peer(offer(broker, scope, 'original', epoch=0), scope, 'old-writer'))
    actor.revision = 'changed'
    with pytest.raises(OktoNexusError, match='capability changed'):
        use(broker, scope, original, 'old-writer', writing=True)
    actor.revision = None
    with pytest.raises(OktoNexusError, match='capability changed'):
        review(broker, scope)
    actor.revision = 'capability-1'
    restarted = broker_for()
    with pytest.raises(OktoNexusError):
        use(restarted, scope, original, 'old-writer', writing=True)
    assert review(restarted, scope).epoch == 1 and not review(restarted, scope).occupied
    recovered = open_presenter(restarted, peer(offer(restarted, scope, 'restart', epoch=1), scope, 'new-channel'))
    assert recovered.writer_epoch == 2
    with pytest.raises(OktoNexusError):
        use(broker, scope, original, 'old-writer', writing=True)
    actor.time += 121
    with pytest.raises(OktoNexusError):
        use(restarted, scope, recovered, 'new-channel', writing=True)
    assert review(restarted, scope).epoch == 2 and not review(restarted, scope).occupied


def test_writer_is_rechecked_inside_input_admission_after_takeover(attachment_store):
    factory, (scope, _), _, broker_for = attachment_store
    broker = broker_for()
    old = open_presenter(broker, peer(offer(broker, scope, 'old-writer', epoch=0), scope, 'old-channel'))
    use(broker, scope, old, 'old-channel', writing=True)
    new = open_presenter(broker, peer(offer(broker, scope, 'new-writer', epoch=1, author=BOB, takeover=True),
                                     scope, 'new-channel', BOB))

    def enqueue(attachment, author, channel_id, intent):
        with broker.authority_fence() as human, factory.unit_of_work() as uow:
            broker.require_writer_effect(uow, human, scope=scope, author=author,
                attachment=attachment, audience=AUDIENCE, channel_id=channel_id)
            return accept_input(uow, scope=scope, author=author, client_intent_id=intent,
                capability_revision='capability-1', text='Synthetic terminal input',
                now=datetime.now(UTC), verify_new_authority=lambda: None)

    with pytest.raises(OktoNexusError, match='cannot perform'):
        enqueue(old, ALICE, 'old-channel', 'old-input')
    receipt = enqueue(new, BOB, 'new-channel', 'new-input')
    assert receipt.status is InputDeliveryState.QUEUED and receipt.sequence == 1
    with broker.authority_fence() as human, factory.unit_of_work(write=False) as uow:
        with pytest.raises(RuntimeError, match='active write'):
            broker.require_writer_effect(uow, human, scope=scope, author=BOB,
                attachment=new, audience=AUDIENCE, channel_id='new-channel')
        assert uow.connection.execute('SELECT COUNT(*) FROM session_interaction_inputs').fetchone()[0] == 1
        assert uow.connection.execute('SELECT COUNT(*) FROM execution_operations').fetchone()[0] == 0


def test_refresh_extends_only_the_current_presentation(attachment_store):
    factory, (scope, _), actor, broker_for = attachment_store
    broker = broker_for()
    reader = open_presenter(broker, peer(offer(broker, scope, 'reader'), scope, 'reader-channel'))
    args = {'scope': scope, 'author': ALICE, 'attachment': reader, 'audience': AUDIENCE,
            'channel_id': 'reader-channel'}
    actor.time += 100
    with pytest.raises(OktoNexusError):
        broker.refresh(**(args | {'channel_id': 'other-channel'}))
    broker.refresh(**args)
    actor.time += 21
    use(broker, scope, reader, 'reader-channel')
    actor.valid.clear()
    with pytest.raises(OktoNexusError, match='login'):
        broker.refresh(**args)
    actor.valid.add(ALICE.authority_ref)
    actor.time += 100
    with pytest.raises(OktoNexusError):
        broker.refresh(**args)
    with factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM execution_leases').fetchone()[0] == 0
        assert uow.connection.execute('SELECT COUNT(*) FROM execution_operations').fetchone()[0] == 0
        assert uow.connection.execute('SELECT COUNT(*) FROM session_attachment_epochs').fetchone()[0] == 0


@pytest.mark.asyncio
async def test_codex_history_channel_rechecks_authority_and_owner_per_page(attachment_store, monkeypatch):
    factory, (scope, _), actor, broker_for = attachment_store
    broker = broker_for()
    reader = open_presenter(broker, peer(offer(broker, scope, 'history'), scope, 'exact-channel'))
    thread = 'bdfe5b81-54cf-43cf-8001-5de670d3dd69'
    mapping = SimpleNamespace(codex_thread_id=thread)
    state = SimpleNamespace(owner='owner', captures=0, revoke=False)

    async def prove(requested):
        assert requested == scope
        return mapping, state.owner

    def capture(selected_factory, *, mapping, access, context):
        assert selected_factory is factory and mapping.codex_thread_id == thread
        assert context.trusted_local_operator
        state.captures += 1
        if state.revoke:
            actor.valid.clear()
        return CodexHistorySnapshot(0, 0, (), ())

    monkeypatch.setattr(codex_presenter_channel, 'read_codex_history_snapshot', capture)
    channel = codex_presenter_channel.CodexPresenterHistoryChannel(broker=broker, prove_owner=prove,
        access=object(), scope=scope, author=ALICE, attachment=reader, audience=AUDIENCE, channel_id='exact-channel')

    async def history(method='thread/items/list', selected=thread):
        return await channel.page(method=method, params={'threadId': selected})

    with pytest.raises(OktoNexusError, match='exact presentation thread'):
        await history(selected='sibling')
    assert state.captures == 0
    state.revoke = True
    with pytest.raises(OktoNexusError, match='login'):
        await history()
    state.revoke = False
    actor.valid.add(ALICE.authority_ref)
    assert (await history())['data'] == []
    assert (await history('thread/turns/list'))['data'] == []
    assert state.captures == 2
    state.owner = 'replacement'
    with pytest.raises(OktoNexusError, match='owner changed'):
        await history()
    assert state.captures == 2

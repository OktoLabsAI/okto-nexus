"""One-use presentation tickets and an exact-session terminal writer fence."""

import hashlib
import secrets
import time
from dataclasses import asdict, dataclass, field
from typing import Literal

from ..adapters.outbound.sqlite.session_interaction import (
    _current_session,
    _scope_params,
)
from ..domain.attention import digest
from ..domain.session_interaction import MAX_SQLITE_INTEGER, InputAuthor, InputScope
from ..errors import ErrorCode, OktoNexusError

AttachmentAccess = Literal['read', 'write']
_OFFER_SECONDS = 30
_PRESENTER_SECONDS = 120


@dataclass(frozen=True, slots=True)
class PreparedPresenter:
    attachment_id: str
    state: str
    ticket: str | None = field(default=None, repr=False)


@dataclass(frozen=True, slots=True)
class PresenterAttachment:
    attachment_id: str
    access: AttachmentAccess
    writer_epoch: int | None


@dataclass(frozen=True, slots=True)
class PresenterWriterReview:
    epoch: int
    occupied: bool
    capability_revision: str


def _secret_hash(value):
    if type(value) is not str or not 1 <= len(value) <= 160 or not value.isascii():
        raise OktoNexusError(ErrorCode.PERMISSION_DENIED, 'The presentation credential is unavailable.', {})
    return hashlib.sha256(value.encode('ascii')).hexdigest()


def _key(scope):
    return scope.session.server_id, scope.session.executor_id, scope.session.session_id


class SessionAttachmentBroker:
    """Persist presenter state. The transport supplies a verified audience and unique channel."""

    def __init__(self, factory, *, authority_fence, current_capability, clock=time.monotonic):
        self.factory = factory
        self.authority_fence = authority_fence
        self.current_capability = current_capability
        self.clock = clock
        self.instance = secrets.token_hex(16)

    def _current_revision(self, uow, resolve_human, scope, author, access, audience):
        if not resolve_human(author.authority_ref):
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED, 'The presentation login is unavailable.', {})
        if not _current_session(uow.connection, _scope_params(scope), require_active_lease=True):
            raise OktoNexusError(ErrorCode.CONFLICT, 'The exact presentation capability changed.', {})
        revision = self.current_capability(uow, scope, author, access, audience)
        if type(revision) is not str or not 1 <= len(revision) <= 160 or not revision.isprintable():
            raise OktoNexusError(ErrorCode.CONFLICT, 'The exact presentation capability changed.', {})
        return revision

    def _authorize(self, uow, resolve_human, scope, author, access, audience, revision):
        if self._current_revision(uow, resolve_human, scope, author, access, audience) != revision:
            raise OktoNexusError(ErrorCode.CONFLICT, 'The exact presentation capability changed.', {})

    def review_reader(self, *, scope, author, audience) -> str:
        with self.authority_fence() as human, self.factory.unit_of_work(write=False) as uow:
            return self._current_revision(uow, human, scope, author, 'read', audience)

    @staticmethod
    def _epoch(conn, scope):
        row = conn.execute("""
            SELECT writer_epoch FROM session_attachment_epochs
            WHERE server_id=? AND executor_id=? AND session_id=?
        """, _key(scope)).fetchone()
        return row[0] if row is not None else 0

    def _expire(self, conn, scope, now):
        conn.execute("""
            UPDATE session_attachments SET state='EXPIRED',ticket_hash=NULL,challenge_hash=NULL
            WHERE server_id=? AND executor_id=? AND session_id=?
              AND state IN ('PREPARED','CHALLENGE','ACTIVE')
              AND (broker_instance<>? OR expires_monotonic<=?)
        """, (*_key(scope), self.instance, now))

    def _row(self, conn, scope, author, attachment_id, now):
        row = conn.execute("""
            SELECT * FROM session_attachments WHERE attachment_id=?
              AND server_id=? AND executor_id=? AND session_id=? AND scope_hash=?
              AND authority_ref=? AND surface=? AND broker_instance=? AND expires_monotonic>?
        """, (attachment_id, *_key(scope), digest(asdict(scope)), author.authority_ref, author.surface,
              self.instance, now)).fetchone()
        if row is None:
            raise OktoNexusError(ErrorCode.NOT_FOUND, 'The exact presentation is unavailable.', {})
        return row

    def review_writer(self, *, scope, author, audience) -> PresenterWriterReview:
        """Read the present writer epoch under the exact current human authority."""
        with self.authority_fence() as human, self.factory.unit_of_work(write=False) as uow:
            revision = self._current_revision(uow, human, scope, author, 'write', audience)
            conn = uow.connection
            writer = conn.execute("""
                SELECT 1 FROM session_attachments WHERE server_id=? AND executor_id=? AND session_id=?
                  AND state='ACTIVE' AND access='write' AND broker_instance=? AND expires_monotonic>?
            """, (*_key(scope), self.instance, self.clock())).fetchone()
            return PresenterWriterReview(self._epoch(conn, scope), writer is not None, revision)

    def prepare(self, *, scope: InputScope, author: InputAuthor, access: AttachmentAccess,
                audience: str, capability_revision: str, client_intent_id: str,
                expected_writer_epoch: int | None = None, takeover: bool = False) -> PreparedPresenter:
        if (access not in ('read', 'write') or type(takeover) is not bool
                or any(type(value) is not str or not 1 <= len(value) <= 160 or not value.isprintable()
                       for value in (audience, capability_revision, client_intent_id))
                or access == 'read' and (expected_writer_epoch is not None or takeover)
                or access == 'write' and (type(expected_writer_epoch) is not int
                                         or not 0 <= expected_writer_epoch < MAX_SQLITE_INTEGER)):
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, 'Review the exact presentation effect.', {})
        identity = (*_key(scope), digest(asdict(scope)), author.authority_ref, author.surface, client_intent_id)
        intent_hash = digest({'revision': capability_revision, 'audience': audience, 'access': access,
                              'expected_writer_epoch': expected_writer_epoch, 'takeover': takeover})
        with self.authority_fence() as human, self.factory.unit_of_work() as uow:
            self._authorize(uow, human, scope, author, access, audience, capability_revision)
            conn = uow.connection
            now = self.clock()
            self._expire(conn, scope, now)
            prior = conn.execute("""
                SELECT attachment_id,intent_hash,state FROM session_attachments
                WHERE server_id=? AND executor_id=? AND session_id=? AND scope_hash=?
                  AND authority_ref=? AND surface=? AND client_intent_id=?
            """, identity).fetchone()
            if prior is not None:
                if prior['intent_hash'] != intent_hash:
                    raise OktoNexusError(ErrorCode.CONFLICT, 'The presentation intent already has a different effect.', {})
                return PreparedPresenter(prior['attachment_id'], prior['state'])
            if access == 'write':
                self._verify_writer(conn, scope, expected_writer_epoch, takeover)
            attachment_id = 'att_' + secrets.token_hex(16)
            ticket = secrets.token_urlsafe(32)
            conn.execute("""
                INSERT INTO session_attachments (
                    attachment_id,server_id,executor_id,session_id,scope_hash,authority_ref,surface,client_intent_id,
                    intent_hash,broker_instance,capability_revision,audience,access,expected_writer_epoch,takeover,
                    state,ticket_hash,expires_monotonic
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'PREPARED',?,?)
            """, (attachment_id, *identity, intent_hash, self.instance, capability_revision, audience, access,
                  expected_writer_epoch, takeover, _secret_hash(ticket), now + _OFFER_SECONDS))
            return PreparedPresenter(attachment_id, 'PREPARED', ticket)

    def _verify_writer(self, conn, scope, epoch, takeover):
        writer = conn.execute("""
            SELECT attachment_id FROM session_attachments WHERE server_id=? AND executor_id=? AND session_id=?
              AND state='ACTIVE' AND access='write'
        """, _key(scope)).fetchone()
        if self._epoch(conn, scope) != epoch or (writer is not None and not takeover):
            raise OktoNexusError(ErrorCode.CONFLICT, 'The terminal writer changed. Review ownership again.', {})
        return writer

    def _handshake(self, uow, human, scope, author, attachment_id, audience, ticket, now):
        row = self._row(uow.connection, scope, author, attachment_id, now)
        if row['audience'] != audience or row['ticket_hash'] is None or not secrets.compare_digest(
                row['ticket_hash'], _secret_hash(ticket)):
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED, 'The presentation ticket is unavailable.', {})
        self._authorize(uow, human, scope, author, row['access'], audience, row['capability_revision'])
        return row

    def challenge(self, *, scope, author, attachment_id, audience, channel_id, ticket):
        """Bind the ticket to a fresh transport connection and return one challenge."""
        if type(channel_id) is not str or not 1 <= len(channel_id) <= 160 or not channel_id.isprintable():
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, 'A presentation channel is required.', {})
        with self.authority_fence() as human, self.factory.unit_of_work() as uow:
            row = self._handshake(uow, human, scope, author, attachment_id, audience, ticket, self.clock())
            if row['state'] != 'PREPARED':
                raise OktoNexusError(ErrorCode.CONFLICT, 'The presentation handshake has already started.', {})
            nonce = secrets.token_urlsafe(32)
            uow.connection.execute("""
                UPDATE session_attachments SET state='CHALLENGE',challenge_hash=?,channel_id=? WHERE attachment_id=?
            """, (_secret_hash(nonce), channel_id, attachment_id))
            return nonce

    def attach(self, *, scope, author, attachment_id, audience, channel_id, ticket, challenge) -> PresenterAttachment:
        with self.authority_fence() as human, self.factory.unit_of_work() as uow:
            now = self.clock()
            row = self._handshake(uow, human, scope, author, attachment_id, audience, ticket, now)
            if (row['state'] != 'CHALLENGE' or row['channel_id'] != channel_id
                    or row['challenge_hash'] is None
                    or not secrets.compare_digest(row['challenge_hash'], _secret_hash(challenge))):
                raise OktoNexusError(ErrorCode.PERMISSION_DENIED, 'The presentation handshake is unavailable.', {})
            conn = uow.connection
            self._expire(conn, scope, now)
            epoch = None
            if row['access'] == 'write':
                writer = self._verify_writer(conn, scope, row['expected_writer_epoch'], row['takeover'])
                epoch = row['expected_writer_epoch'] + 1
                if writer is not None:
                    conn.execute("UPDATE session_attachments SET state='REPLACED' WHERE attachment_id=?", (writer[0],))
                conn.execute("""
                    INSERT INTO session_attachment_epochs VALUES (?,?,?,?)
                    ON CONFLICT(server_id,executor_id,session_id) DO UPDATE SET writer_epoch=excluded.writer_epoch
                """, (*_key(scope), epoch))
            conn.execute("""
                UPDATE session_attachments SET state='ACTIVE',writer_epoch=?,ticket_hash=NULL,challenge_hash=NULL,
                    expires_monotonic=? WHERE attachment_id=?
            """, (epoch, now + _PRESENTER_SECONDS, attachment_id))
            return PresenterAttachment(attachment_id, row['access'], epoch)

    def require_active(self, *, scope, author, attachment: PresenterAttachment, audience, channel_id, writing=False):
        """Check a live presenter before a transport read or preliminary write review."""
        with self.authority_fence() as human, self.factory.unit_of_work(write=False) as uow:
            self._verify_active(uow, human, scope, author, attachment, audience, channel_id, self.clock(), writing)

    def require_writer_effect(self, uow, human, *, scope, author, attachment, audience, channel_id):
        """Verify the presenter inside the canonical effect transaction and human fence."""
        uow.require_active_writer()
        self._verify_active(uow, human, scope, author, attachment, audience, channel_id, self.clock(), True)

    def refresh(self, *, scope, author, attachment, audience, channel_id):
        """Extend only the current presentation on its original authenticated channel."""
        with self.authority_fence() as human, self.factory.unit_of_work() as uow:
            now = self.clock()
            self._verify_active(uow, human, scope, author, attachment, audience, channel_id,
                                now, attachment.access == 'write')
            uow.connection.execute("""
                UPDATE session_attachments SET expires_monotonic=? WHERE attachment_id=?
            """, (now + _PRESENTER_SECONDS, attachment.attachment_id))

    def _verify_active(self, uow, human, scope, author, attachment, audience, channel_id, now, writing):
        row = self._row(uow.connection, scope, author, attachment.attachment_id, now)
        if (row['state'] != 'ACTIVE' or row['audience'] != audience or row['channel_id'] != channel_id
                or row['access'] != attachment.access or row['writer_epoch'] != attachment.writer_epoch
                or writing and (row['access'] != 'write' or self._epoch(uow.connection, scope) != row['writer_epoch'])):
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED, 'This presentation cannot perform the requested action.', {})
        self._authorize(uow, human, scope, author, row['access'], audience, row['capability_revision'])

    def detach(self, *, scope, author, attachment_id, channel_id):
        """Release a presentation receipt. The engine and its queue are independent."""
        with self.authority_fence() as human, self.factory.unit_of_work() as uow:
            if not human(author.authority_ref):
                raise OktoNexusError(ErrorCode.PERMISSION_DENIED, 'The presentation login is unavailable.', {})
            row = self._row(uow.connection, scope, author, attachment_id, self.clock())
            if row['channel_id'] != channel_id or row['state'] not in ('ACTIVE', 'DETACHED'):
                raise OktoNexusError(ErrorCode.NOT_FOUND, 'The exact presentation is unavailable.', {})
            uow.connection.execute("UPDATE session_attachments SET state='DETACHED' WHERE attachment_id=?", (attachment_id,))

    def disconnect(self, *, scope, attachment_id, channel_id) -> bool:
        """Release the exact disconnected transport even if its login was revoked."""
        with self.factory.unit_of_work() as uow:
            changed = uow.connection.execute("""
                UPDATE session_attachments SET state='DETACHED',ticket_hash=NULL,challenge_hash=NULL
                WHERE attachment_id=? AND server_id=? AND executor_id=? AND session_id=? AND scope_hash=?
                  AND broker_instance=? AND channel_id=? AND state IN ('CHALLENGE','ACTIVE')
            """, (attachment_id, *_key(scope), digest(asdict(scope)), self.instance, channel_id))
            return changed.rowcount == 1

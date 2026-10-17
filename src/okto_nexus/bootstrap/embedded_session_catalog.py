"""Bounded canonical session/location lookup; not proof of native ownership."""
import asyncio
import os

from nexus_connector_core import CoreError


class EmbeddedSessionCatalog:
    page_size = 128

    def __init__(self, owner):
        self.owner = owner

    def _name(self, session_id):
        return self.owner.host._journal_path(self.owner.channel.executor_id, session_id).name

    def register(self, session_id):
        """Persist the canonical location before composing a session journal."""
        owner = self.owner
        key = owner.channel.server_id, owner.channel.executor_id, session_id
        name = self._name(session_id)
        with owner.factory.unit_of_work() as uow:
            owner.verify(uow=uow)
            row = uow.connection.execute('SELECT local_journal_name FROM execution_sessions '
                'WHERE server_id=? AND executor_id=? AND session_id=?', key).fetchone()
            if row is None or row[0] not in (None, name):
                raise CoreError('SCOPE_MISMATCH', 'embedded_journal_catalog')
            if row[0] is None:
                uow.connection.execute('UPDATE execution_sessions SET local_journal_name=? '
                    'WHERE server_id=? AND executor_id=? AND session_id=?', (name, *key))

    def backfill_page(self):
        """An interruption retains every committed page; there is no history cap."""
        owner = self.owner
        key = owner.channel.server_id, owner.channel.executor_id
        with owner.factory.unit_of_work() as uow:
            owner.verify(uow=uow)
            rows = uow.connection.execute('SELECT session_id FROM execution_sessions '
                'WHERE server_id=? AND executor_id=? AND local_journal_name IS NULL '
                'ORDER BY rowid LIMIT ?', (*key, self.page_size)).fetchall()
            uow.connection.executemany('UPDATE execution_sessions SET local_journal_name=? '
                'WHERE server_id=? AND executor_id=? AND session_id=? AND local_journal_name IS NULL',
                ((self._name(row[0]), *key, row[0]) for row in rows))
            return len(rows)

    async def backfill(self):
        while await asyncio.to_thread(self.backfill_page) == self.page_size:
            pass

    def verify_names(self, names):
        names = set(names)
        if not names:
            return
        if len(names) > self.page_size:
            raise ValueError('Catalog lookup exceeds its page budget.')
        owner = self.owner
        with owner.factory.unit_of_work(write=False) as uow:
            owner.verify(uow=uow)
            found = {row[0] for row in uow.connection.execute(
                'SELECT local_journal_name FROM execution_sessions WHERE server_id=? AND executor_id=? '
                'AND local_journal_name IN (' + ','.join('?' for _ in names) + ')',
                (owner.channel.server_id, owner.channel.executor_id, *names))}
            if found != names:
                raise CoreError('JOURNAL_UNAVAILABLE', 'embedded_shared_resources')

    async def audit_files(self):
        """Stream directory entries in bounded pages, without a history-sized set.

        This first implementation still audits the directory on startup. Moving
        that audit out of admission requires a durable verified-store frontier.
        """
        try:
            entries = await asyncio.to_thread(os.scandir, self.owner.host.store_dir)
        except FileNotFoundError:
            return False
        ledger_present = ledger_seen = journal_present = False
        def page():
            result = []
            for _ in range(self.page_size):
                entry = next(entries, None)
                if entry is None:
                    break
                result.append(entry.name)
            return result
        try:
            while names := await asyncio.to_thread(page):
                ledger_present |= 'owned-slots.db' in names
                bases = {name[:-4] if name.endswith(('-wal', '-shm')) else name for name in names}
                ledger_seen |= 'owned-slots.db' in bases
                bases.discard('owned-slots.db')
                journal_present |= bool(bases)
                await asyncio.to_thread(self.verify_names, bases)
        finally:
            await asyncio.to_thread(entries.close)
        if (journal_present or ledger_seen) and not ledger_present:
            raise CoreError('JOURNAL_UNAVAILABLE', 'embedded_shared_resources')
        return ledger_present

    def pending_agents(self):
        owner = self.owner
        with owner.factory.unit_of_work(write=False) as uow:
            owner.verify(uow=uow)
            return {row[0] for row in uow.connection.execute(
                'SELECT DISTINCT o.subject_agent_id FROM execution_sessions s '
                'JOIN execution_operations o ON o.server_id=s.server_id AND o.executor_id=s.executor_id '
                'AND o.operation_id=s.open_operation_id WHERE s.server_id=? AND s.executor_id=? '
                'AND s.local_retirement_json IS NULL '
                'UNION SELECT agent_id FROM execution_agent_recovery WHERE server_id=? AND executor_id=? '
                "AND (generation<>? OR state<>'READY')",
                (owner.channel.server_id, owner.channel.executor_id) * 2 +
                (owner.channel.connection_generation,))}

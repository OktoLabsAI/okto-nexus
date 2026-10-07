"""Independent, retained recovery/publication workers for local subjects.

Publication lag is not evidence of native failure. A slow worker is retained
and observed; it is never duplicated or used to revoke a healthy native lease.
"""
import asyncio
import random
import time

from nexus_connector_core import CoreError, ShutdownPolicy

from .embedded_reconciliation import EmbeddedReconciliation


class EmbeddedAgentRecovery:
    observation_timeout = 5.0

    def __init__(self, owner):
        self.owner = owner
        self.tasks = {}
        self.started = {}
        self.delayed = set()
        self.blocked = set()
        self.retry_at = {}
        self.attempts = {}
        self.errors = {}
        self.initialized = False
        self._tick_lock = asyncio.Lock()

    def _state(self, agent_id, state, error=None):
        owner = self.owner
        code = getattr(error, 'code', type(error).__name__) if error else None
        with owner.factory.unit_of_work() as uow:
            owner.verify(uow=uow)
            uow.connection.execute(
                "INSERT INTO execution_agent_recovery(server_id,executor_id,agent_id,generation,state,attempts,error_code,updated_at) "
                "VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(server_id,executor_id,agent_id) DO UPDATE SET "
                "generation=excluded.generation,state=excluded.state,attempts=excluded.attempts,"
                "error_code=excluded.error_code,updated_at=excluded.updated_at",
                (owner.channel.server_id, owner.channel.executor_id, agent_id, owner.channel.connection_generation,
                 state, self.attempts.get(agent_id, 0), code, owner.deps.clock.now_iso()))

    async def initialize(self):
        if self.initialized:
            return
        owner = self.owner
        records = await asyncio.to_thread(EmbeddedReconciliation(owner)._records)
        # Only unattributable/shared resources block the host. Missing or bad
        # journals with a known subject are handled by that subject's worker.
        names = {owner.host._journal_path(owner.channel.executor_id, r['session_id']).name for r in records}
        files = await asyncio.to_thread(lambda: {p.name for p in owner.host.store_dir.iterdir()}
                                       if owner.host.store_dir.exists() else set())
        allowed = names | {'owned-slots.db'}
        allowed |= {name + suffix for name in allowed for suffix in ('-wal', '-shm')}
        if not files.issubset(allowed) or (files & names and 'owned-slots.db' not in files):
            raise CoreError('JOURNAL_UNAVAILABLE', 'embedded_shared_resources')
        if 'owned-slots.db' in files:
            ledger = await owner.host._ledger()
            known = {r['session_id']: r['open_operation_id'] for r in records}
            after, high = 0, None
            for _ in range(256):
                page = await ledger.owned_slot_page(after_rowid=after, high_water_rowid=high, limit=128)
                for slot in page.reservations:
                    if (slot.key.server_id != owner.channel.server_id or slot.key.executor_id != owner.channel.executor_id
                            or known.get(slot.key.session_id) != slot.opening_operation_id):
                        raise CoreError('SCOPE_MISMATCH', 'embedded_shared_resources')
                high = page.high_water_rowid
                if page.next_after_rowid is None:
                    break
                if page.next_after_rowid <= after:
                    raise CoreError('JOURNAL_UNAVAILABLE', 'embedded_shared_resources')
                after = page.next_after_rowid
            else:
                raise CoreError('CAPACITY_EXCEEDED', 'embedded_shared_resources')
        self.blocked = {r['agent_id'] for r in records}
        for agent_id in self.blocked:
            await asyncio.to_thread(self._state, agent_id, 'RECOVERING')
        self.initialized = True

    async def fail(self, agent_id, error):
        # Loss of the shared owner/database must still stop the whole host.
        await asyncio.to_thread(self.owner.verify)
        self.blocked.add(agent_id)
        self.errors[agent_id] = error
        await asyncio.to_thread(self._state, agent_id, 'RECOVERING', error)
        await asyncio.to_thread(self.owner._recovery_event, 'RECOVERY_AGENT_BLOCKED',
            f"{type(error).__name__}: {getattr(error, 'code', 'UNAVAILABLE')} at {getattr(error, 'stage', 'agent runtime history')}",
            agent_id=agent_id)

    async def _contain(self, agent_id):
        owner = self.owner
        # Do not hold an executor-wide gate while joining this agent's producers.
        workers = [t for t, agent in owner.worker_agents.items() if agent == agent_id and not t.done()]
        sessions = [(key, session) for key, session in owner.sessions.items()
                    if session['scope']['agent_id'] == agent_id]
        for session_id, session in sessions:
            if session['executor'] is None:
                continue
            runtime = await session['executor']._runtime()
            report = await runtime.shutdown(ShutdownPolicy(5, 5))
            if ('unknown' in report.session_outcomes.values() or any(
                    facts['process_state'] != 'STOPPED' or facts['release_pending']
                    for facts in runtime.shutdown_resources().values())):
                raise CoreError('RECONCILIATION_REQUIRED', 'embedded_agent_containment')
            if not await owner.host.close_native_actions(executor_id=owner.channel.executor_id,
                    session_id=session_id, timeout_seconds=5):
                raise CoreError('RECONCILIATION_REQUIRED', 'embedded_agent_native_actions')
        if workers:
            await asyncio.gather(*workers, return_exceptions=True)
            # An opening may have been between lease application and publishing
            # its executor when the first containment snapshot was taken.
            # Re-inspect only after every admitted producer has returned.
            return await self._contain(agent_id)
        for session_id, session in sessions:
            renewal = session.get('renew_task')
            if renewal is not None and not renewal.done():
                await asyncio.shield(renewal)
            owner.sessions.pop(session_id, None)

    async def _recover(self, agent_id):
        owner = self.owner
        self.attempts[agent_id] = self.attempts.get(agent_id, 0) + 1
        await self._contain(agent_id)
        await owner._recover_publications(agent_id=agent_id)
        await owner.events.recover(agent_id=agent_id)
        if not await EmbeddedReconciliation(owner).recover(agent_id=agent_id):
            raise CoreError('RECONCILIATION_REQUIRED', 'embedded_agent_history')
        for row in await asyncio.to_thread(EmbeddedReconciliation(owner)._records, agent_id):
            await owner.tools.release_session(row['session_id'])
        await self._retire_closed(agent_id)
        await asyncio.to_thread(self._state, agent_id, 'READY')
        self.blocked.discard(agent_id)
        self.errors.pop(agent_id, None)
        self.attempts.pop(agent_id, None)
        self.retry_at.pop(agent_id, None)
        await asyncio.to_thread(owner._recovery_event, 'RECOVERY_AGENT_READY',
            'Agent history reconciled. Previous work was not replayed.', agent_id=agent_id)

    async def _publish(self, agent_id):
        def progress():
            self.started[agent_id] = time.monotonic()
            self.delayed.discard(agent_id)
        await self.owner._recover_publications(agent_id=agent_id, progress=progress)
        await self.owner.events.recover(agent_id=agent_id, live_only=True, progress=progress)
        await self._retire_closed(agent_id)

    async def _retire_closed(self, agent_id):
        owner = self.owner
        def closed():
            with owner.factory.unit_of_work(write=False) as uow:
                owner.verify(uow=uow)
                return [dict(r) for r in uow.connection.execute(
                    "SELECT s.session_id,s.lifecycle_state FROM execution_local_streams l "
                    "JOIN execution_sessions s USING(server_id,executor_id,session_id) "
                    "WHERE l.server_id=? AND l.executor_id=? AND l.agent_id=? AND l.drained=0 "
                    "AND s.lifecycle_state IN ('CLOSED','FAILED')",
                    (owner.channel.server_id, owner.channel.executor_id, agent_id))]
        for row in await asyncio.to_thread(closed):
            # Prove resource release and that every Core event was committed
            # before ending polling. Receipt stages themselves are unchanged.
            await EmbeddedReconciliation(owner).release_session(row['session_id'],
                failed_open=row['lifecycle_state'] == 'FAILED')
            def commit():
                with owner.factory.unit_of_work() as uow:
                    owner.verify(uow=uow)
                    key = (owner.channel.server_id, owner.channel.executor_id, row['session_id'])
                    uow.connection.execute("UPDATE execution_local_streams SET drained=1 "
                        "WHERE server_id=? AND executor_id=? AND session_id=?", key)
                    uow.connection.execute("UPDATE execution_local_publications SET terminal=1 "
                        "WHERE server_id=? AND executor_id=? AND session_id=?", key)
            await asyncio.to_thread(commit)

    async def _run(self, agent_id, recovering):
        try:
            if recovering:
                await self._recover(agent_id)
            else:
                await self._publish(agent_id)
        except Exception as error:
            if self.owner._stopping.is_set():
                return
            try:
                await self.fail(agent_id, error)
                delay = min(30, 2 ** min(self.attempts.get(agent_id, 0), 5))
                self.retry_at[agent_id] = time.monotonic() + delay * random.uniform(.8, 1.2)
            except Exception as shared_error:
                self.owner.failure = shared_error
                await self.owner.failed()

    def _pending_subjects(self):
        with self.owner.factory.unit_of_work(write=False) as uow:
            self.owner.verify(uow=uow)
            return {row[0] for row in uow.connection.execute(
                "SELECT DISTINCT o.subject_agent_id FROM execution_local_publications p "
                "JOIN execution_operations o USING(server_id,executor_id,operation_id) "
                "WHERE p.server_id=? AND p.executor_id=? AND p.terminal=0 "
                "UNION SELECT agent_id FROM execution_local_streams "
                "WHERE server_id=? AND executor_id=? AND drained=0",
                (self.owner.channel.server_id, self.owner.channel.executor_id) * 2)}

    async def tick(self, *, manual=False, agent_id=None):
        async with self._tick_lock:
            await self._tick(manual=manual, agent_id=agent_id)

    async def _tick(self, *, manual=False, agent_id=None):
        if self.owner._stopping.is_set():
            return
        target_agent_id = agent_id
        now = time.monotonic()
        for agent_id, task in list(self.tasks.items()):
            if task.done():
                task.result()
                del self.tasks[agent_id]
                self.delayed.discard(agent_id)
            elif (now - self.started[agent_id] >= self.observation_timeout
                    and agent_id not in self.blocked and agent_id not in self.delayed):
                # A publication observer can be slow while the harness is
                # healthy. Keep its single worker and native lease alive.
                # Actual journal/stream errors still enter isolated recovery.
                self.delayed.add(agent_id)
                await asyncio.to_thread(self.owner._recovery_event, 'RECOVERY_PUBLICATION_DELAYED',
                    'Publication is delayed; native execution and lease renewal remain active.', agent_id=agent_id)
        enabled = manual or await asyncio.to_thread(self.owner._recovery_enabled)
        subjects = self.blocked | await asyncio.to_thread(self._pending_subjects)
        subjects |= {s['scope']['agent_id'] for s in self.owner.sessions.values()}
        subjects = subjects if target_agent_id is None else subjects & {target_agent_id}
        for agent_id in subjects:
            recovering = agent_id in self.blocked
            if agent_id in self.tasks or (recovering and (not enabled or
                    (not manual and now < self.retry_at.get(agent_id, 0)))):
                continue
            self.started[agent_id] = now
            self.tasks[agent_id] = asyncio.create_task(self._run(agent_id, recovering),
                name='embedded-agent-' + agent_id)

    async def observe(self, *, timeout=1.0):
        if self.tasks:
            await asyncio.wait(tuple(self.tasks.values()), timeout=timeout)

    async def close(self):
        if self.tasks:
            await asyncio.gather(*tuple(self.tasks.values()))

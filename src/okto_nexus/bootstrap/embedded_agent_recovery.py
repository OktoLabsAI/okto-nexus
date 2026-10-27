"""Independent, retained recovery/publication workers for local subjects.

Publication lag is not evidence of native failure. A slow worker is retained
and observed; it is never duplicated or used to revoke a healthy native lease.
"""
import asyncio
import logging
import random
import re
import secrets
import time

from nexus_connector_core import (CoreError, ShutdownPolicy,
    require_audit_snapshot_not_rolled_back)
from ..errors import ErrorCode, OktoNexusError

from .embedded_reconciliation import EmbeddedReconciliation
from .embedded_events import EmbeddedPublicationDeferred


def _diagnostic(error):
    details = getattr(error, 'details', None)
    reason = details.get('reason') if isinstance(details, dict) else None
    # Keep technical reason identifiers, never arbitrary provider messages,
    # commands, URLs or environment values in the shared recovery log.
    suffix = f" ({reason})" if isinstance(reason, str) and re.fullmatch(r'[a-z][a-z0-9_.-]{0,79}', reason) else ''
    return (f"{type(error).__name__}: {getattr(error, 'code', 'UNAVAILABLE')} "
            f"at {getattr(error, 'stage', 'agent runtime history')}{suffix}")


_REASON = re.compile(r'[A-Za-z][A-Za-z0-9_.-]{0,79}')


def _containment_reason(session):
    """Technical cause of a containment, safe to show to an operator."""
    error = session.get('recovery_error')
    reason = session.get('recovery_reason')
    if reason is None and error is not None:
        code = getattr(error, 'code', None) or type(error).__name__
        reason = getattr(code, 'value', code)
    return reason if isinstance(reason, str) and _REASON.fullmatch(reason) else 'SESSION_CONTAINED'


# CROSS JOIN pins the order: the agent's streams first, then the partial index
# idx_event_ingress_error (error rows only). Without it SQLite starts from the
# ingress table and reads every row of the executor.
STREAM_FAULT_SQL = (
    "SELECT DISTINCT s.session_id FROM execution_local_streams l "
    "CROSS JOIN execution_sessions s USING(server_id,executor_id,session_id) "
    "CROSS JOIN execution_event_ingress e USING(server_id,executor_id,session_id,stream_epoch) "
    "WHERE l.server_id=? AND l.executor_id=? AND l.agent_id=? AND l.drained=0 "
    "AND s.lifecycle_state NOT IN ('CLOSED','FAILED') AND e.event_type='error' "
    "AND json_extract(e.payload_json,'$.native_type')='core.event_pump_failed' "
    "AND json_extract(e.payload_json,'$.payload.code')='EVENT_STREAM_UNAVAILABLE'")


class EmbeddedAgentRecovery:
    observation_timeout = 5.0
    # Seconds the host keeps its short tick after the last sign of work.
    busy_linger = 5.0
    # Seconds between safety-net stream health checks of one live agent.
    health_interval = 60.0
    # Seconds between two counter log lines.
    counter_interval = 300.0

    def __init__(self, owner):
        self.owner = owner
        self.tasks = {}
        self.started = {}
        self.delayed = set()
        self.blocked = set()
        self.retry_at = {}
        # Idle back-off by agent. It is separate from retry_at, which holds error back-off.
        self.next_due_at = {}
        # Next safety-net stream health check by agent. A missing key means: check now.
        self.health_due_at = {}
        self.counters = {'busy_ticks': 0, 'idle_ticks': 0, 'stream_checks': 0}
        self._logged = {}
        self._counter_log_at = time.monotonic() + self.counter_interval
        self.attempts = {}
        self.errors = {}
        self.current_errors = {}
        self.publication_pending = set()
        self.initialized = False
        self._tick_lock = asyncio.Lock()
        self.session_tasks = {}
        self.session_retry_at = {}
        self.registry_import_task = None
        self.last_active = time.monotonic()
        self.unsettled = True
        self._registry_stop = asyncio.Event()
        from .embedded_retirement_maintenance import EmbeddedRetirementMaintenance
        self.retirement = EmbeddedRetirementMaintenance(self)

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
        from .embedded_session_catalog import EmbeddedSessionCatalog
        catalog = EmbeddedSessionCatalog(owner)
        await catalog.backfill()
        from ..adapters.outbound.sqlite.execution_embedded_store_binding import (
            bind_embedded_store, require_no_missing_store,
        )
        async def bind_ledger(ledger):
            store_id = await ledger.physical_store_id()
            def bind_store():
                with owner.factory.unit_of_work() as uow:
                    owner.verify(uow=uow)
                    bind_embedded_store(uow.connection, store_id=store_id,
                        recorded_at=owner.deps.clock.now_iso())
            await asyncio.to_thread(bind_store)
            return store_id
        async def verify_anchor_snapshot(ledger, store_id):
            from ..adapters.outbound.sqlite.execution_embedded_store_binding import stored_audit_anchor
            def read_stored():
                with owner.factory.unit_of_work(write=False) as uow:
                    owner.verify(uow=uow)
                    return stored_audit_anchor(uow.connection, store_id=store_id)
            stored = await asyncio.to_thread(read_stored)
            if stored is not None:
                require_audit_snapshot_not_rolled_back(stored,
                    await ledger.journal_audit_anchor(),
                    await ledger.journal_registry_head())
        # Only unattributable/shared resources block the host. Missing or bad
        # journals with a known subject are handled by that subject's worker.
        if await catalog.audit_files():
            ledger = await owner.host._ledger()
            store_id = await bind_ledger(ledger)
            await verify_anchor_snapshot(ledger, store_id)
            # A fenced connection's HELD capacity never crossed native
            # admission. Cancel those holds atomically before the legacy
            # process scan; consumed/uncertain reservations remain occupied.
            for _ in range(256):
                await asyncio.to_thread(owner.verify)
                released = await ledger.release_fenced_capacity_holds(
                    owner.channel.server_id, owner.channel.executor_id,
                    connection_generation=owner.channel.connection_generation, limit=128)
                if released < 128:
                    break
            else:
                raise CoreError('CAPACITY_EXCEEDED', 'embedded_capacity_recovery')
            after, high = 0, None
            for _ in range(256):
                page = await ledger.owned_slot_page(after_rowid=after, high_water_rowid=high, limit=128)
                for slot in page.reservations:
                    rows = await asyncio.to_thread(EmbeddedReconciliation(owner)._records,
                        session_id=slot.key.session_id)
                    known = rows[0]['open_operation_id'] if len(rows) == 1 else None
                    opening = slot.opening_operation_id
                    if known != opening:
                        # A consumed reservation may predate Core.open, so its
                        # slot still has Core's provisional identity. Attribute
                        # it through Core's durable association; keep it occupied
                        # until the agent's recovery proves release is safe.
                        opening = await ledger.capacity_opening_for_slot(slot)
                    if (slot.key.server_id != owner.channel.server_id or slot.key.executor_id != owner.channel.executor_id
                            or opening is None or known is None or known != opening):
                        raise CoreError('SCOPE_MISMATCH', 'embedded_shared_resources')
                    # Occupied physical ownership wins over a stored retirement
                    # checkpoint, including a restored/stale ledger after a crash.
                    from .embedded_retirement import EmbeddedRetirement
                    await asyncio.to_thread(EmbeddedRetirement(owner).invalidate, slot.key.session_id)
                high = page.high_water_rowid
                if page.next_after_rowid is None:
                    break
                if page.next_after_rowid <= after:
                    raise CoreError('JOURNAL_UNAVAILABLE', 'embedded_shared_resources')
                after = page.next_after_rowid
            else:
                raise CoreError('CAPACITY_EXCEEDED', 'embedded_shared_resources')
        else:
            def check_missing():
                with owner.factory.unit_of_work(write=False) as uow:
                    owner.verify(uow=uow)
                    require_no_missing_store(uow.connection)
            await asyncio.to_thread(check_missing)
            # Create and bind the first ledger before the dispatch pump can
            # admit native work. A later startup must observe this same ID.
            ledger = await owner.host._ledger()
            store_id = await bind_ledger(ledger)
            await verify_anchor_snapshot(ledger, store_id)
        self.blocked = await asyncio.to_thread(catalog.pending_agents)
        for agent_id in self.blocked:
            await asyncio.to_thread(self._state, agent_id, 'RECOVERING')
        self.initialized = True
        # Registry conversion is maintenance, not evidence required for this
        # boot's admission: the existing full directory audit already passed.
        self.registry_import_task = asyncio.create_task(
            self._import_registry(catalog, ledger, store_id), name='embedded-registry-import')

    async def _import_registry(self, catalog, ledger, store_id):
        from ..adapters.outbound.sqlite.execution_embedded_store_binding import (
            registry_import_pending, complete_registry_import,
        )
        owner = self.owner
        attempts = 0
        while not owner._stopping.is_set() and not self._registry_stop.is_set():
            try:
                def pending():
                    with owner.factory.unit_of_work(write=False) as uow:
                        owner.verify(uow=uow)
                        return registry_import_pending(uow.connection, store_id=store_id)
                if not await asyncio.to_thread(pending):
                    await self._stage_audit_anchor(catalog, ledger, store_id)
                    return
                if not await catalog.import_verified_files(ledger, stop=self._registry_stop):
                    return
                def complete():
                    with owner.factory.unit_of_work() as uow:
                        owner.verify(uow=uow)
                        complete_registry_import(uow.connection, store_id=store_id)
                await asyncio.to_thread(complete)
                await self._stage_audit_anchor(catalog, ledger, store_id)
                return
            except OktoNexusError as error:
                if error.code == ErrorCode.CONFLICT:
                    return  # The previous owner cannot mutate a replacement.
                failure = error
            except Exception as error:
                failure = error
            attempts += 1
            logging.getLogger(__name__).warning(
                'Embedded registry import pending: %s', _diagnostic(failure))
            try:
                await asyncio.wait_for(self._registry_stop.wait(),
                    timeout=min(30, 2 ** min(attempts, 5)))
            except asyncio.TimeoutError:
                pass

    async def _stage_audit_anchor(self, catalog, ledger, store_id):
        """Record matching Core/Server tokens only after this boot's full audit.

        This remains a candidate frontier. Admission still scans the directory
        on every startup until anomaly and partial-restore policy qualify.
        """
        from ..adapters.outbound.sqlite.execution_embedded_store_binding import (
            stored_audit_anchor, record_audit_anchor,
        )
        owner = self.owner
        while not owner._stopping.is_set() and not self._registry_stop.is_set():
            await asyncio.to_thread(owner.verify)
            head = await ledger.journal_registry_head()
            if head.complete:
                break
            await ledger.advance_journal_registry_head(limit=128)
            await asyncio.sleep(0.01)
        else:
            return
        while not owner._stopping.is_set() and not self._registry_stop.is_set():
            await asyncio.to_thread(owner.verify)
            if await ledger.advance_journal_extension_index(limit=128):
                break
            await asyncio.sleep(0.01)
        else:
            return
        # Physical audit is repeated after legacy import so the staged token
        # cannot represent a directory that changed during conversion.
        if not await catalog.audit_files():
            raise CoreError('JOURNAL_UNAVAILABLE', 'embedded_audit_anchor')
        head = await ledger.journal_registry_head()
        if not head.complete or head.store_id != store_id:
            raise CoreError('PROFILE_DRIFT', 'embedded_audit_anchor')
        def read_stored():
            with owner.factory.unit_of_work(write=False) as uow:
                owner.verify(uow=uow)
                return stored_audit_anchor(uow.connection, store_id=store_id)
        stored = await asyncio.to_thread(read_stored)
        if stored is not None:
            prefix = await ledger.journal_digest_at_revision(stored.revision)
            if prefix != stored.digest:
                raise CoreError('PROFILE_DRIFT', 'embedded_audit_anchor')
        core_anchor = await ledger.journal_audit_anchor()
        if (stored is not None and stored == core_anchor
                and stored.revision == head.revision and stored.digest == head.digest):
            return
        anchor = await ledger.stage_journal_audit_anchor(
            nonce='audit_' + secrets.token_hex(16), head=head)
        def commit_stored():
            with owner.factory.unit_of_work() as uow:
                owner.verify(uow=uow)
                record_audit_anchor(uow.connection, anchor=anchor,
                    recorded_at=owner.deps.clock.now_iso())
        await asyncio.to_thread(commit_stored)

    async def fail(self, agent_id, error):
        # Loss of the shared owner/database must still stop the whole host.
        await asyncio.to_thread(self.owner.verify)
        self.blocked.add(agent_id)
        # Secondary failures during containment must not hide the first cause.
        first = self.errors.setdefault(agent_id, error)
        self.current_errors[agent_id] = error
        # Record the original sanitized classification before the durable
        # write: a secondary storage failure must not erase its provenance.
        logging.getLogger(__name__).warning('Runtime agent recovery requested: agent=%s current=%s first=%s',
            agent_id, _diagnostic(error), _diagnostic(first))
        try:
            await asyncio.to_thread(self._state, agent_id, 'RECOVERING', error)
            await asyncio.to_thread(self.owner._recovery_event, 'RECOVERY_AGENT_BLOCKED',
                f"Current: {_diagnostic(error)}; first: {_diagnostic(first)}",
                agent_id=agent_id)
        except OktoNexusError as persistence_error:
            if persistence_error.code != ErrorCode.DB_ERROR or not persistence_error.retryable:
                raise
            # The in-memory subject fence is enforced before native dispatch.
            # Keep the same recovery worker/obligation: inability to save its
            # status does not prove loss of the shared owner. READY still needs
            # its durable commit after containment and reconciliation.
            logging.getLogger(__name__).warning(
                'Agent recovery status delayed by writer contention: agent=%s', agent_id)

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
        from .embedded_startup_refusal import EmbeddedStartupRefusal
        from .embedded_unopened_retirement import EmbeddedUnopenedRetirement
        for session_id in await EmbeddedStartupRefusal(owner).recover(agent_id=agent_id):
            if not await EmbeddedUnopenedRetirement(owner).retire(session_id):
                raise CoreError('RECONCILIATION_REQUIRED', 'embedded_startup_retirement')
        from .embedded_preopen_recovery import EmbeddedPreopenRecovery
        await EmbeddedPreopenRecovery(owner).recover(agent_id)
        await owner._recover_publications(agent_id=agent_id)
        await owner.events.recover(agent_id=agent_id)
        if not await EmbeddedReconciliation(owner).recover(agent_id=agent_id):
            raise CoreError('RECONCILIATION_REQUIRED', 'embedded_agent_history')
        for row in await asyncio.to_thread(EmbeddedReconciliation(owner)._records, agent_id, pending_only=True):
            await owner.tools.release_session(row['session_id'])
        # Resource containment, stream continuity and delivery settlement above
        # are mandatory. Re-saving historical release checkpoints is maintenance
        # and must not delay readiness after those proofs have converged.
        await asyncio.to_thread(self._state, agent_id, 'READY')
        self.blocked.discard(agent_id)
        self.errors.pop(agent_id, None)
        self.current_errors.pop(agent_id, None)
        self.publication_pending.discard(agent_id)
        self.attempts.pop(agent_id, None)
        self.retry_at.pop(agent_id, None)
        # The readiness transaction has committed. Retry proven unsent work
        # without waiting for the next periodic scan or a user message.
        if owner.deps.runtime_dispatcher is not None:
            owner.deps.runtime_dispatcher.wake()
        await asyncio.to_thread(owner._recovery_event, 'RECOVERY_AGENT_READY',
            'Agent history reconciled. Previous work was not replayed.', agent_id=agent_id)

    def touch(self):
        """Record work. The host keeps its short tick and wakes at once."""
        self.last_active = time.monotonic()
        # New work ends every idle back-off at once.
        self.next_due_at.clear()
        self.owner._activity.set()

    def busy(self):
        """True while work is pending. An idle host may sleep up to its idle interval."""
        return (time.monotonic() - self.last_active < self.busy_linger
                or bool(self.blocked or self.session_tasks or self.unsettled or self.owner.workers)
                or any(session.get('recovering') for session in self.owner.sessions.values()))

    async def _publish(self, agent_id):
        def progress():
            self.started[agent_id] = time.monotonic()
            self.delayed.discard(agent_id)
        started = time.monotonic()
        published = await self.owner._recover_publications(agent_id=agent_id, progress=progress)
        stats = {}
        await self.owner.events.recover(agent_id=agent_id, live_only=True, progress=progress, stats=stats)
        # Check the stream when the agent becomes live, when a batch holds an
        # error event, and every health_interval seconds as a safety net.
        faults = []
        now = time.monotonic()
        if stats.get('error_seen') or now >= self.health_due_at.get(agent_id, 0):
            self.health_due_at[agent_id] = now + self.health_interval
            self.counters['stream_checks'] += 1
            faults = await asyncio.to_thread(self._check_stream_health, agent_id,
                                             frozenset(self.owner.active_operations))
        for session_id in faults:
            self.owner.sessions.get(session_id, {}).setdefault('recovery_reason', 'EVENT_STREAM_UNAVAILABLE')
            self.recover_session(session_id)
        # Lease renewals are not work: they do not keep the short tick.
        if published or stats.get('active') or faults:
            self.touch()
        elif not any(sid == agent_id for sid in self.owner.worker_agents.values()):
            self.next_due_at[agent_id] = started + self.owner.idle_interval * .9

    def recover_session(self, session_id, *, error=None):
        session = self.owner.sessions.get(session_id)
        if session is None:
            raise CoreError('SESSION_UNKNOWN', 'embedded_session_recovery')
        # Fence only this session. Retain one worker, including during slow
        # containment; healthy siblings continue dispatch and publication.
        session['recovering'] = True
        self.touch()
        if error is not None:
            session.setdefault('recovery_error', error)
        task = self.session_tasks.get(session_id)
        if task is not None and not task.done():
            return
        if time.monotonic() < self.session_retry_at.get(session_id, 0):
            return
        self.session_tasks[session_id] = asyncio.create_task(
            self._recover_session(session_id, session), name='embedded-session-' + session_id)

    async def _recover_session(self, session_id, session):
        owner = self.owner
        try:
            await asyncio.to_thread(owner.verify)
            if session.get('recovery_error') is not None and not session.get('recovery_error_recorded'):
                await asyncio.to_thread(owner._recovery_event, 'RECOVERY_SESSION_BLOCKED',
                    f"Session {session_id}: {_diagnostic(session['recovery_error'])}",
                    agent_id=session['scope']['agent_id'])
                session['recovery_error_recorded'] = True
            if session.get('startup_refusal_frame') is not None:
                # The opening worker is the only possible producer. Join it
                # before the Core admission CAS and retain this session alone
                # until the terminal receipt and retirement both commit.
                workers = [t for t, sid in owner.worker_sessions.items()
                           if sid == session_id and not t.done()]
                if workers:
                    await asyncio.gather(*workers, return_exceptions=True)
                from .embedded_startup_refusal import EmbeddedStartupRefusal
                from .embedded_unopened_retirement import EmbeddedUnopenedRetirement
                refusal = EmbeddedStartupRefusal(owner)
                await asyncio.to_thread(refusal.record, session['startup_refusal_frame'])
                if session_id not in await refusal.recover(session_id=session_id):
                    raise CoreError('RECONCILIATION_REQUIRED', 'embedded_startup_refusal')
                if not await EmbeddedUnopenedRetirement(owner).retire(session_id):
                    raise CoreError('RECONCILIATION_REQUIRED', 'embedded_startup_retirement')
                owner.sessions.pop(session_id, None)
                self.session_retry_at.pop(session_id, None)
                return
            if session.get('initial_refusal'):
                # No authorized executor was returned. Finish the exact durable
                # refusal without containing healthy sibling sessions.
                workers = [t for t, sid in owner.worker_sessions.items() if sid == session_id and not t.done()]
                if workers:
                    await asyncio.gather(*workers, return_exceptions=True)
                request = session.get('initial_refusal_request')
                if request is not None:
                    if not await asyncio.to_thread(owner.access.session_containment.denied,
                            request, channel=owner.channel):
                        raise CoreError('RECONCILIATION_REQUIRED', 'embedded_initial_refusal_identity')
                    session.pop('initial_refusal_request', None)
                from .embedded_initial_refusal import EmbeddedInitialRefusal
                if not await EmbeddedInitialRefusal(owner).recover(session_id=session_id, pending_only=False):
                    raise CoreError('RECONCILIATION_REQUIRED', 'embedded_initial_refusal')
                owner.sessions.pop(session_id, None)
                self.session_retry_at.pop(session_id, None)
                return
            runtime = await session['executor']._runtime()
            report = await runtime.shutdown(ShutdownPolicy(5, 5))
            if ('unknown' in report.session_outcomes.values() or any(
                    facts['process_state'] != 'STOPPED' or facts['release_pending']
                    for facts in runtime.shutdown_resources().values())):
                raise CoreError('RECONCILIATION_REQUIRED', 'embedded_session_containment')
            if not await owner.host.close_native_actions(executor_id=owner.channel.executor_id,
                    session_id=session_id, timeout_seconds=5):
                raise CoreError('RECONCILIATION_REQUIRED', 'embedded_session_native_actions')
            workers = [t for t, sid in owner.worker_sessions.items() if sid == session_id and not t.done()]
            if workers:
                await asyncio.gather(*workers, return_exceptions=True)
            renewal = session.get('renew_task')
            if renewal is not None and not renewal.done():
                await asyncio.shield(renewal)
            agent_id = session['scope']['agent_id']
            await owner._recover_publications(agent_id=agent_id, session_id=session_id)
            await owner.events.recover(agent_id=agent_id, session_id=session_id)
            await EmbeddedReconciliation(owner).release_stopped_session(session_id)
            await owner.tools.release_session(session_id)
            # Before the session leaves the owner: a failed write retries with it.
            await asyncio.to_thread(owner._notify_contained_claimant, session_id, agent_id,
                _containment_reason(session))
            owner.sessions.pop(session_id, None)
            self.session_retry_at.pop(session_id, None)
            await asyncio.to_thread(owner._recovery_event, 'RECOVERY_SESSION_RELEASED',
                'Failed session contained; sibling sessions preserved. Previous work was not replayed.',
                agent_id=agent_id)
        except Exception as error:
            # Retry the same owned resource without escalating a local fault
            # into agent-wide containment. Shared authority loss remains fatal.
            try:
                await asyncio.to_thread(owner.verify)
            except Exception as shared_error:
                owner.failure = shared_error
                await owner.failed()
                return
            self.session_retry_at[session_id] = time.monotonic() + 2
            await asyncio.to_thread(owner._recovery_event, 'RECOVERY_SESSION_PENDING',
                f"Session containment pending: {getattr(error, 'code', type(error).__name__)}"
                f" at {getattr(error, 'stage', 'unknown')}",
                agent_id=session['scope']['agent_id'])

    def _check_stream_health(self, agent_id, active_operations):
        # A Core stream-loss fact fences native work but deliberately retains
        # process ownership. The host must initiate scoped containment itself.
        # Read durable history, rather than only the latest page, so a crash
        # after the event ACK cannot lose this recovery obligation.
        owner = self.owner
        with owner.factory.unit_of_work(write=False) as uow:
            owner.verify(uow=uow)
            faults = uow.connection.execute(STREAM_FAULT_SQL,
                (owner.channel.server_id, owner.channel.executor_id, agent_id)).fetchall()
            pending = []
            for fault in faults:
                closes = uow.connection.execute(
                    "SELECT operation_id FROM execution_operations WHERE server_id=? AND executor_id=? "
                    "AND session_id=? AND action='runtime.close'",
                    (owner.channel.server_id, owner.channel.executor_id, fault['session_id'])).fetchall()
                if any(close['operation_id'] in active_operations for close in closes):
                    # Owned close may force the pipe to end before its confirmed
                    # stop receipt reaches Server. Its retained producer already
                    # owns containment; let it settle without stopping siblings.
                    # Failure/unknown is still handled by that producer, and an
                    # unresolved stream is checked again after the worker exits.
                    self.health_due_at.pop(agent_id, None)
                    continue
                pending.append(fault['session_id'])
            return pending

    async def _retire_closed(self, agent_id):
        from .embedded_retirement import EmbeddedRetirement
        retirement = EmbeddedRetirement(self.owner)
        for row in await asyncio.to_thread(retirement.pending, agent_id):
            await self._retire_session(agent_id, row)

    async def _retire_session(self, agent_id, row):
        owner = self.owner
        from .embedded_retirement import EmbeddedRetirement
        retirement = EmbeddedRetirement(owner)
        if owner.sessions.get(row['session_id'], {}).get('recovering'):
            return  # The retained session worker owns its release proof.
        if any(sid == row['session_id'] and not task.done()
               for task, sid in owner.worker_sessions.items()):
            return  # Native stop alone does not join host publication producers.
        if row['stream_epoch'] is None:
            from .embedded_unopened_retirement import EmbeddedUnopenedRetirement
            await EmbeddedUnopenedRetirement(owner).retire(row['session_id'])
            return
        # Prove resource release and that every Core event was committed
        # before ending polling. Receipt stages themselves are unchanged.
        proof = await EmbeddedReconciliation(owner).release_session(row['session_id'],
            failed_open=row['lifecycle_state'] == 'FAILED')
        # The final native event can settle a turn after the publication
        # pass that observed close. Publish its durable receipt before
        # retiring all obligations for this now fully released stream.
        await owner._recover_publications(agent_id=agent_id)
        revision = await asyncio.to_thread(retirement.snapshot, row['session_id'])
        if revision is None:
            return
        proof['retirement_revision'] = revision
        await owner.tools.release_session(row['session_id'])
        if any(sid == row['session_id'] and not task.done()
               for task, sid in owner.worker_sessions.items()):
            return
        await asyncio.to_thread(retirement.commit, row['session_id'], proof)

    async def _run(self, agent_id, recovering):
        try:
            if recovering:
                await self._recover(agent_id)
            else:
                await self._publish(agent_id)
                self.publication_pending.discard(agent_id)
                self.retry_at.pop(agent_id, None)
        except Exception as error:
            if self.owner._stopping.is_set():
                return
            try:
                if isinstance(error, EmbeddedPublicationDeferred) and not recovering:
                    # A failed Server commit did not invalidate the Core journal
                    # or its native process. Retain the lease and retry the same
                    # unacknowledged events instead of containing healthy work.
                    await self.defer_publication(agent_id)
                    return
                await self.fail(agent_id, error)
                delay = min(30, 2 ** min(self.attempts.get(agent_id, 0), 5))
                self.retry_at[agent_id] = time.monotonic() + delay * random.uniform(.8, 1.2)
            except Exception as shared_error:
                self.owner.failure = shared_error
                await self.owner.failed()

    async def defer_publication(self, agent_id):
        await asyncio.to_thread(self.owner.verify)
        self.retry_at[agent_id] = time.monotonic() + 1
        if agent_id not in self.publication_pending:
            self.publication_pending.add(agent_id)
            await asyncio.to_thread(self.owner._recovery_event, 'RECOVERY_PUBLICATION_DELAYED',
                'Server persistence is delayed; native execution and lease renewal remain active.',
                agent_id=agent_id)

    def _pending_subjects(self):
        with self.owner.factory.unit_of_work(write=False) as uow:
            self.owner.verify(uow=uow)
            return {row[0] for row in uow.connection.execute(
                "SELECT DISTINCT o.subject_agent_id FROM execution_local_publications p "
                "JOIN execution_operations o USING(server_id,executor_id,operation_id) "
                "WHERE p.server_id=? AND p.executor_id=? AND p.terminal=0 "
                "UNION SELECT agent_id FROM execution_local_streams "
                "WHERE server_id=? AND executor_id=? AND drained=0 "
                "UNION SELECT o.subject_agent_id FROM execution_sessions s "
                "JOIN execution_operations o ON o.server_id=s.server_id AND o.executor_id=s.executor_id "
                "AND o.operation_id=s.open_operation_id "
                "WHERE s.server_id=? AND s.executor_id=? AND s.local_retirement_json IS NULL "
                "AND s.lifecycle_state IN ('CLOSED','FAILED')",
                (self.owner.channel.server_id, self.owner.channel.executor_id) * 3)}

    async def tick(self, *, manual=False, agent_id=None):
        async with self._tick_lock:
            await self._tick(manual=manual, agent_id=agent_id)

    async def _tick(self, *, manual=False, agent_id=None):
        if self.owner._stopping.is_set():
            return
        target_agent_id = agent_id
        now = time.monotonic()
        for session_id, task in list(self.session_tasks.items()):
            if task.done():
                task.result()
                del self.session_tasks[session_id]
        for session_id, session in list(self.owner.sessions.items()):
            if session.get('recovering'):
                self.recover_session(session_id)
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
        pending = await asyncio.to_thread(self._pending_subjects)
        live = {s['scope']['agent_id'] for s in self.owner.sessions.values()}
        # An open session keeps its own stream row, so only the other pending
        # subjects show unfinished work. Live subjects report work when they run.
        self.unsettled = bool(pending - live)
        subjects = self.blocked | pending | live
        subjects = subjects if target_agent_id is None else subjects & {target_agent_id}
        self.retirement.tick(subjects)
        for table in (self.next_due_at, self.health_due_at):
            for gone in [a for a in table if a not in subjects]:
                del table[gone]
        for agent_id in subjects:
            recovering = agent_id in self.blocked
            if (agent_id in self.tasks or (recovering and not enabled) or
                    (not manual and now < self.retry_at.get(agent_id, 0)) or
                    (not manual and not recovering and now < self.next_due_at.get(agent_id, 0))):
                continue
            self.started[agent_id] = now
            self.tasks[agent_id] = asyncio.create_task(self._run(agent_id, recovering),
                name='embedded-agent-' + agent_id)
        self.counters['busy_ticks' if self.busy() else 'idle_ticks'] += 1
        self._log_counters(now)

    def _log_counters(self, now):
        """Log the counter changes since the last line. Log at most once per counter_interval."""
        if now < self._counter_log_at:
            return
        self._counter_log_at = now + self.counter_interval
        read_units, write_units = self.owner.factory.unit_counts()
        current = dict(self.counters, read_units=read_units, write_units=write_units)
        delta = {k: v - self._logged.get(k, 0) for k, v in current.items()}
        self._logged = current
        if any(delta.values()):
            logging.getLogger(__name__).info(
                'runtime idle counters %ds: busy_ticks=%d idle_ticks=%d read_units=%d write_units=%d stream_checks=%d',
                self.counter_interval, delta['busy_ticks'], delta['idle_ticks'], delta['read_units'],
                delta['write_units'], delta['stream_checks'])

    async def observe(self, *, timeout=1.0):
        if self.tasks:
            await asyncio.wait(tuple(self.tasks.values()), timeout=timeout)

    async def close(self):
        self._registry_stop.set()
        await self.retirement.close()
        if self.registry_import_task is not None:
            await self.registry_import_task
        if self.tasks:
            await asyncio.gather(*tuple(self.tasks.values()))
        if self.session_tasks:
            await asyncio.gather(*tuple(self.session_tasks.values()))

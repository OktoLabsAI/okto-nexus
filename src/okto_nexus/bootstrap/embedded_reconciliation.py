"""Reconcile retained local resources from Core proofs before readiness."""
import asyncio
import json
from types import SimpleNamespace

from nexus_connector_core import (CoreError, EventCursor, OperationKey,
                                 project_r4_resource_release, project_r4_bound_receipt)

from ..application.execution_reconciliation import ExecutionReconciliation


class EmbeddedReconciliation:
    def __init__(self, owner):
        self.owner = owner

    async def recovery_plan(self, agent_id=None):
        """An exact, reviewable set for operator-confirmed legacy recovery."""
        owner = self.owner
        await asyncio.to_thread(owner.verify)
        if owner._stopping.is_set():
            raise CoreError('RECONCILIATION_REQUIRED', 'embedded_recovery_plan')
        ledger = await owner.host._ledger()
        page = await ledger.owned_slot_page(limit=128)
        if page.next_after_rowid is not None:
            raise CoreError('CAPACITY_EXCEEDED', 'embedded_recovery_plan')
        sessions = []
        for slot in page.reservations:
            rows = await asyncio.to_thread(self._records, session_id=slot.key.session_id)
            row = rows[0] if len(rows) == 1 else None
            if row is not None and (row['agent_id'] not in owner.agents.blocked or (agent_id is not None and row['agent_id'] != agent_id)):
                continue
            if slot.key.session_id in owner.sessions:
                raise CoreError('RECONCILIATION_REQUIRED', 'embedded_recovery_plan')
            if (slot.key.server_id != owner.channel.server_id or slot.key.executor_id != owner.channel.executor_id
                    or row is None or row['open_operation_id'] != slot.opening_operation_id or row['binding_json'] is None):
                raise CoreError('SCOPE_MISMATCH', 'embedded_recovery_plan')
            async def inspect(journal):
                claims = await journal.claimed_sessions(owner.channel.server_id, owner.channel.executor_id, limit=2)
                if len(claims.claims) != 1 or claims.next_after_rowid is not None:
                    raise CoreError('RECONCILIATION_REQUIRED', 'embedded_recovery_plan')
                claim = claims.claims[0]
                if (claim.key != slot.key or claim.opening_operation_id != slot.opening_operation_id
                        or claim.opening_connection_generation is None
                        or claim.opening_connection_generation >= owner.channel.connection_generation):
                    raise CoreError('STALE_GENERATION', 'embedded_recovery_plan')
                key = OperationKey(slot.key.server_id, slot.key.executor_id, slot.opening_operation_id)
                receipt = await journal.get_receipt(key)
                projected = project_r4_bound_receipt(json.loads(row['binding_json']), receipt, key=key, receipt_revision=1)
                if (projected['stage'] not in ('SUBMISSION_STARTED', 'SUBMITTED', 'RUNNING', 'OUTCOME_UNKNOWN', 'SUCCEEDED', 'FAILED')
                        or not projected['possible_effect'] or projected['session_id'] != slot.key.session_id):
                    raise CoreError('RECONCILIATION_REQUIRED', 'embedded_recovery_plan')
                return dict(session_id=slot.key.session_id, opening_operation_id=slot.opening_operation_id,
                            agent_id=projected['agent_id'])
            sessions.append(await owner.host.with_history(executor_id=owner.channel.executor_id,
                session_id=slot.key.session_id, read=inspect))
        return dict(executor_id=owner.channel.executor_id, generation=owner.channel.connection_generation, agent_id=agent_id,
                    sessions=sorted(sessions, key=lambda item: item['session_id']))

    async def confirm_stopped(self, plan, actor):
        """Operator attestation is distinct from automatic OS evidence."""
        if plan != await self.recovery_plan(plan.get('agent_id')) or not plan['sessions']:
            raise CoreError('STALE_GENERATION', 'embedded_recovery_plan')
        owner = self.owner
        await asyncio.to_thread(owner.verify)
        await asyncio.to_thread(owner._recovery_event, 'RECOVERY_OPERATOR_CONFIRMED_STOPPED',
            json.dumps(dict(actor=actor, plan=plan)))
        ledger = await owner.host._ledger()
        for session in plan['sessions']:
            await asyncio.to_thread(owner.verify)
            await ledger.release_owned_slot(OperationKey(owner.channel.server_id, owner.channel.executor_id,
                session['opening_operation_id']), session['session_id'])

    def _never_started(self, row):
        """A durable dispatch refusal before publication proves no Core call."""
        with self.owner.factory.unit_of_work(write=False) as uow:
            self.owner.verify(uow=uow)
            key=(self.owner.channel.server_id,self.owner.channel.executor_id,row['session_id'])
            state=uow.connection.execute('SELECT s.lifecycle_state,s.lease_state,d.dispatch_state,d.last_error '
                'FROM execution_sessions s JOIN execution_dispatch_outbox d ON d.server_id=s.server_id '
                'AND d.executor_id=s.executor_id AND d.operation_id=s.open_operation_id '
                'WHERE s.server_id=? AND s.executor_id=? AND s.session_id=?',key).fetchone()
            if not state:
                return False
            if state['lifecycle_state'] == 'FAILED':
                error = json.loads(state['last_error'] or '{}')
                if (state['lease_state'] not in ('NONE', 'CLOSED') or state['dispatch_state'] != 'RESOLVED_TERMINAL'
                        or error.get('possible_effect') is not False
                        or not (error.get('stage') == 'dispatch' or (
                            error.get('code') == 'LOCAL_PREOPEN_FAILED' and
                            error.get('proof') == 'fenced_owner_no_publication_no_core_claim_receipt_or_slot'))):
                    return False
            elif state['lifecycle_state'] != 'OPEN_PENDING':
                return False
            # _bind commits before Core.open. Under the new fenced owner, an
            # absent binding/journal and empty scoped ledger prove no opening,
            # including a crash before prepare or before dispatch began.
            for table in ('execution_local_publications','execution_receipts'):
                if uow.connection.execute(f'SELECT 1 FROM {table} p JOIN execution_operations o '
                    'USING(server_id,executor_id,operation_id) WHERE o.server_id=? AND o.executor_id=? AND o.session_id=? LIMIT 1',key).fetchone():
                    return False
            return row['binding_json'] is None and row['stream_epoch'] is None

    def _records(self, agent_id=None, *, session_id=None, pending_only=False):
        with self.owner.factory.unit_of_work(write=False) as uow:
            self.owner.verify(uow=uow)
            # A release proves one exact session. Do not scan every historical
            # session (or apply the recovery-plan history cap) for each close.
            # Keep an equality predicate so SQLite can seek the composite key;
            # an optional-parameter OR would turn this back into a prefix scan.
            target = " AND s.session_id=?" if session_id is not None else ""
            if pending_only:
                target += " AND s.local_retirement_json IS NULL"
            params = (self.owner.channel.server_id, self.owner.channel.executor_id, agent_id, agent_id)
            if session_id is not None:
                params += (session_id,)
            params += (2 if session_id is not None else 32769,)
            rows = uow.connection.execute("SELECT s.session_id,s.open_operation_id,s.local_retirement_json,p.binding_json,l.stream_epoch,o.subject_agent_id AS agent_id, "
                "EXISTS(SELECT 1 FROM execution_local_preopen_fences f JOIN execution_preopen_refusals r "
                "USING(server_id,executor_id,operation_id) WHERE f.server_id=s.server_id AND f.executor_id=s.executor_id "
                "AND f.operation_id=s.open_operation_id AND s.lifecycle_state='CLOSED' AND s.lease_state='CLOSED') AS preopen_recovered "
                "FROM execution_sessions s JOIN execution_operations o ON o.server_id=s.server_id AND o.executor_id=s.executor_id AND o.operation_id=s.open_operation_id LEFT JOIN execution_local_publications p ON p.server_id=s.server_id "
                "AND p.executor_id=s.executor_id AND p.operation_id=s.open_operation_id "
                "LEFT JOIN execution_local_streams l ON l.server_id=s.server_id AND l.executor_id=s.executor_id "
                "AND l.session_id=s.session_id AND l.opening_operation_id=s.open_operation_id "
                "WHERE s.server_id=? AND s.executor_id=? AND (? IS NULL OR o.subject_agent_id=?)" + target +
                " ORDER BY s.rowid LIMIT ?", params).fetchall()
            if len(rows)>32768:
                raise CoreError("CAPACITY_EXCEEDED","embedded_recovery")
            return [dict(row) for row in rows]

    def _committed_stream(self, key):
        with self.owner.factory.unit_of_work(write=False) as uow:
            self.owner.verify(uow=uow)
            row=uow.connection.execute("SELECT committed_contiguous,gap_state FROM execution_event_watermarks "
                "WHERE server_id=? AND executor_id=? AND session_id=? AND stream_epoch=?",key).fetchone()
            if row is not None and row["gap_state"]!="none":
                raise CoreError("EVENT_GAP","embedded_resource_stream")
            return row["committed_contiguous"] if row is not None else 0

    async def release_stopped_session(self, session_id):
        """Reconcile one fenced, joined producer, including failed preparation.

        The caller has contained its Core and native action owner. Never infer
        absence of native effects from the exception that triggered recovery.
        """
        owner = self.owner
        session = owner.sessions.get(session_id)
        if (session is None or not session.get('recovering') or
                any(sid == session_id and not task.done() for task, sid in owner.worker_sessions.items()) or
                session.get('renew_task') is not None and not session['renew_task'].done()):
            raise CoreError('RECONCILIATION_REQUIRED', 'embedded_session_producer')
        rows = await asyncio.to_thread(self._records, session_id=session_id)
        if len(rows) != 1:
            raise CoreError('RECONCILIATION_REQUIRED', 'embedded_session_release')
        row = rows[0]
        if row['binding_json'] is None and row['stream_epoch'] is None:
            from nexus_connector_core import SessionKey
            ledger = await owner.host._ledger()
            slot = await ledger.owned_slot_state(SessionKey(
                owner.channel.server_id, owner.channel.executor_id, session_id))
            if slot is not None and not slot.released:
                raise CoreError('RECONCILIATION_REQUIRED', 'embedded_owned_resources')
            await self._recover_unstarted(row)
            if owner.deps.runtime_dispatcher is not None:
                owner.deps.runtime_dispatcher.wake()
            return
        if row['binding_json'] is None or row['stream_epoch'] is None:
            raise CoreError('RECONCILIATION_REQUIRED', 'embedded_resource_binding')
        receipt = await owner.host.historical_receipt(session_id=session_id,
            key=OperationKey(owner.channel.server_id, owner.channel.executor_id, row['open_operation_id']))
        failed_open = False
        if receipt is not None and receipt.stage == 'FAILED':
            async def never_claimed(journal):
                from nexus_connector_core import SessionKey
                launch = await journal.get_process_launch(SessionKey(
                    owner.channel.server_id, owner.channel.executor_id, session_id))
                return launch is not None and launch.stop_proof == 'NEVER_CLAIMED'
            failed_open = (not receipt.possible_effect and receipt.retry_safe) or await owner.host.with_history(
                executor_id=owner.channel.executor_id, session_id=session_id, read=never_claimed)
        await self.release_session(session_id, failed_open=failed_open)

    async def release_session(self, session_id, *, failed_open=False):
        """Project one contained session without quiescing unrelated runtimes."""
        owner, host = self.owner, self.owner.host
        rows = await asyncio.to_thread(self._records, session_id=session_id)
        if len(rows) != 1:
            raise CoreError('RECONCILIATION_REQUIRED', 'embedded_session_release')
        row = rows[0]
        ledger = await host._ledger()
        async def inspect(journal):
            page = await journal.claimed_sessions(owner.channel.server_id, owner.channel.executor_id, limit=2)
            if len(page.claims) != 1 or page.next_after_rowid is not None:
                raise CoreError('RECONCILIATION_REQUIRED', 'embedded_session_release')
            claim = page.claims[0]
            if claim.key.session_id != session_id or claim.opening_operation_id != row['open_operation_id']:
                raise CoreError('SCOPE_MISMATCH', 'embedded_session_release')
            slot = await ledger.owned_slot_state(claim.key)
            receipt = await journal.get_receipt(OperationKey(claim.key.server_id, claim.key.executor_id, claim.opening_operation_id))
            binding = json.loads(row['binding_json'])
            if failed_open:
                projected = project_r4_bound_receipt(binding, receipt,
                    key=OperationKey(claim.key.server_id, claim.key.executor_id, claim.opening_operation_id),
                    receipt_revision=1)
                journal_slot = await journal.owned_slot_state(claim.key)
                launch = await journal.get_process_launch(claim.key)
                never_claimed = (launch is not None and launch.identity.key == claim.key
                    and launch.identity.opening_operation_id == claim.opening_operation_id
                    and launch.identity.owner_generation == claim.opening_owner_generation
                    and launch.identity.connection_generation == claim.opening_connection_generation
                    and launch.producer_fenced and not launch.spawn_claimed
                    and launch.stop_proof == 'NEVER_CLAIMED')
                if (projected['session_id'] != session_id or projected['stage'] != 'FAILED'
                        or not (never_claimed or not projected['possible_effect'] and projected['retry_safe'])
                        or any(resource is not None and (resource.key != claim.key or not resource.released
                            or resource.opening_operation_id != claim.opening_operation_id)
                            for resource in (slot, journal_slot))
                        or await journal.get_process_birth(claim.key) is not None):
                    raise CoreError('RECONCILIATION_REQUIRED', 'embedded_failed_open_release')
                # A durable pre-effect refusal can precede reservation entirely.
                # A fenced never-claimed producer is stronger independent proof;
                # preserve any monotonic possible-effect marker in its receipt.
                # Any reservation that does exist must still prove release.
                # No process existed: do not manufacture the EXITED proof used
                # for successful openings, or a successful close receipt.
                fact = {'owner_generation': claim.opening_owner_generation}
            else:
                fact = project_r4_resource_release(binding, claim, slot, receipt)
            cursor = EventCursor(claim.key.server_id, claim.key.executor_id, session_id, row['stream_epoch'])
            sequence = await journal.contiguous_watermark(cursor)
            if sequence != await asyncio.to_thread(self._committed_stream,
                    (claim.key.server_id, claim.key.executor_id, session_id, row['stream_epoch'])):
                raise CoreError('EVENT_GAP', 'embedded_session_release')
            return fact | dict(stream_epoch=row['stream_epoch'], committed_sequence=sequence)
        fact = await host.with_history(executor_id=owner.channel.executor_id, session_id=session_id, read=inspect)
        def commit():
            with owner.factory.unit_of_work() as uow:
                owner.verify(uow=uow)
                changed = uow.connection.execute(
                    "UPDATE execution_sessions SET lifecycle_state=?,lease_state='CLOSED' "
                    "WHERE server_id=? AND executor_id=? AND session_id=? AND owner_generation=? AND open_operation_id=?",
                    ('FAILED' if failed_open else 'CLOSED', owner.channel.server_id, owner.channel.executor_id, session_id,
                     fact['owner_generation'], row['open_operation_id']))
                if changed.rowcount != 1:
                    raise CoreError('STALE_GENERATION', 'embedded_session_release')
                if not failed_open:
                    from ..application.execution_domain_delivery import project_released_deliveries
                    project_released_deliveries(uow.connection, server_id=owner.channel.server_id,
                        executor_id=owner.channel.executor_id, session_id=session_id, proof=fact)
                if failed_open:
                    key = (owner.channel.server_id, owner.channel.executor_id, session_id)
                    uow.connection.execute("UPDATE execution_leases SET status='REVOKED' "
                        "WHERE server_id=? AND executor_id=? AND session_id=?", key)
                    uow.connection.execute("UPDATE execution_session_capabilities SET revoked_at=? "
                        "WHERE server_id=? AND executor_id=? AND session_id=? AND revoked_at IS NULL",
                        (owner.deps.clock.now_iso(), *key))
                from ..application.execution_initial_turns import settle_failed_initial_turns
                settle_failed_initial_turns(uow.connection, server_id=owner.channel.server_id,
                    executor_id=owner.channel.executor_id)
        await asyncio.to_thread(commit)
        # Releasing the opening can make its never-sent first turn retryable.
        # Notify after commit; the earlier receipt wake cannot see that state.
        owner.deps.runtime_dispatcher.wake()
        return dict(fact, server_id=owner.channel.server_id, executor_id=owner.channel.executor_id,
                    session_id=session_id, opening_operation_id=row['open_operation_id'],
                    release_kind='failed_open' if failed_open else 'resource_released')

    async def _empty_slots(self, source, session_ids=None):
        after, high = 0, None
        for _ in range(256):
            page = await source.owned_slot_page(after_rowid=after,high_water_rowid=high,limit=128)
            if any(session_ids is None or slot.key.session_id in session_ids for slot in page.reservations):
                raise CoreError("RECONCILIATION_REQUIRED","embedded_owned_resources")
            high = page.high_water_rowid
            if page.next_after_rowid is None:
                return
            if page.next_after_rowid<=after:
                raise CoreError("JOURNAL_UNAVAILABLE","embedded_resource_cursor")
            after = page.next_after_rowid
        raise CoreError("CAPACITY_EXCEEDED","embedded_resource_scan")

    async def _recover_containers(self, ledger, records):
        """Release fenced native trees only after observing their exact container stop."""
        from nexus_connector_core.native.process.recovery import recover_owned_container
        from nexus_connector_core.native.process.launch_recovery import recover_process_launch
        owner = self.owner
        for row in records:
            if row['binding_json'] is None:
                continue
            async def inspect(journal):
                page = await journal.claimed_sessions(owner.channel.server_id, owner.channel.executor_id, limit=2)
                if len(page.claims) != 1 or page.next_after_rowid is not None:
                    return
                claim = page.claims[0]
                slot = await ledger.owned_slot_state(claim.key)
                if slot is not None and slot.released:
                    return
                if (claim.key.session_id != row['session_id']
                        or claim.opening_operation_id != row['open_operation_id']
                        or slot is not None and slot.opening_operation_id != claim.opening_operation_id
                        or claim.opening_connection_generation is None
                        or claim.opening_connection_generation >= owner.channel.connection_generation):
                    raise CoreError('RECONCILIATION_REQUIRED', 'embedded_container_scope')
                key = OperationKey(claim.key.server_id, claim.key.executor_id, claim.opening_operation_id)
                receipt = await journal.get_receipt(key)
                projected = project_r4_bound_receipt(json.loads(row['binding_json']), receipt,
                    key=key, receipt_revision=1)
                if projected['session_id'] != claim.key.session_id:
                    raise CoreError('RECONCILIATION_REQUIRED', 'embedded_container_receipt')
                recovered = await recover_process_launch(journal, claim.key,
                    connection_generation=owner.channel.connection_generation, validate_authority=owner.verify)
                if recovered.state != 'NO_LAUNCH_INTENT':
                    if recovered.state != 'STOPPED':
                        return  # Busy producer/unknown container retains every slot.
                    launch = recovered.record
                    if launch.stop_proof == 'NEVER_CLAIMED':
                        receipt = await journal.get_receipt(key)
                        if receipt.stage != 'FAILED':
                            raise CoreError('RECONCILIATION_REQUIRED', 'embedded_launch_settlement')
                        # _publish uses the separate Server DB and a per-operation
                        # lock; it does not reenter the history journal. Persist
                        # the terminal fact before donating physical capacity.
                        await owner._publish(json.loads(row['binding_json']), receipt)
                    elif (slot is None or projected['stage'] not in ('SUBMISSION_STARTED', 'SUBMITTED', 'RUNNING',
                            'OUTCOME_UNKNOWN', 'SUCCEEDED', 'FAILED') or not projected['possible_effect']):
                        raise CoreError('RECONCILIATION_REQUIRED', 'embedded_container_receipt')
                    await asyncio.to_thread(owner.verify)
                    await asyncio.to_thread(owner._recovery_event, 'RECOVERY_CONTAINER_STOPPED',
                        json.dumps(dict(session_id=claim.key.session_id,
                            opening_operation_id=claim.opening_operation_id,
                            container_id=launch.identity.container_id, stop_proof=launch.stop_proof)))
                    journal_slot = await journal.owned_slot_state(claim.key)
                    if journal_slot is not None and not journal_slot.released:
                        await journal.release_owned_slot(key, claim.key.session_id)
                    await asyncio.to_thread(owner.verify)
                    if slot is not None:
                        await ledger.release_owned_slot(key, claim.key.session_id)
                    return
                if slot is None:
                    return  # Missing resources alone never prove a historical launch stopped.
                if (projected['session_id'] != claim.key.session_id
                        or projected['stage'] not in ('SUBMISSION_STARTED', 'SUBMITTED', 'RUNNING', 'OUTCOME_UNKNOWN', 'SUCCEEDED', 'FAILED')
                        or not projected['possible_effect']):
                    raise CoreError('RECONCILIATION_REQUIRED', 'embedded_container_receipt')
                birth = await journal.get_process_birth(claim.key)
                if birth is None or birth.key != claim.key or birth.opening_operation_id != claim.opening_operation_id:
                    return
                await asyncio.to_thread(owner.verify)
                if await asyncio.to_thread(recover_owned_container, birth.evidence, stop=True) != 'STOPPED':
                    return
                await asyncio.to_thread(owner.verify)
                # Persist evidence before release; retries are idempotent. No receipt
                # for a close or a completed turn is manufactured here.
                await asyncio.to_thread(owner._recovery_event, 'RECOVERY_CONTAINER_STOPPED',
                    json.dumps(dict(session_id=claim.key.session_id,
                        opening_operation_id=claim.opening_operation_id,
                        container_id=birth.evidence.container_id)))
                await ledger.release_owned_slot(key, claim.key.session_id)
            await owner.host.with_history(executor_id=owner.channel.executor_id,
                session_id=row['session_id'], read=inspect)

    async def recover(self, agent_id=None):
        owner,host = self.owner,self.owner.host
        records = await asyncio.to_thread(self._records, agent_id, pending_only=True)
        absent = set()
        for row in records:
            if not host._journal_path(owner.channel.executor_id,row['session_id']).exists() and await asyncio.to_thread(self._never_started,row):
                absent.add(row['session_id'])
        expected = {host._journal_path(owner.channel.executor_id,r["session_id"]).name for r in records if r['session_id'] not in absent}
        # An installation containing only pre-dispatch refusals never opened
        # Core, including its global ledger. Never waive a ledger for a session
        # that might have reached the native boundary.
        ledger_present = await asyncio.to_thread((host.store_dir / 'owned-slots.db').is_file)
        if len(absent) != len(records) or ledger_present:
            expected.add("owned-slots.db")
        if agent_id is None:
            from .embedded_session_catalog import EmbeddedSessionCatalog
            catalog = EmbeddedSessionCatalog(owner)
            await catalog.backfill()
            await catalog.audit_files()
        # Shared directory attribution belongs to initialize. A subject worker
        # checks only its pending paths, never enumerating other agents' history.
        if not await asyncio.to_thread(lambda: all((host.store_dir / name).is_file() for name in expected)):
            raise CoreError("JOURNAL_UNAVAILABLE","embedded_resource_files")
        # These openings have an authenticated no-admission fence, not a
        # native claim to release. EmbeddedPreopenRecovery revalidates their
        # Core fact and physical slots before reaching this pass.
        records = [row for row in records if not row['preopen_recovered']]
        ledger = await host._ledger() if 'owned-slots.db' in expected else None
        if ledger is not None:
            # Consumption can precede both the initial lease and Core.open.
            # The new owner fences the old worker; Core alone confirms whether
            # its original placeholder can be released without stopping work.
            from ..application.execution_preopen_capacity import ExecutionPreopenCapacity
            from ..adapters.outbound.sqlite.execution_preopen_capacity import SqlitePreopenCapacityRepository
            preopen = ExecutionPreopenCapacity(factory=owner.factory,
                repository=SqlitePreopenCapacityRepository(), capacity_provider=owner.execution_capacity,
                channel=owner.channel)
            for row in records:
                if row['binding_json'] is None and row['stream_epoch'] is None:
                    await asyncio.to_thread(owner.verify)
                    await preopen.release(session_id=row['session_id'], opening_operation_id=row['open_operation_id'])
            await self._recover_containers(ledger, [r for r in records if r['session_id'] not in absent])
            await self._empty_slots(ledger, {r['session_id'] for r in records} if agent_id is not None else None)
        proofs = {}
        unstarted_sessions = set()
        for row in records:
            await asyncio.to_thread(owner.verify)
            if row['session_id'] in absent:
                if await self._recover_unstarted(row, proven_absent=True):
                    unstarted_sessions.add(row['session_id'])
                continue
            if row["binding_json"] is None or row["stream_epoch"] is None:
                from .embedded_initial_refusal import EmbeddedInitialRefusal
                if await EmbeddedInitialRefusal(owner).recover(session_id=row['session_id'], pending_only=False):
                    continue
                if row['binding_json'] is None and row['stream_epoch'] is None:
                    await self._recover_unstarted(row)
                    continue
                raise CoreError("RECONCILIATION_REQUIRED","embedded_resource_binding")
            opening_receipt = await host.historical_receipt(session_id=row['session_id'],
                key=OperationKey(owner.channel.server_id, owner.channel.executor_id, row['open_operation_id']))
            never_claimed = False
            if opening_receipt is not None and opening_receipt.stage == 'FAILED':
                async def never_started(journal):
                    from nexus_connector_core import SessionKey
                    launch = await journal.get_process_launch(SessionKey(
                        owner.channel.server_id, owner.channel.executor_id, row['session_id']))
                    return launch is not None and launch.stop_proof == 'NEVER_CLAIMED'
                never_claimed = await host.with_history(executor_id=owner.channel.executor_id,
                    session_id=row['session_id'], read=never_started)
            if (opening_receipt is not None and opening_receipt.stage == 'FAILED' and
                    (never_claimed or not opening_receipt.possible_effect and opening_receipt.retry_safe)):
                # The durable no-effect fact and released reservation are the
                # proof, independent of the refusal code (including an opening
                # whose authority expired before native spawn).
                await self.release_session(row['session_id'], failed_open=True)
                continue
            async def inspect(journal):
                await self._empty_slots(journal)
                page = await journal.claimed_sessions(owner.channel.server_id,owner.channel.executor_id,limit=2)
                if len(page.claims)!=1 or page.next_after_rowid is not None:
                    raise CoreError("RECONCILIATION_REQUIRED","embedded_resource_claim")
                claim = page.claims[0]
                if claim.key.session_id!=row["session_id"] or claim.opening_operation_id!=row["open_operation_id"]:
                    raise CoreError("SCOPE_MISMATCH","embedded_resource_claim")
                slot = await ledger.owned_slot_state(claim.key)
                receipt = await journal.get_receipt(OperationKey(claim.key.server_id,claim.key.executor_id,claim.opening_operation_id))
                fact = project_r4_resource_release(json.loads(row["binding_json"]),claim,slot,receipt)
                cursor = EventCursor(claim.key.server_id,claim.key.executor_id,claim.key.session_id,row["stream_epoch"])
                sequence = await journal.contiguous_watermark(cursor)
                # The publisher already persisted/applied every contiguous event.
                if sequence != await asyncio.to_thread(self._committed_stream,(
                        claim.key.server_id,claim.key.executor_id,claim.key.session_id,row["stream_epoch"])):
                    raise CoreError("EVENT_GAP","embedded_resource_stream")
                return fact,dict(session_id=claim.key.session_id,stream_epoch=row["stream_epoch"],sequence=sequence)
            proofs[row["session_id"]] = await host.with_history(executor_id=owner.channel.executor_id,
                session_id=row["session_id"],read=inspect)
        # Older versions could retire the stream without settling its delivery.
        # Revalidate the retained proof even for sessions already marked closed.
        def settle_retained():
            from ..application.execution_domain_delivery import project_released_deliveries
            with owner.factory.unit_of_work() as uow:
                owner.verify(uow=uow)
                for session_id, (fact, stream) in proofs.items():
                    if uow.connection.execute("SELECT 1 FROM execution_sessions WHERE server_id=? AND executor_id=? "
                            "AND session_id=? AND lifecycle_state='CLOSED' AND lease_state='CLOSED'",
                            (owner.channel.server_id, owner.channel.executor_id, session_id)).fetchone():
                        project_released_deliveries(uow.connection, server_id=owner.channel.server_id,
                            executor_id=owner.channel.executor_id, session_id=session_id,
                            proof=dict(ownership=fact, stream=stream))
        await asyncio.to_thread(settle_retained)
        reconciliation = ExecutionReconciliation(owner.factory,owner.channel,
            owner_guard=lambda conn:owner.verify(uow=SimpleNamespace(connection=conn)), agent_id=agent_id,
            unstarted_sessions=unstarted_sessions)
        for _ in range(128):
            request = await asyncio.to_thread(reconciliation.request)
            def receipts():
                with owner.factory.unit_of_work(write=False) as uow:
                    owner.verify(uow=uow)
                    result=[]
                    for operation_id in request["operation_ids"]:
                        row=uow.connection.execute("SELECT canonical_frame FROM execution_receipts "
                            "WHERE server_id=? AND executor_id=? AND operation_id=? ORDER BY receipt_revision DESC LIMIT 1",
                            (owner.channel.server_id,owner.channel.executor_id,operation_id)).fetchone()
                        if row:
                            frame=json.loads(row[0])
                            result.append({k:frame[k] for k in ("operation_id","intent_hash","receipt_revision","stage")})
                    return result
            complete = len(request["operation_ids"])<256 and len(request["session_ids"])<256
            facts,claims,streams=[],[],[]
            for session_id in request["session_ids"]:
                fact,stream=proofs[session_id]
                facts.append(fact)
                streams.append(stream)
                claims.append(dict(session_id=session_id,owner_generation=fact["owner_generation"],state="RELEASED"))
            report=request | dict(type="reconcile.report",next_cursor=None if complete else "page_"+str(reconciliation.pages+1),
                complete=complete,receipts=await asyncio.to_thread(receipts),claims=claims,ownership_facts=facts,stream_watermarks=streams)
            result=await asyncio.to_thread(reconciliation.accept,report)
            if complete:
                return not result["recovery_remaining"]
        raise CoreError("CAPACITY_EXCEEDED","embedded_reconciliation")

    async def _recover_unstarted(self, row, *, proven_absent=False):
        """Prove an opening stopped before the durable native-call boundary.

        _execute commits a local publication binding before Core.open. A fenced
        owner, absent binding AND empty Core claims/receipts/slots prove no
        native opening; absence of a receipt alone is never sufficient.
        """
        owner = self.owner
        async def inspect(journal):
            await self._empty_slots(journal)
            claims = await journal.claimed_sessions(owner.channel.server_id, owner.channel.executor_id, limit=1)
            receipt = await journal.get_receipt(OperationKey(owner.channel.server_id,
                owner.channel.executor_id, row['open_operation_id']))
            if claims.claims or claims.next_after_rowid is not None or receipt is not None:
                raise CoreError('RECONCILIATION_REQUIRED', 'embedded_preopen_history')
        if proven_absent:
            if not await asyncio.to_thread(self._never_started,row):
                raise CoreError('RECONCILIATION_REQUIRED','embedded_preopen_history')
        else:
            await owner.host.with_history(executor_id=owner.channel.executor_id, session_id=row['session_id'], read=inspect)
        def commit():
            with owner.factory.unit_of_work() as uow:
                owner.verify(uow=uow)
                conn = uow.connection
                key = (owner.channel.server_id, owner.channel.executor_id, row['session_id'])
                state = conn.execute('SELECT lifecycle_state,open_operation_id FROM execution_sessions '
                    'WHERE server_id=? AND executor_id=? AND session_id=?', key).fetchone()
                if state is None or state['open_operation_id'] != row['open_operation_id'] or state['lifecycle_state'] not in ('OPEN_PENDING', 'FAILED'):
                    raise CoreError('RECONCILIATION_REQUIRED', 'embedded_preopen_state')
                if conn.execute('SELECT 1 FROM execution_local_publications p JOIN execution_operations o '
                    'USING(server_id,executor_id,operation_id) WHERE o.server_id=? AND o.executor_id=? AND o.session_id=?', key).fetchone():
                    raise CoreError('RECONCILIATION_REQUIRED', 'embedded_preopen_binding')
                if conn.execute('SELECT 1 FROM execution_receipts r JOIN execution_operations o '
                    'USING(server_id,executor_id,operation_id) WHERE o.server_id=? AND o.executor_id=? AND o.session_id=?', key).fetchone():
                    raise CoreError('RECONCILIATION_REQUIRED', 'embedded_preopen_receipt')
                from ..application.execution_reconciliation import pending_unstarted_session
                if proven_absent and pending_unstarted_session(conn, *key):
                    # No reservation, lease, local binding, Core journal or
                    # owned slot ever existed. Preserve the original durable
                    # admission for its first dispatch under current authority.
                    return True
                operations = conn.execute("SELECT operation_id FROM execution_operations WHERE server_id=? AND executor_id=? "
                    "AND session_id=? AND admission_state<>'RESOLVED_TERMINAL'", key).fetchall()
                for operation in operations:
                    opkey = (*key[:2], operation['operation_id'])
                    error = json.dumps(dict(code='LOCAL_PREOPEN_FAILED', stage='prepare',
                        message='Local preparation stopped before the native runtime was opened.',
                        possible_effect=False, retry_safe=False, operation_id=operation['operation_id'],
                        proof='fenced_owner_no_publication_no_core_claim_receipt_or_slot'))
                    conn.execute("INSERT INTO execution_dispatch_outbox(server_id,executor_id,operation_id,dispatch_state,last_error) "
                        "VALUES(?,?,?,'RESOLVED_TERMINAL',?) ON CONFLICT(server_id,executor_id,operation_id) DO UPDATE SET "
                        "dispatch_state='RESOLVED_TERMINAL',last_error=excluded.last_error,reservation_class=NULL,reserved_bytes=0,reserved_at=NULL",
                        (*opkey, error))
                    conn.execute("UPDATE execution_operations SET admission_state='RESOLVED_TERMINAL' "
                        "WHERE server_id=? AND executor_id=? AND operation_id=?", opkey)
                conn.execute("UPDATE execution_sessions SET lifecycle_state='FAILED',lease_state='CLOSED' "
                    "WHERE server_id=? AND executor_id=? AND session_id=?", key)
                conn.execute("UPDATE execution_leases SET status='REVOKED' WHERE server_id=? AND executor_id=? AND session_id=?", key)
                conn.execute("UPDATE execution_session_capabilities SET revoked_at=? WHERE server_id=? AND executor_id=? "
                    "AND session_id=? AND revoked_at IS NULL", (owner.deps.clock.now_iso(), *key))
        return await asyncio.to_thread(commit)

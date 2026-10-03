"""Reconcile retained local resources from Core proofs before readiness."""
import asyncio
import json
from types import SimpleNamespace

from nexus_connector_core import CoreError, EventCursor, OperationKey, project_r4_resource_release

from ..application.execution_reconciliation import ExecutionReconciliation


class EmbeddedReconciliation:
    def __init__(self, owner):
        self.owner = owner

    def _records(self):
        with self.owner.factory.unit_of_work(write=False) as uow:
            self.owner.verify(uow=uow)
            rows = uow.connection.execute("SELECT s.session_id,s.open_operation_id,p.binding_json,l.stream_epoch "
                "FROM execution_sessions s LEFT JOIN execution_local_publications p ON p.server_id=s.server_id "
                "AND p.executor_id=s.executor_id AND p.operation_id=s.open_operation_id "
                "LEFT JOIN execution_local_streams l ON l.server_id=s.server_id AND l.executor_id=s.executor_id "
                "AND l.session_id=s.session_id AND l.opening_operation_id=s.open_operation_id "
                "WHERE s.server_id=? AND s.executor_id=? ORDER BY s.rowid LIMIT 32769",
                (self.owner.channel.server_id,self.owner.channel.executor_id)).fetchall()
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

    async def release_session(self, session_id):
        """Project one contained session without quiescing unrelated runtimes."""
        owner, host = self.owner, self.owner.host
        rows = [row for row in await asyncio.to_thread(self._records) if row['session_id'] == session_id]
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
            fact = project_r4_resource_release(json.loads(row['binding_json']), claim, slot, receipt)
            cursor = EventCursor(claim.key.server_id, claim.key.executor_id, session_id, row['stream_epoch'])
            sequence = await journal.contiguous_watermark(cursor)
            if sequence != await asyncio.to_thread(self._committed_stream,
                    (claim.key.server_id, claim.key.executor_id, session_id, row['stream_epoch'])):
                raise CoreError('EVENT_GAP', 'embedded_session_release')
            return fact
        fact = await host.with_history(executor_id=owner.channel.executor_id, session_id=session_id, read=inspect)
        def commit():
            with owner.factory.unit_of_work() as uow:
                owner.verify(uow=uow)
                changed = uow.connection.execute(
                    "UPDATE execution_sessions SET lifecycle_state='CLOSED',lease_state='CLOSED' "
                    "WHERE server_id=? AND executor_id=? AND session_id=? AND owner_generation=? AND open_operation_id=?",
                    (owner.channel.server_id, owner.channel.executor_id, session_id,
                     fact['owner_generation'], row['open_operation_id']))
                if changed.rowcount != 1:
                    raise CoreError('STALE_GENERATION', 'embedded_session_release')
        await asyncio.to_thread(commit)

    async def _empty_slots(self, source):
        after, high = 0, None
        for _ in range(256):
            page = await source.owned_slot_page(after_rowid=after,high_water_rowid=high,limit=128)
            if page.reservations:
                raise CoreError("RECONCILIATION_REQUIRED","embedded_owned_resources")
            high = page.high_water_rowid
            if page.next_after_rowid is None:
                return
            if page.next_after_rowid<=after:
                raise CoreError("JOURNAL_UNAVAILABLE","embedded_resource_cursor")
            after = page.next_after_rowid
        raise CoreError("CAPACITY_EXCEEDED","embedded_resource_scan")

    async def recover(self):
        owner,host = self.owner,self.owner.host
        records = await asyncio.to_thread(self._records)
        if not records:
            return False
        expected = {host._journal_path(owner.channel.executor_id,r["session_id"]).name for r in records}
        expected.add("owned-slots.db")
        allowed = expected | {name+suffix for name in expected for suffix in ("-wal","-shm")}
        files = await asyncio.to_thread(lambda: {p.name for p in host.store_dir.iterdir()})
        if not files.issubset(allowed) or not expected.issubset(files):
            raise CoreError("JOURNAL_UNAVAILABLE","embedded_resource_files")
        ledger = await host._ledger()
        await self._empty_slots(ledger)
        proofs = {}
        for row in records:
            await asyncio.to_thread(owner.verify)
            if row["binding_json"] is None or row["stream_epoch"] is None:
                if row['binding_json'] is None and row['stream_epoch'] is None:
                    await self._recover_unstarted(row)
                    continue
                raise CoreError("RECONCILIATION_REQUIRED","embedded_resource_binding")
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
        reconciliation = ExecutionReconciliation(owner.factory,owner.channel,
            owner_guard=lambda conn:owner.verify(uow=SimpleNamespace(connection=conn)))
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

    async def _recover_unstarted(self, row):
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
        await asyncio.to_thread(commit)

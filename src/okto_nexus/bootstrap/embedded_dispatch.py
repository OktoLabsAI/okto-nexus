"""Serve-owned local outbox execution through the shared Core contract."""
import asyncio
from contextlib import asynccontextmanager
import json
import secrets
import time

from nexus_connector_core import (
    CoreError, LaunchIntent, OpenOperation, TurnOperation, ControlOperation,
    OperationKey, prepare_r4_receipt_binding, project_r4_bound_receipt,
    r4_close_operation, ShutdownPolicy,
)
from nexus_connector_core.protocol import canonical_json

from ..adapters.outbound.execution.core_inventory import protocol_info
from ..adapters.outbound.execution.embedded import EmbeddedExecutor
from ..adapters.outbound.sqlite.execution_receipts import append_execution_receipt
from ..application.execution_dispatch_pump import ExecutionDispatchPump
from ..application.execution_leases import ExecutionChannel, ExecutionLeaseService
from ..application.execution_local_launch import ApprovedLocalLaunch
from ..errors import ErrorCode, OktoNexusError
from .execution_authority import build_execution_access

_SCOPE = ("server_id", "executor_id", "binding_id", "agent_id", "workspace_id",
          "workspace_binding_id", "session_id", "session_owner_generation",
          "authorization_revision", "configuration_revision", "binding_revision", "credential_epoch")


class EmbeddedDispatchOwner:
    def __init__(self, inventory, host):
        self.inventory, self.host = inventory, host
        self.deps = inventory.deps
        self.factory = self.deps.connection_factory
        self.channel = ExecutionChannel(inventory.key.server_id, inventory.key.executor_id,
                                        inventory.dispatcher.owner_id, inventory.generation)
        self.access = build_execution_access(self.deps)
        self.leases = ExecutionLeaseService(factory=self.factory, access=self.access,
                                            fresh_publications=inventory.fresh)
        self.sessions = {}
        self.workers = set()
        self.renewals = set()
        self.pump = None
        self.maintenance = None
        self.native_factory = None
        self.failure = None
        self._stopping = asyncio.Event()
        self._close_task = None
        self._after = 0
        self._publish_lock = asyncio.Lock()
        self._containment_task = None
        self.containment_report = None
        self.state_failure = None

    def _quiesce(self):
        c = self.channel
        with self.factory.unit_of_work() as uow:
            uow.connection.execute("UPDATE execution_executors SET control_state='RECOVERING' "
                "WHERE server_id=? AND executor_id=? AND owner_instance_id=? AND generation=? "
                "AND kind='embedded' AND control_state='CONTROL_READY'",
                (c.server_id,c.executor_id,c.connection_id,c.connection_generation))

    def verify(self, *, uow=None):
        if uow is None:
            with self.factory.unit_of_work(write=False) as unit:
                return self.verify(uow=unit)
        owner, channel = self.inventory, self.channel
        if (not owner.dispatcher.repo.owns(uow, owner_id=channel.connection_id,
                epoch=owner.dispatcher.epoch, now=self.deps.clock.now_iso())
                or uow.connection.execute("SELECT 1 FROM execution_executors WHERE server_id=? AND executor_id=? "
                    "AND kind='embedded' AND owner_instance_id=? AND generation=? AND revoked_at IS NULL "
                    "AND control_state IN ('RECOVERING','CONTROL_READY')",
                    (channel.server_id,channel.executor_id,channel.connection_id,channel.connection_generation)).fetchone() is None):
            raise OktoNexusError(ErrorCode.CONFLICT, "The embedded dispatch owner changed.", {})

    def _activate(self):
        # Retained journals require reconciliation, never a fresh empty-session
        # assumption. A later recovery pass must prove their durable state.
        if self.host.store_dir.exists() and any(self.host.store_dir.iterdir()):
            return False
        with self.factory.unit_of_work() as uow:
            self.verify(uow=uow)
            c = self.channel
            if (uow.connection.execute("SELECT 1 FROM execution_sessions WHERE server_id=? AND executor_id=? "
                    "AND lifecycle_state NOT IN ('CLOSED','FAILED') LIMIT 1", (c.server_id,c.executor_id)).fetchone()
                    or uow.connection.execute("SELECT 1 FROM execution_operations WHERE server_id=? AND executor_id=? "
                    "AND admission_state<>'RESOLVED_TERMINAL' LIMIT 1", (c.server_id,c.executor_id)).fetchone()):
                return False
            return uow.connection.execute("UPDATE execution_executors SET control_state='CONTROL_READY' "
                "WHERE server_id=? AND executor_id=? AND owner_instance_id=? AND generation=? AND control_state='RECOVERING'",
                (c.server_id,c.executor_id,c.connection_id,c.connection_generation)).rowcount == 1

    async def start(self):
        if not protocol_info()["remote_execution_ready"]:
            return
        if not await asyncio.to_thread(self._activate):
            return
        self.pump = ExecutionDispatchPump(factory=self.factory, channel=self.channel, access=self.access,
            fresh_publications=self.inventory.fresh, send=self.enqueue, send_lock=asyncio.Lock(),
            verify_link=self.verify, close_link=self.failed)
        self.pump.start()
        self.maintenance = asyncio.create_task(self._maintain(), name="embedded-publications")

    async def failed(self):
        self._stopping.set()
        if self.pump is not None:
            self.pump._stopping.set()
        if self._containment_task is None:
            self._containment_task = asyncio.create_task(
                self.host.shutdown(ShutdownPolicy(0,0)), name="embedded-failure-containment")
        try:
            await asyncio.to_thread(self._quiesce)
        except Exception as error:
            # A storage failure must not prevent native containment.
            self.state_failure = error

    async def enqueue(self, frame):
        if self._stopping.is_set():
            raise CoreError("STALE_GENERATION", "embedded_dispatch")
        # The outbox reserves four productive and two control items before
        # this callback. Retain every producer until it reports its receipt.
        task = asyncio.create_task(self._execute_owned(frame), name="embedded-" + frame["operation_id"])
        self.workers.add(task)
        task.add_done_callback(self.workers.discard)

    @asynccontextmanager
    async def _gate(self, session, action):
        if action in ("runtime.open", "turn.submit", "turn.steer"):
            async with session["gate"]:
                yield
        else:
            yield

    async def _request_grant(self, request):
        await asyncio.to_thread(self.verify)
        return await asyncio.to_thread(self.leases.issue, request, channel=self.channel)

    def _bind(self, frame, binding):
        raw = canonical_json(binding).decode()
        with self.factory.unit_of_work() as uow:
            self.verify(uow=uow)
            c = self.channel
            row = uow.connection.execute("SELECT binding_json FROM execution_local_publications "
                "WHERE server_id=? AND executor_id=? AND operation_id=?",
                (c.server_id,c.executor_id,frame["operation_id"])).fetchone()
            if row is not None:
                if row[0] != raw:
                    raise CoreError("OPERATION_CONFLICT", "embedded_binding")
                return
            uow.connection.execute("INSERT INTO execution_local_publications "
                "(server_id,executor_id,operation_id,session_id,binding_json) VALUES (?,?,?,?,?)",
                (c.server_id,c.executor_id,frame["operation_id"],frame["session_id"],raw))

    async def _execute_owned(self, frame):
        try:
            await self._execute(frame)
        except Exception as error:
            # A SENDING reservation has crossed the dispatch fence. Preserve it
            # for reconciliation; neither synthesize a receipt nor retry work.
            self.failure = error
            await self.failed()

    async def _execute(self, frame):
        await asyncio.to_thread(self.verify)
        action, payload = frame["action"], frame["payload"]
        key = frame["session_id"]
        if action == "runtime.open":
            if key in self.sessions or len(self.sessions) >= self.host.max_owned_slots:
                raise CoreError("CAPACITY_EXCEEDED", "embedded_dispatch")
            session = {"gate":asyncio.Lock(), "executor":None,
                       "scope":{name:frame[name] for name in _SCOPE}, "renew_at":None}
            self.sessions[key] = session
        else:
            session = self.sessions.get(key)
            if session is None or session["executor"] is None:
                raise CoreError("SESSION_UNKNOWN", "embedded_dispatch")
        async with self._gate(session, action):
            await asyncio.to_thread(self.verify)
            if action == "runtime.open":
                setup = await asyncio.to_thread(ApprovedLocalLaunch, self.inventory, session["scope"])
                executor, applied = await EmbeddedExecutor.authorize_r4(self.host, scope=session["scope"],
                    grant_id=frame["grant_id"], connection_id=self.channel.connection_id,
                    connection_generation=self.channel.connection_generation, request_grant=self._request_grant,
                    candidate=setup.candidate, workspace_root=setup.workspace_root,
                    environment=setup.environment, native_factory=self.native_factory)
                await asyncio.to_thread(self.leases.applied, applied.acknowledgement, channel=self.channel)
                session["executor"] = executor
                session["renew_at"] = time.monotonic() + max(0, applied.context.lease_deadline_monotonic-time.monotonic())/2
            executor = session["executor"]
            runtime = await executor._runtime()
            context = runtime.r4_operation_context(frame, connection_id=self.channel.connection_id,
                                                   connection_generation=self.channel.connection_generation)
            options = {}
            if action == "runtime.open":
                await asyncio.to_thread(executor.local_launch.check)
                prepared = await runtime.prepare(LaunchIntent(frame["agent_id"],frame["workspace_id"],
                    payload["adapter_id"],mode=payload["mode"],model=payload.get("model"),
                    auth_refs=executor.local_launch.auth_refs),context)
                epoch = "stream_" + secrets.token_hex(16)
                options = dict(prepared=prepared,stream_epoch=epoch)
            binding = prepare_r4_receipt_binding(frame, context, **options)
            await asyncio.to_thread(self._bind, frame, binding)
            await asyncio.to_thread(self.verify)
            if action == "runtime.open":
                receipt = await runtime.open(OpenOperation(frame["operation_id"],key,epoch,prepared),context)
            elif action == "turn.submit":
                receipt = await runtime.submit(TurnOperation(frame["operation_id"],key,payload["text"],
                    frame.get("expected_turn_id")),context)
            elif action in ("turn.steer","turn.interrupt"):
                receipt = await runtime.control(ControlOperation(frame["operation_id"],key,action.split(".")[1],
                    text=payload.get("text"),reason=payload.get("reason"),expected_turn_id=frame.get("expected_turn_id")),context)
            elif action == "runtime.close":
                receipt = await runtime.close(r4_close_operation(frame),context,wait_for_completion=True)
            else:
                raise CoreError("CAPABILITY_UNSUPPORTED", "embedded_dispatch")
            await self._publish(binding, receipt)
            if action == "runtime.close" and receipt.stage == "SUCCEEDED":
                self.sessions.pop(key, None)

    async def _publish(self, binding, receipt):
        source = binding["source"]
        key = OperationKey(source["server_id"],source["executor_id"],source["operation_id"])
        def persist():
            with self.factory.unit_of_work(write=False) as uow:
                old = uow.connection.execute("SELECT canonical_frame FROM execution_receipts "
                    "WHERE server_id=? AND executor_id=? AND operation_id=? ORDER BY receipt_revision DESC LIMIT 1",
                    (key.server_id,key.executor_id,key.operation_id)).fetchone()
            previous = json.loads(old[0]) if old else None
            revision = previous["receipt_revision"] + 1 if previous else 1
            frame = project_r4_bound_receipt(binding,receipt,key=key,receipt_revision=revision)
            unchanged = previous and {**frame,"receipt_revision":previous["receipt_revision"]} == previous
            if not unchanged:
                append_execution_receipt(self.factory,embedded_owner=self.inventory,frame=frame)
            if receipt.stage in ("SUCCEEDED","FAILED","CANCELLED"):
                with self.factory.unit_of_work() as uow:
                    self.verify(uow=uow)
                    uow.connection.execute("UPDATE execution_local_publications SET terminal=1 "
                        "WHERE server_id=? AND executor_id=? AND operation_id=?",
                        (key.server_id,key.executor_id,key.operation_id))
        # Only one publisher may allocate a source revision at a time.
        async with self._publish_lock:
            await asyncio.to_thread(persist)

    def _page(self):
        with self.factory.unit_of_work(write=False) as uow:
            self.verify(uow=uow)
            rows = uow.connection.execute("SELECT rowid,* FROM execution_local_publications "
                "WHERE server_id=? AND executor_id=? AND terminal=0 AND rowid>? ORDER BY rowid LIMIT 128",
                (self.channel.server_id,self.channel.executor_id,self._after)).fetchall()
            return [dict(row) for row in rows]

    async def _renew_owned(self, session_id, session):
        try:
            async with session["gate"]:
                if self._stopping.is_set() or self.sessions.get(session_id) is not session:
                    return
                executor = session["executor"]
                applied = await executor.renew_r4(scope=session["scope"],
                    connection_id=self.channel.connection_id,connection_generation=self.channel.connection_generation,
                    request_grant=self._request_grant)
                await asyncio.to_thread(self.leases.applied,applied.acknowledgement,channel=self.channel)
                session["renew_at"] = time.monotonic() + max(0,applied.context.lease_deadline_monotonic-time.monotonic())/2
        except Exception as error:
            if self.sessions.get(session_id) is session:
                self.failure = error
                await self.failed()

    async def _maintain(self):
        try:
            while not self._stopping.is_set():
                for session_id, session in list(self.sessions.items()):
                    if (session["renew_at"] is not None and time.monotonic() >= session["renew_at"]
                            and (session.get("renew_task") is None or session["renew_task"].done())):
                        task = asyncio.create_task(self._renew_owned(session_id, session), name="embedded-renew-" + session_id)
                        session["renew_task"] = task
                        self.renewals.add(task)
                        task.add_done_callback(self.renewals.discard)
                rows = await asyncio.to_thread(self._page)
                self._after = rows[-1]["rowid"] if rows else 0
                for row in rows:
                    key = OperationKey(row["server_id"],row["executor_id"],row["operation_id"])
                    receipt = await self.host.operation_receipt(session_id=row["session_id"],key=key)
                    if receipt is not None:
                        await self._publish(json.loads(row["binding_json"]),receipt)
                try:
                    await asyncio.wait_for(self._stopping.wait(),.1)
                except asyncio.TimeoutError:
                    pass
        except Exception as error:
            self.failure = error
            await self.failed()

    async def close(self):
        if self._close_task is None:
            self._close_task = asyncio.create_task(self._close(),name="embedded-dispatch-close")
        await asyncio.shield(self._close_task)

    async def _close(self):
        self._stopping.set()
        failures = []
        try:
            await asyncio.to_thread(self._quiesce)
        except Exception as error:
            self.state_failure = error
            failures.append(error)
        for task in (self.pump.stop() if self.pump is not None else None,
                     asyncio.shield(self.maintenance) if self.maintenance is not None else None):
            if task is not None:
                try:
                    await task
                except Exception as error:
                    failures.append(error)
        # Core drain can unblock a native producer even if outbox cleanup failed.
        if self._containment_task is None:
            self._containment_task = asyncio.create_task(self.host.shutdown(), name="embedded-core-drain")
        results = await asyncio.gather(*tuple(self.workers), *tuple(self.renewals), return_exceptions=True)
        failures.extend(result for result in results if isinstance(result, BaseException))
        try:
            self.containment_report = await asyncio.shield(self._containment_task)
        except Exception as error:
            failures.append(error)
        if failures:
            first = failures[0]
            if isinstance(first, Exception):
                raise first
            raise RuntimeError("An embedded producer was canceled before cleanup completed.") from first

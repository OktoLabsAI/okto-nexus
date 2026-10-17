"""Serve-owned local outbox execution through the shared Core contract."""
import asyncio
from contextlib import asynccontextmanager
import json
import logging
import math
import secrets
import sqlite3
import time
from datetime import datetime

from nexus_connector_core import (
    CoreError, LaunchIntent, OpenOperation, TurnOperation, ControlOperation, validate_harness_settings,
    OperationKey, OperationNotAdmitted, prepare_r4_receipt_binding, project_r4_bound_receipt,
    r4_close_operation, r4_native_decision_operation, ShutdownPolicy,
    OperationCapacityDeferred, CapacityRetryWaiter,
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
from .embedded_events import EmbeddedPublicationDeferred

_SCOPE = ("server_id", "executor_id", "binding_id", "agent_id", "workspace_id",
          "workspace_binding_id", "session_id", "session_owner_generation",
          "authorization_revision", "configuration_revision", "binding_revision", "credential_epoch")


class SessionAuthorityGate:
    """Concurrent containment controls, exclusive lease-context replacement."""
    def __init__(self):
        self.condition = asyncio.Condition()
        self.controls = 0
        self.updating = False

    @asynccontextmanager
    async def control(self):
        async with self.condition:
            await self.condition.wait_for(lambda: not self.updating)
            self.controls += 1
        try:
            yield
        finally:
            async with self.condition:
                self.controls -= 1
                self.condition.notify_all()

    @asynccontextmanager
    async def update(self):
        async with self.condition:
            await self.condition.wait_for(lambda: not self.controls and not self.updating)
            self.updating = True
        try:
            yield
        finally:
            async with self.condition:
                self.updating = False
                self.condition.notify_all()


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
        from ..adapters.outbound.sqlite.execution_capacity_authority import SqliteExecutionCapacityAuthority
        self.capacity_boot_id = 'capacity_' + secrets.token_hex(16)
        self.capacity_authority = SqliteExecutionCapacityAuthority(factory=self.factory, channel=self.channel,
            fresh_publications=inventory.fresh, verify_owner=self.verify,
            now=lambda: datetime.fromisoformat(self.deps.clock.now_iso().replace('Z', '+00:00')))
        self.sessions = {}
        self.workers = set()
        self.active_operations = set()
        self.worker_agents = {}
        self.worker_sessions = {}
        self.renewals = set()
        self.pump = None
        self.maintenance = None
        self.lease_maintenance = None
        self.native_factory = None
        self.failure = None
        self._stopping = asyncio.Event()
        self._close_task = None
        self._shutdown_started = None
        self._shutdown_deadline = None
        self._shutdown_policy = ShutdownPolicy()
        self._shutdown_recovery_task = None
        self._after = 0
        self._publish_locks = {}
        self._containment_task = None
        self.containment_report = None
        self.state_failure = None
        self.recovery_failure = None
        self._recovery_task = None
        self._recovery_lock = asyncio.Lock()
        from .embedded_events import EmbeddedEventPublisher
        self.events = EmbeddedEventPublisher(self)
        from .embedded_agent_recovery import EmbeddedAgentRecovery
        self.agents = EmbeddedAgentRecovery(self)
        from .embedded_tools import EmbeddedToolsOwner
        self.tools = EmbeddedToolsOwner(self)
        from .embedded_capacity import EmbeddedCapacityPublication
        self.capacity_publication = EmbeddedCapacityPublication(self)
        self.capacity_waiter = CapacityRetryWaiter(self._capacity_revision)
        original_launch=self.host.local_launch_factory
        if original_launch is not None:
            self.host.local_launch_factory=lambda scope:self.tools.decorate(original_launch(scope))

    async def check_capacity_scope(self, request, *, action):
        if self._stopping.is_set() or self.failure is not None:
            return 'RECOVERING'
        return await self.capacity_authority.check_capacity_scope(request, action=action)

    async def execution_capacity(self):
        """Compose the shared Core port with this owner's real authority."""
        return await self.host.capacity_service(server_id=self.channel.server_id,
            executor_id=self.channel.executor_id, boot_id=self.capacity_boot_id, authority=self)

    async def _capacity_revision(self):
        ledger = await self.host._ledger()
        return await ledger.capacity_revision()

    async def _capacity_flow(self, binding, state, sequence):
        from nexus_connector_core.capacity_codec import capacity_dispatch_state
        from ..adapters.outbound.sqlite.execution_capacity_flow import record_capacity_dispatch_state
        frame = capacity_dispatch_state(binding, state=state, sequence=sequence)
        await asyncio.to_thread(record_capacity_dispatch_state, self.factory, channel=self.channel, frame=frame)

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
        # Only an empty installation uses fresh activation. Retained stores
        # must pass the Core resource reconciliation performed by start().
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
        from .embedded_context import EmbeddedContextObserver
        self.context_observer = EmbeddedContextObserver(self)
        self.inventory.dispatcher.context_dispatcher.service.canonical_observer = self.context_observer
        await self._start_attempt()
        if self.pump is None and not self._stopping.is_set():
            self._recovery_task = asyncio.create_task(self._recover_automatically(),name='automatic-runtime-recovery')

    def _recovery_enabled(self):
        from ..application.runtime_policy import defaults
        with self.factory.unit_of_work(write=False) as uow:
            return defaults(uow.connection)['automatic_recovery']

    def _recovery_event(self, code, message, *, agent_id=None):
        with self.factory.unit_of_work() as uow:
            uow.connection.execute('INSERT INTO runtime_recovery_events(executor_id,created_at,code,message,agent_id) VALUES(?,?,?,?,?)',
                (self.channel.executor_id,self.deps.clock.now_iso(),code,message,agent_id))
        logger = logging.getLogger(__name__)
        (logger.info if code in ('RECOVERY_READY', 'RECOVERY_AGENT_READY') else logger.warning)('Runtime recovery: %s %s',code,message)

    async def _recover_automatically(self):
        from nexus_connector_core import RuntimeAutomation
        from ..application.runtime_recovery import drain_pending, mark_recovery_attention
        reported = False
        async def attempt():
            await self._start_attempt()
            return self.pump is not None
        async def exhausted():
            nonlocal reported
            await asyncio.to_thread(mark_recovery_attention, self)
            if not reported:
                reported = True
                await asyncio.to_thread(self._recovery_event,'RECOVERY_ATTENTION_REQUIRED','Initial recovery attempts did not resolve retained state. Automatic checks continue; operator recovery is available. No work was replayed.')
        await RuntimeAutomation().recover(attempt=attempt, stop=self._stopping,
            enabled=lambda: asyncio.to_thread(self._recovery_enabled),
            pending=lambda: asyncio.to_thread(drain_pending, self.deps), exhausted=exhausted, continuous=True)

    async def _start_attempt(self, *, manual=False):
        async with self._recovery_lock:
            if self.pump is not None or self._stopping.is_set():
                return
            await self._start_attempt_locked(manual=manual)

    async def retry_recovery(self, agent_id=None):
        await asyncio.to_thread(self.verify)
        await self._start_attempt(manual=True)
        await self.agents.tick(manual=True, agent_id=agent_id)
        await self.agents.observe()
        ready = self.pump is not None and (not self.agents.blocked if agent_id is None else agent_id not in self.agents.blocked)
        return {'state': 'READY' if ready else 'RECOVERING',
                'recovering_agents': sorted(self.agents.blocked),
                'error_code': getattr(self.recovery_failure or self.agents.current_errors.get(agent_id), 'code', None),
                'message': ('Runtime restored. Previous work was not replayed.' if ready else
                    'Automatic recovery is still pending for the affected agents. Retained history was preserved.')}

    async def recovery_plan(self, agent_id=None):
        from .embedded_reconciliation import EmbeddedReconciliation
        async with self._recovery_lock:
            return await EmbeddedReconciliation(self).recovery_plan(agent_id)

    async def confirm_recovery(self, plan, actor):
        from .embedded_reconciliation import EmbeddedReconciliation
        async with self._recovery_lock:
            await EmbeddedReconciliation(self).confirm_stopped(plan, actor)
            if self.pump is None:
                await self._start_attempt_locked(manual=True)
        return await self.retry_recovery(plan.get('agent_id'))

    async def _start_attempt_locked(self, *, manual=False):
        if not protocol_info()["remote_execution_ready"]:
            return
        if not manual and not await asyncio.to_thread(self._recovery_enabled):
            if not await asyncio.to_thread(self._activate): return
        self.recovery_failure=None
        try:
            await self.agents.initialize()
            await self.agents.tick(manual=manual)
            await self.agents.observe()
            def activate_host():
                with self.factory.unit_of_work() as uow:
                    self.verify(uow=uow)
                    uow.connection.execute("UPDATE execution_executors SET control_state='CONTROL_READY' "
                        "WHERE server_id=? AND executor_id=? AND owner_instance_id=? AND generation=?",
                        (self.channel.server_id,self.channel.executor_id,
                         self.channel.connection_id,self.channel.connection_generation))
            await asyncio.to_thread(activate_host)
        except Exception as error:
            self.recovery_failure = error
            await asyncio.to_thread(self._recovery_event,'RECOVERY_BLOCKED',
                f"{type(error).__name__}: {getattr(error,'code','UNAVAILABLE')} at {getattr(error,'stage','shared runtime resources')}")
            return
        if self._stopping.is_set():
            return
        self.pump = ExecutionDispatchPump(factory=self.factory, channel=self.channel, access=self.access,
            fresh_publications=self.inventory.fresh, send=self.enqueue, send_lock=asyncio.Lock(),
            verify_link=self.verify, close_link=self.failed,
            retained_operations=lambda: tuple(self.active_operations),
            wake_deliveries=self.deps.runtime_dispatcher.wake,
            resolve_native_input=self.deps.native_decisions.inputs.resolve)
        self.pump.start()
        self.lease_maintenance = asyncio.create_task(self._maintain_leases(), name="embedded-lease-renewals")
        self.maintenance = asyncio.create_task(self._maintain(), name="embedded-publications")
        await asyncio.to_thread(self._recovery_event,'RECOVERY_READY','Local host ready. Agents with retained history recover independently; previous work was not replayed.')

    async def _recover_publications(self, *, agent_id=None, progress=None):
        """Publish retained facts once before any new dispatch is enabled."""
        from .embedded_initial_refusal import EmbeddedInitialRefusal
        await EmbeddedInitialRefusal(self).recover(agent_id=agent_id)
        after = 0
        while True:
            rows = await asyncio.to_thread(self._page, after=after, agent_id=agent_id)
            if not rows:
                return
            for row in rows:
                # A live producer can still prove no native effect. Its
                # SUBMISSION_STARTED journal entry is a crash fence, not a
                # settled receipt to publish over the producer's final fact.
                if (row["operation_id"] in self.active_operations
                        or self.sessions.get(row['session_id'], {}).get('initial_refusal')):
                    continue
                await asyncio.to_thread(self.verify)
                key = OperationKey(row["server_id"],row["executor_id"],row["operation_id"])
                receipt = await self.host.historical_receipt(session_id=row["session_id"],key=key)
                if receipt is not None:
                    await self._publish(json.loads(row["binding_json"]),receipt)
                if progress is not None:
                    progress()
            after = rows[-1]["rowid"]

    async def failed(self):
        if self.failure is None and self.pump is not None:
            self.failure = self.pump.error
        if not self._stopping.is_set():
            error = self.failure
            # Preserve the failure path without logging native payloads,
            # credentials, or exception messages supplied by a harness.
            import traceback
            from pathlib import Path
            origin = ' -> '.join(f'{Path(frame.filename).name}:{frame.lineno}:{frame.name}'
                for frame in traceback.extract_tb(error.__traceback__)[-5:]) if error else 'unavailable'
            logging.getLogger(__name__).error(
                "Embedded runtime containment: type=%s code=%s stage=%s origin=%s",
                type(error).__name__, getattr(error, "code", None), getattr(error, "stage", None), origin)
        self._stopping.set()
        self.capacity_waiter.stop()
        if self.pump is not None:
            self.pump._stopping.set()
        if self._containment_task is None:
            self._containment_task = asyncio.create_task(
                self.host.shutdown(ShutdownPolicy(0,0), close_stores=False), name="embedded-failure-containment")
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
        self.worker_agents[task] = frame["agent_id"]
        self.worker_sessions[task] = frame['session_id']
        task.add_done_callback(self.workers.discard)
        task.add_done_callback(lambda done: self.worker_agents.pop(done, None))
        task.add_done_callback(lambda done: self.worker_sessions.pop(done, None))

    @asynccontextmanager
    async def _gate(self, session, action):
        if action in ("runtime.open", "turn.submit", "turn.steer"):
            async with session["gate"]:
                if action == "runtime.open":
                    session["opening"] = True
                try:
                    yield
                finally:
                    if action == "runtime.open":
                        # Join any opening renewal before releasing the gate
                        # to exact-context productive operations.
                        async with session["authority_gate"].control():
                            session["opening"] = False
        else:
            # Controls bypass a blocked productive native call, but must keep
            # their selected Core context current across local persistence.
            async with session["authority_gate"].control():
                yield

    async def _request_grant(self, request):
        await asyncio.to_thread(self.verify)
        try:
            return await asyncio.to_thread(self.leases.issue, request, channel=self.channel)
        except OktoNexusError as error:
            if request['purpose'] == 'initial':
                from .embedded_initial_refusal import InitialLeaseDenied
                try:
                    recorded = await asyncio.to_thread(self.leases.access.session_containment.denied,
                        request, channel=self.channel)
                except (OSError, sqlite3.OperationalError) as persistence_error:
                    raise InitialLeaseDenied(request) from persistence_error
                except OktoNexusError as persistence_error:
                    if persistence_error.code != ErrorCode.DB_ERROR:
                        raise
                    raise InitialLeaseDenied(request) from persistence_error
                if recorded:
                    raise InitialLeaseDenied() from error
            raise

    def _bind(self, frame, binding, stream_epoch=None):
        raw = canonical_json(binding).decode()
        with self.factory.unit_of_work() as uow:
            self.verify(uow=uow)
            from ..application.execution_agent_recovery import require_agent_ready
            require_agent_ready(uow.connection, frame['server_id'], frame['executor_id'], frame['agent_id'])
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
            if stream_epoch is not None:
                uow.connection.execute("INSERT INTO execution_local_streams "
                    "(server_id,executor_id,session_id,stream_epoch,opening_operation_id,binding_id,agent_id) "
                    "VALUES (?,?,?,?,?,?,?)",(c.server_id,c.executor_id,frame["session_id"],stream_epoch,
                        frame["operation_id"],frame["binding_id"],frame["agent_id"]))

    async def _execute_owned(self, frame):
        self.active_operations.add(frame['operation_id'])
        try:
            continuation, deferred, sequence = {}, None, 0
            while True:
                if deferred is not None and (self._stopping.is_set() or
                        self.sessions.get(frame['session_id']) is not continuation.get('session')):
                    await self._publish(continuation['binding'], deferred.stopped_receipt())
                    return
                version = self.capacity_waiter.version
                try:
                    if deferred is not None:
                        sequence += 1
                        await self._capacity_flow(continuation['binding'], 'RUNNING', sequence)
                        self.active_operations.add(frame['operation_id'])
                    await self._execute(frame, continuation=continuation)
                    break
                except OperationCapacityDeferred as error:
                    error.require_binding(continuation['binding'])
                    deferred = error
                    sequence += 1
                    await self._capacity_flow(continuation['binding'], 'WAITING', sequence)
                    self.active_operations.discard(frame['operation_id'])
                    if not await self.capacity_waiter.wait(version):
                        await self._publish(continuation['binding'], deferred.stopped_receipt())
                        return
        except Exception as error:
            # Preserve uncertain work, but contain only its known subject.
            try:
                from .embedded_initial_refusal import InitialLeaseDenied
                if isinstance(error, InitialLeaseDenied):
                    session = self.sessions[frame['session_id']]
                    session['initial_refusal'] = True
                    if error.pending_request is not None:
                        session['initial_refusal_request'] = error.pending_request
                    self.agents.recover_session(frame['session_id'])
                    return
                if isinstance(error, EmbeddedPublicationDeferred):
                    await self.agents.defer_publication(frame['agent_id'])
                    return
                session = self.sessions.get(frame['session_id'])
                if session is not None and (session.get('recovering') or (
                        isinstance(error, CoreError) and error.code == 'EVENT_STREAM_UNAVAILABLE')):
                    self.agents.recover_session(frame['session_id'])
                    return
                await self.agents.fail(frame['agent_id'], error)
            except Exception as shared_error:
                if self.failure is None:
                    self.failure = shared_error
                await self.failed()
        finally:
            self.active_operations.discard(frame['operation_id'])

    async def _execute(self, frame, *, continuation=None):
        continuation = {} if continuation is None else continuation
        await asyncio.to_thread(self.verify)
        action, payload = frame["action"], frame["payload"]
        key = frame["session_id"]
        resuming = action == 'runtime.open' and 'options' in continuation
        if resuming:
            session = continuation['session']
            if self.sessions.get(key) is not session:
                raise CoreError('SESSION_UNKNOWN', 'embedded_dispatch')
        elif action == "runtime.open":
            if key in self.sessions or len(self.sessions) >= self.host.max_owned_slots:
                raise CoreError("CAPACITY_EXCEEDED", "embedded_dispatch")
            session = {"gate":asyncio.Lock(), "authority_gate":SessionAuthorityGate(), "executor":None,
                       "scope":{name:frame[name] for name in _SCOPE}, "renew_at":None}
            self.sessions[key] = session
        else:
            session = self.sessions.get(key)
            if session is None or session["executor"] is None:
                raise CoreError("SESSION_UNKNOWN", "embedded_dispatch")
        continuation['session'] = session
        async with self._gate(session, action):
            await asyncio.to_thread(self.verify)
            if session.get('recovering'):
                raise CoreError('EVENT_STREAM_UNAVAILABLE', 'embedded_session_recovery')
            if action == "runtime.open" and not resuming:
                setup = await asyncio.to_thread(ApprovedLocalLaunch, self.inventory, session["scope"])
                await self.tools.prepare(frame,setup)
                tool_config=self.tools.configurations.get(key)
                executor, applied = await EmbeddedExecutor.authorize_r4(self.host, scope=session["scope"],
                    grant_id=frame["grant_id"], connection_id=self.channel.connection_id,
                    connection_generation=self.channel.connection_generation, request_grant=self._request_grant,
                    candidate=setup.candidate, workspace_root=setup.workspace_root,
                    environment=setup.environment, native_factory=self.native_factory,
                    native_action_factory=tool_config["native_factory"] if tool_config else None,
                    native_approvals_enabled=bool(self.deps.config.feature_hitl and
                        setup.candidate.adapter_id in {"codex_app_server", "claude_stream", "pi_rpc"}))
                await asyncio.to_thread(self.leases.applied, applied.acknowledgement, channel=self.channel)
                session["executor"] = executor
                self._schedule_renewal(session, applied)
            executor = session["executor"]
            runtime = await executor._runtime()
            context = runtime.r4_operation_context(frame, connection_id=self.channel.connection_id,
                                                   connection_generation=self.channel.connection_generation)
            options = continuation.get('options', {})
            if action == "runtime.open" and not resuming:
                await asyncio.to_thread(executor.local_launch.check)
                prepared = await runtime.prepare(LaunchIntent(frame["agent_id"],frame["workspace_id"],
                    payload["adapter_id"],mode=payload["mode"],model=payload.get("model"),
                    auth_refs=executor.local_launch.auth_refs,
                    mcp_preset=tuple(frame['payload'].get('mcp_preset', [])),
                    harness_settings=validate_harness_settings(
                        payload['adapter_id'], payload.get('harness_settings', {}))),context)
                epoch = "stream_" + secrets.token_hex(16)
                options = dict(prepared=prepared,stream_epoch=epoch)
                continuation['options'] = options
            elif action in ("approval.decide", "input.provide"):
                native_operation = r4_native_decision_operation(frame)
                options = dict(applied_operation=native_operation)
            if action == "runtime.open":
                context = runtime.r4_operation_context(frame, connection_id=self.channel.connection_id,
                    connection_generation=self.channel.connection_generation)
            binding = prepare_r4_receipt_binding(frame, context, **options)
            continuation['binding'] = binding
            await asyncio.to_thread(self._bind, frame, binding, options.get("stream_epoch"))
            if self.host.capacity_enabled and action in ('runtime.open', 'turn.submit'):
                capacity = await self.execution_capacity()
                await capacity.bind_admitted_capacity_operation(binding)
            await asyncio.to_thread(self.verify)
            if action == "runtime.open":
                prepared, epoch = options['prepared'], options['stream_epoch']
                try:
                    context = runtime.r4_operation_context(frame, connection_id=self.channel.connection_id,
                        connection_generation=self.channel.connection_generation)
                    receipt = await runtime.open(OpenOperation(frame["operation_id"],key,epoch,prepared),context)
                except OperationCapacityDeferred:
                    raise
                except CoreError as error:
                    # The stored Core receipt describes the opening. Resource
                    # containment below is a separate proof, even after spawn.
                    receipt = await self.host.historical_receipt(session_id=key,
                        key=OperationKey(frame['server_id'], frame['executor_id'], frame['operation_id']))
                    if (receipt is None or receipt.stage != 'FAILED'
                            or receipt.error_code != error.code
                            or receipt.operation_id != frame['operation_id']):
                        raise
            elif action == "turn.submit":
                receipt = await self._command_receipt(frame, lambda: runtime.submit(
                    TurnOperation(frame["operation_id"],key,payload["text"],frame.get("expected_turn_id")),context))
            elif action in ("turn.steer","turn.interrupt"):
                receipt = await self._command_receipt(frame, lambda: runtime.control(
                    ControlOperation(frame["operation_id"],key,action.split(".")[1],text=payload.get("text"),
                        reason=payload.get("reason"),expected_turn_id=frame.get("expected_turn_id")),context))
            elif action == "runtime.close":
                receipt = await runtime.close(r4_close_operation(frame),context,wait_for_completion=True)
            elif action in ("approval.decide", "input.provide"):
                receipt = await self._command_receipt(frame,
                    lambda: runtime.decide_native_approval(operation=native_operation, context=context))
            else:
                raise CoreError("CAPABILITY_UNSUPPORTED", "embedded_dispatch")
            if action == 'runtime.open' and receipt.stage == 'SUBMITTED':
                await self.context_observer.publish_support(runtime, key)
            await self._publish(binding, receipt)
            if action == 'runtime.open' and receipt.stage == 'FAILED':
                report = await runtime.shutdown(ShutdownPolicy(0, 0))
                if ('unknown' in report.session_outcomes.values() or any(
                        facts['process_state'] != 'STOPPED' or facts['release_pending']
                        for facts in runtime.shutdown_resources().values())):
                    raise CoreError('RECONCILIATION_REQUIRED', 'embedded_session_containment')
                if not await self.host.close_native_actions(
                        executor_id=self.channel.executor_id, session_id=key, timeout_seconds=5):
                    raise CoreError('RECONCILIATION_REQUIRED', 'embedded_native_action_containment')
                await self.events.recover(agent_id=frame['agent_id'])
                from .embedded_reconciliation import EmbeddedReconciliation
                await EmbeddedReconciliation(self).release_session(key, failed_open=not receipt.possible_effect)
                await self.tools.release_session(key)
                self.sessions.pop(key, None)
            if action == "runtime.close" and receipt.stage == "SUCCEEDED":
                await self.tools.release_session(key)
                self.sessions.pop(key, None)

    async def _command_receipt(self, frame, invoke):
        try:
            return await invoke()
        except OperationCapacityDeferred:
            raise
        except OperationNotAdmitted as error:
            # Core refused admission before any effect. _publish durably
            # records this bound fact in Server before it becomes observable;
            # the Core journal's containment reserve remains untouched.
            return error.refusal
        except CoreError as error:
            # A stale target or another proved pre-write refusal belongs to
            # this command. It must not contain unrelated work in a healthy
            # session. Exception flags alone cannot establish that proof.
            if error.possible_effect or not error.retry_safe:
                raise
            receipt = await self.host.historical_receipt(session_id=frame['session_id'],
                key=OperationKey(frame['server_id'], frame['executor_id'], frame['operation_id']))
            if (receipt is None or receipt.stage != 'FAILED' or receipt.possible_effect
                    or not receipt.retry_safe or receipt.error_code != error.code
                    or receipt.operation_id != frame['operation_id']
                    or receipt.session_id != frame['session_id']):
                raise
            return receipt

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
            return not unchanged
        # Serialize revisions for this operation, never unrelated agents.
        async with self._publish_locks.setdefault(key, asyncio.Lock()):
            try:
                changed = await asyncio.to_thread(persist)
            except (OSError, sqlite3.OperationalError) as error:
                raise EmbeddedPublicationDeferred() from error
            except OktoNexusError as error:
                if error.code != ErrorCode.DB_ERROR:
                    raise
                raise EmbeddedPublicationDeferred() from error
            if changed and self.deps.runtime_dispatcher is not None:
                self.deps.runtime_dispatcher.wake()

    def _page(self, *, after=None, agent_id=None):
        parameters = [self.channel.server_id, self.channel.executor_id,
                      self._after if after is None else after]
        agent_predicate = ""
        if agent_id is not None:
            # Drive from pending rows; never materialize an agent's full history.
            agent_predicate = (" AND EXISTS (SELECT 1 FROM execution_operations o "
                "WHERE o.server_id=p.server_id AND o.executor_id=p.executor_id "
                "AND o.operation_id=p.operation_id AND o.subject_agent_id=?)")
            parameters.append(agent_id)
        with self.factory.unit_of_work(write=False) as uow:
            self.verify(uow=uow)
            rows = uow.connection.execute("SELECT p.rowid,p.* FROM execution_local_publications p "
                "WHERE p.server_id=? AND p.executor_id=? AND p.terminal=0 AND p.rowid>?"
                + agent_predicate + " ORDER BY p.rowid LIMIT 128", parameters).fetchall()
            return [dict(row) for row in rows]

    @asynccontextmanager
    async def _renewal_gate(self, session):
        # Core follows compatible installed renewals during preparation/open.
        # Productive turns retain their exact-context exclusion contract.
        if session.get("opening"):
            async with session["authority_gate"].update():
                if session.get("opening"):
                    yield
                    return
        async with session["gate"], session["authority_gate"].update():
            yield

    def _schedule_renewal(self, session, applied):
        now = time.monotonic()
        # Reserve the observed request/application cost on top of the normal
        # half-life margin. In particular, short leases must not spend half
        # their remaining life waiting before starting another slow grant.
        # This changes scheduling only, never the authority's actual deadline.
        elapsed = max(0, now - session['executor'].lease_request_started)
        remaining = max(0, applied.context.lease_deadline_monotonic - now)
        session['renew_at'] = now + max(0, remaining / 2 - elapsed)

    async def _renew_owned(self, session_id, session):
        try:
            async with self._renewal_gate(session):
                if self._stopping.is_set() or self.sessions.get(session_id) is not session:
                    return
                executor = session["executor"]
                applied = await executor.renew_r4(scope=session["scope"],
                    connection_id=self.channel.connection_id,connection_generation=self.channel.connection_generation,
                    request_grant=self._request_grant)
                await asyncio.to_thread(self.leases.applied,applied.acknowledgement,channel=self.channel)
                self._schedule_renewal(session, applied)
        except Exception as error:
            if self.sessions.get(session_id) is session:
                if session.get('recovering'):
                    self.agents.recover_session(session_id)
                    return
                # Expired/revoked session authority is an expected containment
                # boundary, not a failure of every runtime on this executor.
                expected = (isinstance(error, CoreError) and error.code in {
                    'AGENT_REVOKED', 'SESSION_UNKNOWN', 'STALE_GENERATION',
                    'LEASE_EXPIRED', 'LEASE_REVALIDATION_REQUIRED'}) or (
                    isinstance(error, OktoNexusError) and error.code in {
                        ErrorCode.CONFLICT, ErrorCode.PERMISSION_DENIED})
                if expected:
                    try:
                        await asyncio.to_thread(self.verify)
                        # Retain the scoped cleanup owner even if shutdown or
                        # release proof is delayed. An unavailable stop must
                        # not escalate into containment of healthy siblings.
                        self.agents.recover_session(session_id)
                        return
                    except Exception as containment_error:
                        error = containment_error
                try:
                    await self.agents.fail(session['scope']['agent_id'], error)
                except Exception as shared_error:
                    if self.failure is None:
                        self.failure = shared_error
                    await self.failed()

    async def _maintain_leases(self):
        """Schedule authority independently of history and queue admission.

        Only dispatch work here. Each session keeps its single renewal worker;
        a slow database request or authority gate never delays its siblings.
        Shutdown joins both this scheduler and every worker it produced.
        """
        try:
            while not self._stopping.is_set():
                for session_id, session in list(self.sessions.items()):
                    if (not session.get('recovering') and session["scope"]["agent_id"] not in self.agents.blocked and session["renew_at"] is not None and time.monotonic() >= session["renew_at"]
                            and (session.get("renew_task") is None or session["renew_task"].done())):
                        task = asyncio.create_task(self._renew_owned(session_id, session), name="embedded-renew-" + session_id)
                        session["renew_task"] = task
                        self.renewals.add(task)
                        task.add_done_callback(self.renewals.discard)
                try:
                    await asyncio.wait_for(self._stopping.wait(), .05)
                except asyncio.TimeoutError:
                    pass
        except Exception as error:
            if self.failure is None:
                self.failure = error
            await self.failed()

    async def _maintain(self):
        from nexus_connector_core import DEFAULT_RUNTIME_AUTOMATION
        pending_at=0
        try:
            while not self._stopping.is_set():
                self.capacity_publication.tick()
                await self.agents.tick()
                if time.monotonic()>=pending_at:
                    from ..application.runtime_recovery import drain_pending
                    try:
                        await asyncio.to_thread(drain_pending,self.deps)
                    except OktoNexusError as error:
                        # Queue admission is transactional and precedes native
                        # delivery. Contention here does not invalidate live
                        # sessions or the executor's ownership. Retry the same
                        # durable queue on a later tick, after lease renewal.
                        if error.code != ErrorCode.DB_ERROR or not error.retryable:
                            raise
                        logging.getLogger(__name__).warning(
                            'Pending-message admission deferred by transient storage contention; runtime remains active.')
                    pending_at=time.monotonic()+DEFAULT_RUNTIME_AUTOMATION.message_interval
                try:
                    await asyncio.wait_for(self._stopping.wait(),.1)
                except asyncio.TimeoutError:
                    pass
        except Exception as error:
            if self.failure is None:
                self.failure = error
            await self.failed()

    def _start_close(self):
        if self._close_task is None:
            if self._shutdown_started is None:
                self._shutdown_started = asyncio.get_running_loop().time()
            self._close_task = asyncio.create_task(self._close(), name="embedded-dispatch-close")
        return self._close_task

    def shutdown_status(self):
        """Read retained ownership without waiting for storage or a native probe."""
        task = self._close_task
        error = None
        if task is not None and task.done():
            if task.cancelled():
                error = "SHUTDOWN_INTERRUPTED"
            elif task.exception() is not None:
                error = "SHUTDOWN_RECOVERY_REQUIRED"
        resources = self.host.shutdown_resources()
        drained = task is not None and task.done() and error is None and not resources
        return {"state": "DRAINED" if drained else (
                    "DRAINING_PENDING" if self._shutdown_started is not None else "RUNNING"),
                "deadline_monotonic": self._shutdown_deadline,
                "resources": resources, "error_code": error}

    async def request_shutdown(self, *, timeout_seconds=50.0):
        """Bound the observation, never the lifetime of the retained owner.

        The first request fixes one deadline for all resources. Subsequent
        requests neither extend it nor cancel an in-flight cleanup. A finished
        uncertain/failed pass can recover the same runtime owners.
        """
        if (isinstance(timeout_seconds, bool)
                or not isinstance(timeout_seconds, (int, float))
                or not math.isfinite(timeout_seconds) or timeout_seconds < 0):
            raise ValueError("The shutdown timeout must be finite and nonnegative.")
        loop = asyncio.get_running_loop()
        if self._shutdown_deadline is None:
            started = self._shutdown_started if self._shutdown_started is not None else loop.time()
            deadline = started + timeout_seconds
            if not math.isfinite(deadline):
                raise ValueError("The shutdown deadline must be finite.")
            self._shutdown_deadline = deadline
            # Reserve up to five seconds for observation and reporting.
            budget = max(0.0, timeout_seconds - 5.0)
            self._shutdown_policy = ShutdownPolicy(min(30.0, budget),
                min(15.0, max(0.0, budget - 30.0)))
        if self._shutdown_recovery_task is None:
            self._start_close()
            self._shutdown_recovery_task = asyncio.create_task(
                self._recover_shutdown(), name="embedded-shutdown-recovery")
        await asyncio.wait((self._shutdown_recovery_task,),
            timeout=max(0.0, self._shutdown_deadline - loop.time()))
        return self.shutdown_status()

    async def _recover_shutdown(self):
        while True:
            try:
                await asyncio.shield(self._start_close())
            except Exception:
                # An error is not proof that the stores or native owners were
                # released. Keep the same host and retry only a finished pass.
                pass
            if self.shutdown_status()["state"] == "DRAINED":
                return
            await asyncio.sleep(.1)
            self._close_task = None

    async def wait_shutdown(self):
        """Keep the owning loop alive until the requested shutdown resolves."""
        if self._shutdown_recovery_task is None:
            raise RuntimeError("Shutdown must be requested before waiting for recovery.")
        await asyncio.shield(self._shutdown_recovery_task)

    async def close(self):
        await asyncio.shield(self._start_close())

    async def _publish_shutdown_history(self):
        try:
            await self._recover_publications()
            await self.events.recover()
            from .embedded_reconciliation import EmbeddedReconciliation
            reconciliation = EmbeddedReconciliation(self)
            for row in await asyncio.to_thread(reconciliation._records, pending_only=True):
                report = self.containment_report.get((self.channel.executor_id, row['session_id']))
                if report is None or 'unknown' in report.session_outcomes.values():
                    continue
                receipt = await self.host.historical_receipt(session_id=row['session_id'],
                    key=OperationKey(self.channel.server_id, self.channel.executor_id, row['open_operation_id']))
                if receipt is not None and receipt.stage in ('SUBMITTED', 'SUCCEEDED'):
                    await reconciliation.release_session(row['session_id'])
        except OktoNexusError as error:
            if error.code != ErrorCode.CONFLICT:
                raise
            # A superseded owner must still contain its processes and close
            # its stores. Only the new owner may publish the retained history.
            try:
                await asyncio.to_thread(self.verify)
            except OktoNexusError as ownership_error:
                if ownership_error.code != ErrorCode.CONFLICT:
                    raise
            else:
                raise error

    async def _close(self):
        self._stopping.set()
        self.capacity_waiter.stop()
        # Native containment must start before any database or publication
        # wait. Keep the journals alive for the producers joined below.
        if self.pump is not None:
            self.pump._stopping.set()
        if self._containment_task is not None and self._containment_task.done():
            # A completed pass can still leave uncertain ownership or a
            # deferred publication. Reobserve the same owners and reopen the
            # history phase before retrying; never duplicate a pending pass.
            self._containment_task = None
        if self._containment_task is None:
            policy = self._shutdown_policy
            if (self._shutdown_deadline is not None
                    and asyncio.get_running_loop().time() >= self._shutdown_deadline):
                policy = ShutdownPolicy(0, 0)
            self._containment_task = asyncio.create_task(
                self.host.shutdown(policy, close_stores=False), name="embedded-core-drain")
        failures = []
        try:
            await asyncio.to_thread(self._quiesce)
        except Exception as error:
            self.state_failure = error
            failures.append(error)
        for task in (self.pump.stop() if self.pump is not None else None,
                     asyncio.shield(self._recovery_task) if self._recovery_task is not None else None,
                     self.capacity_publication.close(),
                     self.capacity_waiter.aclose(),
                     asyncio.shield(self.lease_maintenance) if self.lease_maintenance is not None else None,
                     asyncio.shield(self.maintenance) if self.maintenance is not None else None):
            if task is not None:
                try:
                    await task
                except Exception as error:
                    failures.append(error)
        await self.agents.close()
        results = await asyncio.gather(*tuple(self.workers), *tuple(self.renewals), return_exceptions=True)
        failures.extend(result for result in results if isinstance(result, BaseException))
        try:
            self.containment_report = await asyncio.shield(self._containment_task)
            # A producer may have finished containment while it was being
            # joined. Refresh the report without closing its durable history.
            self.containment_report = await self.host.shutdown(ShutdownPolicy(0, 0), close_stores=False)
            # Native shutdown can append its last receipt/events after the
            # periodic publishers stop. Commit those facts before closing
            # their journals, including unknown outcomes without a result.
            await self._publish_shutdown_history()
            # All dispatch/publication producers have returned. The host now
            # joins history readers and closes only resolved Core resources.
            if not any('unknown' in report.session_outcomes.values()
                       for report in self.containment_report.values()):
                self.containment_report = await self.host.shutdown(ShutdownPolicy(0,0))
        except Exception as error:
            failures.append(error)
        try:
            certain=self.containment_report is not None and not any(
                "unknown" in report.session_outcomes.values() for report in self.containment_report.values())
            await self.tools.close(release=certain)
        except Exception as error:
            failures.append(error)
        if failures:
            first = failures[0]
            if isinstance(first, Exception):
                raise first
            raise RuntimeError("An embedded producer was canceled before cleanup completed.") from first

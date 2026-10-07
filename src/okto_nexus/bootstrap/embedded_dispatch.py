"""Serve-owned local outbox execution through the shared Core contract."""
import asyncio
from contextlib import asynccontextmanager
import json
import logging
import math
import secrets
import time

from nexus_connector_core import (
    CoreError, LaunchIntent, OpenOperation, TurnOperation, ControlOperation, validate_harness_settings,
    OperationKey, prepare_r4_receipt_binding, project_r4_bound_receipt,
    r4_close_operation, r4_native_decision_operation, ShutdownPolicy,
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
        self.worker_agents = {}
        self.renewals = set()
        self.pump = None
        self.maintenance = None
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
        original_launch=self.host.local_launch_factory
        if original_launch is not None:
            self.host.local_launch_factory=lambda scope:self.tools.decorate(original_launch(scope))

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
                'error_code': getattr(self.recovery_failure or self.agents.errors.get(agent_id), 'code', None),
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
            resolve_native_input=self.deps.native_decisions.inputs.resolve)
        self.pump.start()
        self.maintenance = asyncio.create_task(self._maintain(), name="embedded-publications")
        await asyncio.to_thread(self._recovery_event,'RECOVERY_READY','Local host ready. Agents with retained history recover independently; previous work was not replayed.')

    async def _recover_publications(self, *, agent_id=None, progress=None):
        """Publish retained facts once before any new dispatch is enabled."""
        after = 0
        while True:
            rows = await asyncio.to_thread(self._page, after=after, agent_id=agent_id)
            if not rows:
                return
            for row in rows:
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
            logging.getLogger(__name__).error(
                "Embedded runtime containment: type=%s code=%s stage=%s",
                type(error).__name__, getattr(error, "code", None), getattr(error, "stage", None))
        self._stopping.set()
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
        task.add_done_callback(self.workers.discard)
        task.add_done_callback(lambda done: self.worker_agents.pop(done, None))

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
        try:
            await self._execute(frame)
        except Exception as error:
            # Preserve uncertain work, but contain only its known subject.
            try:
                await self.agents.fail(frame['agent_id'], error)
            except Exception as shared_error:
                if self.failure is None:
                    self.failure = shared_error
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
                    auth_refs=executor.local_launch.auth_refs,
                    harness_settings=validate_harness_settings(
                        payload['adapter_id'], payload.get('harness_settings', {}))),context)
                epoch = "stream_" + secrets.token_hex(16)
                options = dict(prepared=prepared,stream_epoch=epoch)
            elif action in ("approval.decide", "input.provide"):
                native_operation = r4_native_decision_operation(frame)
                options = dict(applied_operation=native_operation)
            binding = prepare_r4_receipt_binding(frame, context, **options)
            await asyncio.to_thread(self._bind, frame, binding, options.get("stream_epoch"))
            await asyncio.to_thread(self.verify)
            if action == "runtime.open":
                try:
                    receipt = await runtime.open(OpenOperation(frame["operation_id"],key,epoch,prepared),context)
                except CoreError as error:
                    # Only a durable Core no-spawn receipt can localize this
                    # refusal. An exception flag alone is not release proof.
                    if (error.code != 'PROFILE_DRIFT' or not error.retry_safe
                            or error.possible_effect):
                        raise
                    receipt = await self.host.historical_receipt(session_id=key,
                        key=OperationKey(frame['server_id'], frame['executor_id'], frame['operation_id']))
                    if (receipt is None or receipt.stage != 'FAILED'
                            or receipt.possible_effect or not receipt.retry_safe
                            or receipt.error_code != error.code
                            or receipt.operation_id != frame['operation_id']):
                        raise
                    await self._publish(binding, receipt)
                    report = await runtime.shutdown(ShutdownPolicy(0, 0))
                    if ('unknown' in report.session_outcomes.values() or any(
                            facts['process_state'] != 'STOPPED' or facts['release_pending']
                            for facts in runtime.shutdown_resources().values())):
                        raise CoreError('RECONCILIATION_REQUIRED', 'embedded_session_containment')
                    if not await self.host.close_native_actions(
                            executor_id=self.channel.executor_id, session_id=key, timeout_seconds=5):
                        raise CoreError('RECONCILIATION_REQUIRED', 'embedded_native_action_containment')
                    await self.events.recover(agent_id=frame["agent_id"])
                    from .embedded_reconciliation import EmbeddedReconciliation
                    await EmbeddedReconciliation(self).release_session(key, failed_open=True)
                    await self.tools.release_session(key)
                    self.sessions.pop(key, None)
                    return
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
            await self._publish(binding, receipt)
            if action == "runtime.close" and receipt.stage == "SUCCEEDED":
                await self.tools.release_session(key)
                self.sessions.pop(key, None)

    async def _command_receipt(self, frame, invoke):
        try:
            return await invoke()
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
            changed = await asyncio.to_thread(persist)
            if changed and self.deps.runtime_dispatcher is not None:
                self.deps.runtime_dispatcher.wake()

    def _page(self, *, after=None, agent_id=None):
        with self.factory.unit_of_work(write=False) as uow:
            self.verify(uow=uow)
            rows = uow.connection.execute("SELECT rowid,* FROM execution_local_publications "
                "WHERE server_id=? AND executor_id=? AND terminal=0 AND rowid>? "
                "AND (? IS NULL OR operation_id IN (SELECT operation_id FROM execution_operations WHERE server_id=? AND executor_id=? AND subject_agent_id=?)) ORDER BY rowid LIMIT 128",
                (self.channel.server_id,self.channel.executor_id,self._after if after is None else after,
                 agent_id,self.channel.server_id,self.channel.executor_id,agent_id)).fetchall()
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
                # Expired/revoked session authority is an expected containment
                # boundary, not a failure of every runtime on this executor.
                expected = (isinstance(error, CoreError) and error.code in {
                    'AGENT_REVOKED', 'SESSION_UNKNOWN', 'STALE_GENERATION'}) or (
                    isinstance(error, OktoNexusError) and error.code in {
                        ErrorCode.CONFLICT, ErrorCode.PERMISSION_DENIED})
                if expected:
                    try:
                        await asyncio.to_thread(self.verify)
                        runtime = await session['executor']._runtime()
                        report = await runtime.shutdown(ShutdownPolicy(5, 5))
                        if ('unknown' in report.session_outcomes.values() or any(
                                facts['process_state'] != 'STOPPED' or facts['release_pending']
                                for facts in runtime.shutdown_resources().values())):
                            raise CoreError('RECONCILIATION_REQUIRED', 'embedded_session_containment')
                        if not await self.host.close_native_actions(
                                executor_id=self.channel.executor_id, session_id=session_id, timeout_seconds=5):
                            raise CoreError('RECONCILIATION_REQUIRED', 'embedded_native_action_containment')
                        await self.events.recover(agent_id=session['scope']['agent_id'])
                        from .embedded_reconciliation import EmbeddedReconciliation
                        await EmbeddedReconciliation(self).release_session(session_id)
                        self.sessions.pop(session_id, None)
                        return
                    except Exception as containment_error:
                        error = containment_error
                try:
                    await self.agents.fail(session['scope']['agent_id'], error)
                except Exception as shared_error:
                    if self.failure is None:
                        self.failure = shared_error
                    await self.failed()

    async def _maintain(self):
        from nexus_connector_core import DEFAULT_RUNTIME_AUTOMATION
        pending_at=0
        try:
            while not self._stopping.is_set():
                if time.monotonic()>=pending_at:
                    from ..application.runtime_recovery import drain_pending
                    await asyncio.to_thread(drain_pending,self.deps)
                    pending_at=time.monotonic()+DEFAULT_RUNTIME_AUTOMATION.message_interval
                for session_id, session in list(self.sessions.items()):
                    if (session["scope"]["agent_id"] not in self.agents.blocked and session["renew_at"] is not None and time.monotonic() >= session["renew_at"]
                            and (session.get("renew_task") is None or session["renew_task"].done())):
                        task = asyncio.create_task(self._renew_owned(session_id, session), name="embedded-renew-" + session_id)
                        session["renew_task"] = task
                        self.renewals.add(task)
                        task.add_done_callback(self.renewals.discard)
                await self.agents.tick()
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

    async def _close(self):
        self._stopping.set()
        # Native containment must start before any database or publication
        # wait. Keep the journals alive for the producers joined below.
        if self.pump is not None:
            self.pump._stopping.set()
        if (self._containment_task is not None and self._containment_task.done()
                and (self._containment_task.cancelled()
                     or self._containment_task.exception() is not None)):
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
            # All dispatch/publication producers have returned. The host now
            # joins history readers and closes only resolved Core resources.
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

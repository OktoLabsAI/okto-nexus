"""Reset history only after draining runtimes; restart their owned services."""
import asyncio
import time

from ..errors import ErrorCode, OktoNexusError


async def _close_remote_sessions(app, context):
    from .execution_authority import build_execution_access
    from ..application.execution_intents import resolve_execution_intent
    from ..application.execution_admission import submit_execution_operation
    deps = app.state.deps
    access = build_execution_access(deps)
    submitted = set()
    until = time.monotonic() + 30
    while True:
        with deps.connection_factory.unit_of_work(write=False) as uow:
            rows = [dict(r) for r in uow.connection.execute(
                'SELECT s.*,e.agent_id FROM execution_sessions s '
                'JOIN execution_executors x USING(server_id,executor_id) '
                'JOIN execution_bindings b USING(server_id,executor_id,binding_id) '
                'JOIN agent_endpoints e ON e.endpoint_id=b.endpoint_id '
                "WHERE x.kind='remote' AND s.lifecycle_state<>'CLOSED'")]
        if not rows:
            return
        for row in rows:
            if row['session_id'] in submitted or row['lifecycle_state'] != 'READY':
                continue
            def close(row=row):
                common = dict(actor_agent_id=context.actor_agent_id or 'operator', access=access,
                    remote_ready=True, fresh_publications=app.state.inventory_fresh_publications)
                resolution = resolve_execution_intent(deps.connection_factory, context=context,
                    request=dict(client_intent_id='database-reset-close:' + row['session_id'],
                        intent='runtime.close', agent_id=row['agent_id'], session_id=row['session_id'],
                        binding_id=row['binding_id'], workspace_binding_id=row['workspace_binding_id']), **common)
                if not resolution['can_submit']:
                    return False
                submit_execution_operation(deps.connection_factory, context=context,
                    request={key: resolution[key] for key in ('client_intent_id', 'operation_id', 'resolution_revision', 'intent_hash')}, **common)
                return True
            if await asyncio.to_thread(close):
                submitted.add(row['session_id'])
        if time.monotonic() >= until:
            raise OktoNexusError(ErrorCode.CONFLICT,
                'Reset could not confirm that remote executions stopped. No history or connection configuration was deleted.', {})
        await asyncio.sleep(.1)


async def _run(app, *, keep_agents, reset, context):
    from .server_runtime import start_runtime_services
    deps = app.state.deps
    coordinator = getattr(app.state, 'runtime_shutdown', None)
    dispatcher = getattr(deps, 'runtime_dispatcher', None)
    embedded = getattr(app.state, 'embedded_dispatch_owner', None)
    native_factory = getattr(embedded, 'native_factory', None)
    drained = False
    deps.runtime_admission_fence.close()
    if dispatcher is not None:
        dispatcher.quiesce()
    try:
        app.state.database_reset_phase = 'stopping_executions'
        await _close_remote_sessions(app, context)
        if coordinator is not None:
            # This is a runtime restart within the same HTTP server.
            coordinator.on_drained = None
            await coordinator.request(timeout_seconds=2)
            await coordinator.wait()
            drained = True
        app.state.database_reset_phase = 'clearing_history'
        counts, vacuumed = await asyncio.to_thread(reset)
        if not keep_agents:
            app.state.auth.invalidate_all()
        return dict(deleted=counts, kept_agents=keep_agents, vacuumed=vacuumed, pending=False)
    finally:
        if drained:
            app.state.database_reset_phase = 'reconnecting'
            deps.runtime_dispatcher = None
            deps.harness_supervisor = None
            deps.runtime_admission_fence.reopen_after_reset()
            try:
                await start_runtime_services(app, native_factory=native_factory)
            except BaseException:
                deps.runtime_admission_fence.close()
                raise
        elif coordinator is None or coordinator.status()['state'] == 'RUNNING':
            deps.runtime_admission_fence.reopen_after_reset()
            if dispatcher is not None:
                dispatcher.resume_after_cancelled_reset()
        app.state.database_reset_phase = 'finished'


async def request_reset(app, *, keep_agents, reset, context):
    task = getattr(app.state, 'database_reset_task', None)
    if task is not None and not task.done():
        if app.state.database_reset_keep_agents != keep_agents:
            raise OktoNexusError(ErrorCode.CONFLICT, 'A reset with different options is already in progress.', {})
    else:
        owner = getattr(app.state, 'runtime_shutdown', None)
        if owner is not None and owner.status()['state'] != 'RUNNING':
            raise OktoNexusError(ErrorCode.CONFLICT, 'Server shutdown is already in progress.', {})
        app.state.database_reset_keep_agents = keep_agents
        task = asyncio.create_task(_run(app, keep_agents=keep_agents, reset=reset, context=context), name='database-reset')
        # A client disconnect cannot cancel the owned reset/reconnection task.
        task.add_done_callback(lambda done: done.exception() if not done.cancelled() else None)
        app.state.database_reset_task = task
    await asyncio.wait((task,), timeout=1)
    return reset_status(app)


def reset_status(app):
    task = getattr(app.state, 'database_reset_task', None)
    if task is None:
        return dict(pending=False, phase='idle')
    if task.done():
        return task.result()
    return dict(pending=True, phase=getattr(app.state, 'database_reset_phase', 'stopping_executions'))

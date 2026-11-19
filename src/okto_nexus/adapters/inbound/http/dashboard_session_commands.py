"""Read the versioned, exact-session catalogue of dashboard commands."""

from dataclasses import asdict
from re import fullmatch

import anyio
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ....adapters.outbound.sqlite.execution_agent_revisions import (
    current_agent_revisions,
)
from ....adapters.outbound.sqlite.session_interaction_queue_controls import (
    has_unresolved_interrupt,
    is_input_queue_paused,
)
from ....application.execution_operator_authority import require_operator_request
from ....application.execution_session_views import read_execution_session
from ....application.session_interaction_authority import require_session_input_grant
from ....application.session_interaction_promotion import steer_human_input
from ....application.session_interaction_targets import (
    active_claude_operation,
    active_interrupt_target,
    steer_effect_revisions,
)
from ....bootstrap.execution_authority import build_execution_access
from ....domain.attention import digest
from ....errors import ErrorCode, OktoNexusError
from .dashboard_session_input import (
    _HEADERS,
    _error,
    _exact_view,
    _read_scope,
    _runtime_error,
    enqueue_input_response,
    interrupt_response,
)
from .dashboard_session_steer import steer_response
from .identity_ctx import runtime_request_context
from .session_interaction_contract import (
    CommandDescriptor,
    CommandHandler,
    CommandId,
    CommandState,
    EnqueueSessionCommand,
    InterruptSessionCommand,
    ReadSessionCommand,
    SessionCommand,
    SessionCommandCatalog,
)


def _action(command: CommandId, label: str, effect: str, handler: CommandHandler,
            state: CommandState = 'supported', reason: str | None = None):
    writes = handler in ('enqueue', 'review_steer', 'review_interrupt')
    return CommandDescriptor(command_id=command, label=label, effect=effect, source='nexus',
        surface='dashboard', handler=handler, arguments=('message',) if handler in ('enqueue', 'review_steer') else (),
        state=state, reason=reason, requires_confirmation=writes)


def _unavailable(command: CommandId, label: str, effect: str, state: CommandState, reason: str):
    native = state == 'native_only'
    return CommandDescriptor(command_id=command, label=label, effect=effect,
        source='native' if native else 'nexus', surface='native_terminal' if native else 'dashboard',
        handler=None, state=state, reason=reason, requires_confirmation=False)


_READ_ACTIONS = (
    _action('help', 'Session commands', 'Show actions and their availability in this session.', 'catalog'),
    _action('status', 'Session status', 'Show the current session status.', 'session_status'),
)

_UNQUALIFIED = (
    _unavailable('compact', 'Compact context', 'Summarize the conversation context.', 'unqualified',
                 'Context compaction has no qualified dashboard handler.'),
    _unavailable('model', 'Choose model', 'Change the model for subsequent turns.', 'unqualified',
                 'Model changes have no qualified dashboard handler.'),
    _unavailable('effort', 'Choose effort', 'Change reasoning effort for subsequent turns.', 'unqualified',
                 'Effort changes have no qualified dashboard handler.'),
    _unavailable('export', 'Export session', 'Save a copy of the conversation.', 'unsupported',
                 'Session export is unavailable in the dashboard.'),
    _unavailable('fork', 'Fork session', 'Create another conversation from the current one.', 'unqualified',
                 'Forking has no qualified dashboard handler.'),
    _unavailable('clear', 'Clear context', 'Start with an empty conversation context.', 'unsupported',
                 'Clearing the context is unavailable in the dashboard.'),
)


def _availability(check):
    try:
        return 'supported', None, check()
    except OktoNexusError as error:
        if error.code == ErrorCode.PERMISSION_DENIED:
            return 'denied_by_policy', 'The current session policy or authorization prevents this action.', None
        if error.code in (ErrorCode.CONFLICT, ErrorCode.NOT_FOUND):
            return 'disabled_for_state', 'The session is currently unavailable for this action.', None
        raise


def _productive_availability(uow, *, factory, access, scope, context, revision):
    if revision is None:
        return 'unqualified', 'This session has no current qualified input capability.', None
    return _availability(lambda: require_session_input_grant(
        uow, factory=factory, access=access, scope=scope, context=context))


def read_command_catalog(uow, *, factory, access, scope, document, context, options, remote_control_host=None):
    exact = _exact_view(factory, uow, context=context, access=access, document=document, scope=scope)
    conn = uow.connection
    endpoint = conn.execute("""
        SELECT e.adapter_id, CASE WHEN json_valid(s.native_launch_build_json)
            THEN json_extract(s.native_launch_build_json, '$.version') END AS native_launch_version
        FROM execution_sessions s
        JOIN execution_bindings b USING(server_id, executor_id, binding_id)
        JOIN agent_endpoints e ON e.endpoint_id=b.endpoint_id
        WHERE s.server_id=:server_id AND s.executor_id=:executor_id AND s.session_id=:session_id
    """, asdict(scope.session)).fetchone()
    adapter = endpoint['adapter_id'] if endpoint else None
    launch_version = endpoint['native_launch_version'] if endpoint else None
    if not isinstance(launch_version, str) or not fullmatch(r'[0-9][0-9A-Za-z.+_-]{0,63}', launch_version):
        launch_version = None
    revision_for = options.get('session_input_capability_revision')
    revision = revision_for(uow, scope) if revision_for else None
    state, reason, grant = _productive_availability(
        uow, factory=factory, access=access, scope=scope, context=context, revision=revision)
    if revision_for is None:
        state, reason = 'denied_by_policy', 'Session interaction is disabled on this server.'
    send = _action('send', 'Send for next turn', 'Queue a message for the next eligible turn.', 'enqueue', state, reason)

    turn = (active_interrupt_target(uow, scope, current_next_turn_revision=revision_for,
                                    remote_control_host=remote_control_host)
            if adapter in ('codex_app_server', 'pi_rpc', 'claude_stream') and revision is not None else None)
    interrupt_state, interrupt_reason = state, reason
    if adapter in ('codex_app_server', 'pi_rpc', 'claude_stream') and revision is not None:
        if has_unresolved_interrupt(conn, scope.session):
            interrupt_state, interrupt_reason = 'disabled_for_state', 'An interruption is already pending.'
        else:
            if turn is None:
                interrupt_state, interrupt_reason = 'disabled_for_state', 'There is no confirmed active turn.'
            else:
                interrupt_state, interrupt_reason, _ = _availability(lambda: require_operator_request(
                    uow, actor='operator', subject=scope.agent_id, access=access, context=context,
                    binding_id=scope.binding_id, action='turn.interrupt'))
    elif revision_for is not None:
        interrupt_state, interrupt_reason = 'unqualified', 'Exact turn interruption is unavailable for this integration.'
    interrupt = _action('interrupt', 'Stop current turn', 'Interrupt the current turn and pause the message queue.',
                        'review_interrupt', interrupt_state, interrupt_reason)

    steer_target = turn
    if adapter == 'claude_stream' and revision is not None:
        steer_target = active_claude_operation(uow, scope, current_next_turn_revision=revision_for,
                                               remote_control_host=remote_control_host)
    steer_revisions = steer_effect_revisions(steer_target) if steer_target is not None else None
    steer_state, steer_reason = state, reason
    if state == 'supported':
        if adapter not in ('codex_app_server', 'pi_rpc', 'claude_stream'):
            steer_state, steer_reason = 'unqualified', 'Reorientation is unavailable for this integration.'
        elif has_unresolved_interrupt(conn, scope.session) or steer_target is None:
            steer_state, steer_reason = 'disabled_for_state', 'There is no confirmed active run available for reorientation.'
        elif steer_revisions is None:
            steer_state, steer_reason = 'unqualified', 'There is no qualified reorientation effect for this turn.'
        elif is_input_queue_paused(conn, scope.session):
            steer_state, steer_reason = 'disabled_for_state', 'Resume the message queue first.'
    description = {
        'pi_rpc': 'Send a message at the next boundary of the confirmed Pi run.',
        'claude_stream': 'Interrupt the confirmed Claude turn, then send the replacement message.',
    }.get(adapter, 'Send a message to the confirmed active turn.')
    steer = _action('steer', 'Reorient current turn', description,
                    'review_steer', steer_state, steer_reason)

    resume = _unavailable('resume', 'Resume saved session', 'Open a saved conversation.',
                          'native_only' if adapter == 'codex_app_server' else 'unqualified',
                          'Use a compatible Codex terminal. Check whether your terminal supports resume.'
                          if adapter == 'codex_app_server' else 'Resuming saved sessions has no qualified dashboard handler.')
    items = (*_READ_ACTIONS, send, steer, interrupt, *_UNQUALIFIED, resume)
    _, agent_revisions, _ = current_agent_revisions(
        factory, agent_id=scope.agent_id, uow=uow, persist=False, require_active=False)
    catalog_facts = {'version': 1, 'scope': exact, 'adapter': adapter, 'input': revision,
        'target': turn.revision if turn else None, 'steer': steer_revisions, 'grant': grant,
        'agent_revisions': asdict(agent_revisions), 'items': [item.model_dump(mode='json') for item in items]}
    if launch_version is not None:
        catalog_facts['native_launch_version'] = launch_version
    catalog_revision = 'sha256:' + digest(catalog_facts)
    return SessionCommandCatalog(scope=document, session_owner_generation=scope.generation.value,
        capability_revision=catalog_revision, adapter_id=adapter, native_launch_version=launch_version, items=items)


def build_router():
    router = APIRouter(prefix='/runtime/sessions/{session_id}')

    @router.get('/commands')
    async def commands(session_id: str, request: Request):
        if not getattr(request.state, 'operator_session', False):
            return _error(401, 'AUTH_FAILED', 'Sign in as the human operator to view session commands.')
        try:
            document, scope = _read_scope(request, session_id)
        except ValueError:
            return _error(422, 'VALIDATION_ERROR', 'An exact session scope is required.')
        state = request.app.state
        factory = state.deps.connection_factory
        access = build_execution_access(state.deps)
        context = runtime_request_context()
        options = getattr(state, 'session_input_dispatch_options', {})

        def read():
            with factory.unit_of_work(write=False) as uow:
                catalog = read_command_catalog(uow, factory=factory, access=access, scope=scope, document=document,
                    context=context, options=options, remote_control_host=state.deps.runtime_availability.current_host)
                return catalog.model_dump(mode='json')

        try:
            return JSONResponse(await anyio.to_thread.run_sync(read), headers=_HEADERS)
        except OktoNexusError as error:
            return _runtime_error(error)

    async def execute_command_for(session_id, body, request, surface):
        if not getattr(request.state, 'operator_session', False):
            return _error(401, 'AUTH_FAILED', 'Sign in as the human operator to use session commands.')
        if body.scope.session_id != session_id or request.query_params:
            return _error(422, 'VALIDATION_ERROR', 'The command must use the exact session scope.')
        state = request.app.state
        factory = state.deps.connection_factory
        access = build_execution_access(state.deps)
        context = runtime_request_context()
        options = getattr(state, 'session_input_dispatch_options', {})
        scope = body.input_scope()

        def verify_command(uow):
            catalog = read_command_catalog(uow, factory=factory, access=access, scope=scope, document=body.scope,
                context=context, options=options, remote_control_host=state.deps.runtime_availability.current_host)
            if catalog.capability_revision != body.catalog_revision:
                raise OktoNexusError(ErrorCode.CONFLICT, 'Session commands changed. Review the current action again.', {})
            action = next(item for item in catalog.items if item.command_id == body.command)
            if action.state != 'supported':
                code = ErrorCode.PERMISSION_DENIED if action.state == 'denied_by_policy' else ErrorCode.CONFLICT
                raise OktoNexusError(code, action.reason or 'The session command is unavailable.', {})
            return catalog

        if isinstance(body, EnqueueSessionCommand):
            return await enqueue_input_response(session_id, body, request, verify_command=verify_command,
                                                surface=surface)
        if isinstance(body, InterruptSessionCommand):
            return await interrupt_response(session_id, body, request, verify_command=verify_command,
                                            surface=surface)
        if not isinstance(body, ReadSessionCommand):
            return await steer_response(session_id, body, request, steer_human_input, {
                'client_intent_id': body.client_intent_id, 'text': body.content[0].text, 'verify_command': verify_command,
            }, surface=surface)

        def read():
            with factory.unit_of_work(write=False) as uow:
                catalog = verify_command(uow)
                if body.command == 'help':
                    return catalog.model_dump(mode='json')
                session = read_execution_session(factory, server_id=scope.session.server_id,
                    executor_id=scope.session.executor_id, session_id=session_id, context=context, access=access, _uow=uow)
                return {**{key: session[key] for key in ('lifecycle_state', 'lease_state', 'control_available')},
                        'scope': body.scope.model_dump(), 'session_owner_generation': scope.generation.value}

        try:
            return JSONResponse(await anyio.to_thread.run_sync(read), headers=_HEADERS)
        except OktoNexusError as error:
            return _runtime_error(error)

    @router.post('/commands:execute')
    async def execute_command(session_id: str, body: SessionCommand, request: Request):
        return await execute_command_for(session_id, body, request, 'web')

    @router.post('/terminal/commands:execute')
    async def execute_terminal_command(session_id: str, body: SessionCommand, request: Request):
        return await execute_command_for(session_id, body, request, 'nexus_cli')

    return router

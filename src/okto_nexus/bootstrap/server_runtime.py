"""Start the serve-owned runtime services, including after an operator reset."""
from functools import partial

import anyio

async def start_runtime_services(app, *, native_factory=None):
    from .runtime_host import EmbeddedRuntimeHost
    from .server_shutdown import ServerShutdownCoordinator
    from .runtime_boot_owner import RuntimeBootOwner
    from .local_codex_presentations import publish_local_codex_presentations
    from .local_claude_presentations import publish_local_claude_presentations
    from .local_pi_presentations import publish_local_pi_presentations
    from ..adapters.inbound.http.dashboard_session_presentations import (
        LocalClaudePresentations, LocalPiPresentations, RemoteCodexPresentations,
    )
    from ..application.session_attachment_broker import SessionAttachmentBroker
    from ..adapters.outbound.sqlite.runtime_outbox_repo import SqliteRuntimeOutboxRepo
    from ..adapters.inbound.mcp.tools.harness import build_dispatcher, run_runtime_boot
    from ..application.connection_test import ConnectionTests
    from .handoff_runtime_scheduler import build_handoff_notice_maintenance, build_handoff_runtime_scheduler
    from ..application.handoff_runtime_service import HandoffRuntimeService
    from ..application.session_interaction_capability import next_turn_revision
    from ..application.session_interaction_scheduler import SessionInputScheduler
    from ..application.session_interaction_targets import interrupt_revision, steer_revisions
    from ..adapters.outbound.execution.core_inventory import protocol_info
    from .execution_authority import build_execution_access
    deps = app.state.deps
    previous_supervisor = getattr(app.state, 'embedded_runtime_supervisor', None)
    if previous_supervisor is not None and not previous_supervisor.drained:
        raise RuntimeError('The previous embedded supervisor has not drained.')
    previous_boot = getattr(app.state, 'runtime_boot_owner', None)
    if previous_boot is not None and not previous_boot.drained:
        raise RuntimeError('The previous runtime boot owner has not drained.')
    previous_notices = getattr(app.state, 'handoff_notice_maintenance', None)
    if previous_notices is not None and not previous_notices.drained:
        raise RuntimeError('The previous handoff notice owner has not drained.')
    previous_handoffs = getattr(app.state, 'handoff_runtime_service', None)
    if previous_handoffs is not None and not previous_handoffs.drained:
        raise RuntimeError('The previous handoff runtime owner has not drained.')
    app.state.handoff_runtime_service = None
    notices = build_handoff_notice_maintenance(deps)
    app.state.handoff_notice_maintenance = notices
    notices.start()
    with deps.connection_factory.unit_of_work(write=False) as uow:
        history = SqliteRuntimeOutboxRepo().has_history(uow)
        handoff_history = uow.connection.execute(
            'SELECT 1 FROM handoff_runtime_attempts WHERE active=1 LIMIT 1').fetchone() is not None
        input_history = uow.connection.execute("""
            SELECT 1 FROM session_interaction_capacity_attempts WHERE state='PREPARED' AND resolved_at IS NULL
            UNION ALL
            SELECT 1 FROM session_interaction_inputs
            WHERE capacity_state IN ('WAITING_CONSUMPTION','NEEDS_RECONCILIATION')
               OR (capacity_state='CONSUMED' AND status IN ('DISPATCHING','REFUSED_BEFORE_SEND'))
            LIMIT 1
        """).fetchone() is not None
    acquisition_enabled = deps.config.runtime_handoff_auto_claim_enabled and deps.config.feature_harness_integrations
    scheduling = acquisition_enabled or handoff_history
    input_enabled = deps.config.runtime_session_interaction_enabled and deps.config.feature_harness_integrations
    input_scheduling = input_enabled or input_history
    capacity_enabled = scheduling or input_scheduling
    if capacity_enabled:
        deps.runtime_availability.enabled = True
    input_revision = partial(next_turn_revision, availability=deps.runtime_availability,
                             fresh_publications=app.state.inventory_fresh_publications)
    authority_fence = app.state.operator_auth.authority_fence
    app.state.session_input_dispatch_options = {
        'session_input_authority_fence': authority_fence,
        'session_input_capability_revision': input_revision,
        'session_interrupt_capability_revision': partial(interrupt_revision, current_next_turn_revision=input_revision,
            remote_control_host=deps.runtime_availability.current_host),
        'session_steer_revisions': partial(steer_revisions, current_next_turn_revision=input_revision,
            remote_control_host=deps.runtime_availability.current_host),
    } if input_enabled else {}
    remote_codex = app.state.remote_codex_presentation
    remote_next_turn = input_revision if input_enabled else None
    app.state.remote_codex_presentations = RemoteCodexPresentations(
        SessionAttachmentBroker(deps.connection_factory, authority_fence=authority_fence,
            current_capability=partial(remote_codex.capability_revision, next_turn_revision=remote_next_turn)),
        remote_codex, build_execution_access(deps), next_turn_revision=remote_next_turn)
    remote_pi = app.state.remote_pi_presentation
    app.state.remote_pi_presentations = LocalPiPresentations(
        SessionAttachmentBroker(deps.connection_factory, authority_fence=authority_fence,
            current_capability=partial(remote_pi.capability_revision, next_turn_revision=remote_next_turn)),
        remote_pi.prove, remote_pi.open_renderer, build_execution_access(deps), remote_next_turn,
        open_editor=remote_pi.open_editor)
    remote_claude = app.state.remote_claude_presentation
    app.state.remote_claude_presentations = LocalClaudePresentations(
        SessionAttachmentBroker(deps.connection_factory, authority_fence=authority_fence,
                                current_capability=remote_claude.capability_revision),
        remote_claude.prove, remote_claude.open_reader) if input_enabled else None
    if deps.config.feature_harness_integrations or history:
        if not await anyio.to_thread.run_sync(build_dispatcher(deps).start):
            raise RuntimeError('Another runtime owner holds this store; serve startup refused.')
    with deps.connection_factory.unit_of_work(write=False) as uow:
        generation = uow.connection.execute('SELECT generation FROM runtime_reset_generation WHERE singleton=1').fetchone()[0]
    journal_dir = 'core-runtime' if generation == 0 else f'core-runtime-reset-{generation}'
    host = EmbeddedRuntimeHost(deps.config.home_dir.resolve() / journal_dir, capacity_enabled=capacity_enabled,
                               pi_presentation_enabled=input_enabled)
    inventory = dispatch = boot = None
    app.state.runtime_boot_owner = None
    app.state.embedded_core_host = host
    if deps.config.feature_harness_integrations:
        from .embedded_inventory import EmbeddedInventoryOwner
        from .embedded_dispatch import EmbeddedDispatchOwner
        from ..application.execution_local_launch import ApprovedLocalLaunch
        inventory = EmbeddedInventoryOwner(deps, app.state.inventory_fresh_publications)
        app.state.embedded_inventory_owner = inventory
        # Claims the generation only. Discovery and its retries are retained
        # by inventory, independently of HTTP and dispatch startup.
        await inventory.start()
        host.local_launch_factory = lambda scope: ApprovedLocalLaunch(inventory, scope)
        dispatch = EmbeddedDispatchOwner(inventory, host,
                                         session_input_dispatch_options=app.state.session_input_dispatch_options)
        dispatch.native_factory = native_factory
        app.state.embedded_dispatch_owner = dispatch
        await dispatch.start()
        boot = RuntimeBootOwner(deps, inventory, run_runtime_boot)
        app.state.runtime_boot_owner = boot
        boot.start()
    publish_local_codex_presentations(app, dispatch)
    publish_local_claude_presentations(app, dispatch)
    publish_local_pi_presentations(app, dispatch)
    handoffs = None
    if scheduling or input_scheduling:
        scheduler = build_handoff_runtime_scheduler(deps, acquisition_enabled=acquisition_enabled) if scheduling else None
        session_inputs = SessionInputScheduler(factory=deps.connection_factory, access=build_execution_access(deps),
            availability=deps.runtime_availability, authority_fence=authority_fence,
            current_capability_revision=input_revision, fresh_publications=app.state.inventory_fresh_publications,
            execution_ready=protocol_info()['remote_execution_ready'], acquisition_enabled=input_enabled,
            interval=deps.config.runtime_idle_interval_ms / 1000) if input_scheduling else None
        handoffs = HandoffRuntimeService(scheduler, session_inputs=session_inputs)
        app.state.handoff_runtime_service = handoffs
        handoffs.start()
    def drained():
        server = getattr(app.state, 'server', None)
        if server is not None:
            server.should_exit = True
    app.state.connection_tests = ConnectionTests(deps)
    async def persist_stop():
        from ..adapters.outbound.service_manager.stop_latch import persist_service_stop
        await anyio.to_thread.run_sync(persist_service_stop, getattr(app.state, 'service_lock', None))
    coordinator = ServerShutdownCoordinator(deps, embedded=dispatch, inventory=inventory,
        host=host, on_drained=drained, connection_tests=app.state.connection_tests,
        runtime_boot=boot,
        handoff_notices=notices,
        handoff_runtime=handoffs,
        persist_stop=persist_stop,
        on_embedded_report=lambda report: setattr(app.state, 'embedded_shutdown_report', report))
    app.state.runtime_shutdown = coordinator
    app.state.embedded_runtime_supervisor = None
    if dispatch is not None:
        from .embedded_supervisor import EmbeddedRuntimeSupervisor
        supervisor = EmbeddedRuntimeSupervisor(app, coordinator)
        app.state.embedded_runtime_supervisor = coordinator.supervisor = supervisor
        supervisor.start()
    return host, inventory, dispatch, coordinator

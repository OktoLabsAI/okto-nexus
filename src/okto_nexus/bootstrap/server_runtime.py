"""Start the serve-owned runtime services, including after an operator reset."""
import anyio


async def start_runtime_services(app, *, native_factory=None):
    from .runtime_host import EmbeddedRuntimeHost
    from .server_shutdown import ServerShutdownCoordinator
    from .runtime_boot_owner import RuntimeBootOwner
    from ..adapters.outbound.sqlite.runtime_outbox_repo import SqliteRuntimeOutboxRepo
    from ..adapters.inbound.mcp.tools.harness import build_dispatcher, run_runtime_boot
    from ..application.connection_test import ConnectionTests
    from .handoff_runtime_scheduler import build_handoff_notice_maintenance, build_handoff_runtime_scheduler
    from ..application.handoff_runtime_service import HandoffRuntimeService
    deps = app.state.deps
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
    acquisition_enabled = deps.config.runtime_handoff_auto_claim_enabled and deps.config.feature_harness_integrations
    scheduling = acquisition_enabled or handoff_history
    if scheduling:
        deps.runtime_availability.enabled = True
    if deps.config.feature_harness_integrations or history:
        if not await anyio.to_thread.run_sync(build_dispatcher(deps).start):
            raise RuntimeError('Another runtime owner holds this store; serve startup refused.')
    with deps.connection_factory.unit_of_work(write=False) as uow:
        generation = uow.connection.execute('SELECT generation FROM runtime_reset_generation WHERE singleton=1').fetchone()[0]
    journal_dir = 'core-runtime' if generation == 0 else f'core-runtime-reset-{generation}'
    host = EmbeddedRuntimeHost(deps.config.home_dir.resolve() / journal_dir, capacity_enabled=scheduling)
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
        dispatch = EmbeddedDispatchOwner(inventory, host)
        dispatch.native_factory = native_factory
        app.state.embedded_dispatch_owner = dispatch
        await dispatch.start()
        boot = RuntimeBootOwner(deps, inventory, run_runtime_boot)
        app.state.runtime_boot_owner = boot
        boot.start()
    handoffs = None
    if scheduling:
        handoffs = HandoffRuntimeService(build_handoff_runtime_scheduler(deps,
            acquisition_enabled=acquisition_enabled))
        app.state.handoff_runtime_service = handoffs
        handoffs.start()
    def drained():
        server = getattr(app.state, 'server', None)
        if server is not None:
            server.should_exit = True
    app.state.connection_tests = ConnectionTests(deps)
    coordinator = ServerShutdownCoordinator(deps, embedded=dispatch, inventory=inventory,
        host=host, on_drained=drained, connection_tests=app.state.connection_tests,
        runtime_boot=boot,
        handoff_notices=notices,
        handoff_runtime=handoffs,
        on_embedded_report=lambda report: setattr(app.state, 'embedded_shutdown_report', report))
    app.state.runtime_shutdown = coordinator
    return host, inventory, dispatch, coordinator

"""Start the serve-owned runtime services, including after an operator reset."""
import anyio


async def start_runtime_services(app, *, native_factory=None):
    from .runtime_host import EmbeddedRuntimeHost
    from .server_shutdown import ServerShutdownCoordinator
    from ..adapters.outbound.sqlite.runtime_outbox_repo import SqliteRuntimeOutboxRepo
    from ..adapters.inbound.mcp.tools.harness import build_dispatcher, run_runtime_boot
    from ..application.connection_test import ConnectionTests
    deps = app.state.deps
    with deps.connection_factory.unit_of_work(write=False) as uow:
        history = SqliteRuntimeOutboxRepo().has_history(uow)
    if deps.config.feature_harness_integrations or history:
        if not await anyio.to_thread.run_sync(build_dispatcher(deps).start):
            raise RuntimeError('Another runtime owner holds this store; serve startup refused.')
    with deps.connection_factory.unit_of_work(write=False) as uow:
        generation = uow.connection.execute('SELECT generation FROM runtime_reset_generation WHERE singleton=1').fetchone()[0]
    journal_dir = 'core-runtime' if generation == 0 else f'core-runtime-reset-{generation}'
    host = EmbeddedRuntimeHost(deps.config.home_dir.resolve() / journal_dir)
    inventory = dispatch = None
    app.state.embedded_core_host = host
    if deps.config.feature_harness_integrations:
        from .embedded_inventory import EmbeddedInventoryOwner
        from .embedded_dispatch import EmbeddedDispatchOwner
        from ..application.execution_local_launch import ApprovedLocalLaunch
        inventory = EmbeddedInventoryOwner(deps, app.state.inventory_fresh_publications)
        app.state.embedded_inventory_owner = inventory
        await inventory.start()
        host.local_launch_factory = lambda scope: ApprovedLocalLaunch(inventory, scope)
        dispatch = EmbeddedDispatchOwner(inventory, host)
        dispatch.native_factory = native_factory
        app.state.embedded_dispatch_owner = dispatch
        await dispatch.start()
        await anyio.to_thread.run_sync(run_runtime_boot, deps)
    def drained():
        server = getattr(app.state, 'server', None)
        if server is not None:
            server.should_exit = True
    app.state.connection_tests = ConnectionTests(deps)
    coordinator = ServerShutdownCoordinator(deps, embedded=dispatch, inventory=inventory,
        host=host, on_drained=drained, connection_tests=app.state.connection_tests,
        on_embedded_report=lambda report: setattr(app.state, 'embedded_shutdown_report', report))
    app.state.runtime_shutdown = coordinator
    return host, inventory, dispatch, coordinator

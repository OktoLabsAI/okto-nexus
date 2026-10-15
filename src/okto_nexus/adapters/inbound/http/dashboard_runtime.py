"""Dashboard adapters for canonical runtime services, with existing UI auth."""
from fastapi import APIRouter


def build_router():
    from .connections_v1 import build_router as connections
    from .runtime_v1 import build_router as runtime
    allowed = {
        'me', 'prepare_binding', 'apply_binding', 'binding_view',
        'agent_executors', 'runtime_options', 'check_local_installation',
        'refresh_inventory', 'publish_realization', 'resolve_intent',
        'intent_view', 'submit_operation', 'operation_view', 'session_list',
        'session_view', 'session_events', 'native_decision', 'native_decision_view',
        'native_input_requests',
        'connection_setup_read', 'connection_setup_test', 'connection_setup_test_read', 'connection_setup_finish',
        'workspace_paths_read',
        'retry_runtime_recovery',
        'runtime_recovery_plan', 'confirm_runtime_stopped',
    }
    router = APIRouter()
    for source in (connections(), runtime()):
        router.routes.extend(route for route in source.routes if route.name in allowed)
    return router

"""Dashboard adapters for canonical runtime services, with existing UI auth."""
from fastapi import APIRouter


def build_router():
    from .connections_v1 import build_router as connections
    from .runtime_v1 import build_router as runtime
    allowed = {
        'me', 'prepare_binding', 'apply_binding', 'binding_view',
        'agent_executors', 'runtime_options', 'check_local_installation',
        'refresh_inventory', 'revalidate_bindings', 'publish_realization', 'resolve_intent',
        'intent_view', 'submit_operation', 'operation_view', 'session_list',
        'session_view', 'session_events', 'native_decision', 'native_decision_view',
        'native_input_requests',
        'project_preset_read',
        'remote_setup_review', 'remote_setup_bootstrap', 'remote_setup_recover', 'remote_setup_materialization',
        'project_preset_update_read',
        'connection_setup_read', 'connection_setup_test', 'connection_setup_test_read', 'connection_setup_finish',
        'connection_setup_commit_read', 'connection_setup_recover',
        'connection_authorization_review', 'connection_authorization_issue',
        'workspace_paths_read',
        'retry_runtime_recovery',
        'runtime_recovery_plan', 'confirm_runtime_stopped',
        'accept_installation_succession', 'list_installation_successions',
    }
    router = APIRouter()
    for source in (connections(), runtime()):
        router.routes.extend(route for route in source.routes if route.name in allowed)
    return router

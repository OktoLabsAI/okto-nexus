"""One read-only import of the frozen PR27 installed normalizer, without startup."""
import inspect
import json

import okto_nexus
from okto_nexus.adapters.inbound.http.runtime_v1 import ConnectionSetupRequest, build_router
from okto_nexus.application.execution_local_realizations import _digest

BODY = dict(client_intent_id='legacy-golden', agent_id='subject',
    baseline=dict(execution_revision=0, runtime_revision=0, defaults_revision=1,
                  binding_revision=None, endpoint_revision=None),
    configuration=dict(format='okto-nexus-connection', version=1, adapter_id='codex_app_server',
        execution_location='remote', runtime_enabled=False, session_policy='per_sender',
        workspace_root='C:/golden-project', workspace_label='Golden', provider_home=None,
        secret_bindings={}, alias='golden', harness_settings={}, automatic_reply=True,
        tool_access='always_allow', authorization=dict(minutes=60, actions=20)))

if __name__ == '__main__':
    route = next(route for route in build_router().routes if route.name == 'connection_setup_finish')
    normalize = inspect.getclosurevars(route.endpoint).nonlocals['setup_request']
    value = normalize(ConnectionSetupRequest.model_validate(BODY))
    print(json.dumps(dict(module=okto_nexus.__file__, request_hash=_digest(value), normalized=value), sort_keys=True))

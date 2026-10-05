"""Test-only compatibility writer, not a supported transport or CLI command."""
import json
import sys


def create(request):
    from okto_nexus.bootstrap.dependencies import bootstrap
    from okto_nexus.adapters.inbound.mcp.tools.messages import build_service
    from okto_nexus.application.auth import AgentKeyAuthService
    from okto_nexus.domain.runtime_context import RuntimeRequestContext
    from okto_nexus.errors import OktoNexusError

    try:
        deps = bootstrap({}, ['--home', request['home'], '--feature-harness-integrations',
                              'true' if request['enabled'] else 'false', '--embedding-mode', 'off'])
        assert getattr(deps, 'runtime_dispatcher', None) is None
        with deps.connection_factory.unit_of_work() as uow:
            actor = AgentKeyAuthService(deps.repos.agents, deps.clock).resolve(uow, request['key'])
        assert actor is not None and actor.agent_id == 'caller'
        result = build_service(deps).create_message(project_root=request['root'],
            from_agent_id=actor.agent_id, subject='writer fence fixture', body='isolated fixture',
            target={'strategy': 'direct', 'agent_id': 'worker'},
            _runtime_context=RuntimeRequestContext(actor.agent_id, 'agent_key',
                                                  credential_binding=actor.api_key_hash))
        assert getattr(deps, 'runtime_dispatcher', None) is None
        return {'ok': True, 'data': result}
    except OktoNexusError as error:
        return {'ok': False, 'error': error.to_error_dict()}


if __name__ == '__main__':
    print(json.dumps(create(json.load(sys.stdin))))

"""One versioned project preset, resolved into the ordinary setup contract."""
from nexus_connector_core.connection_configuration import parse_connection_configuration
from nexus_connector_core.protocol import canonical_json
import hashlib

from ..domain.permissions import PERMISSION_REGISTRY

ORIGIN = {'id': 'project-generalist', 'revision': 1}
CLIENTS = {'codex': 'codex_app_server', 'claude': 'claude_stream', 'pi': 'pi_rpc'}


def identity_defaults():
    """Copy explicit coordination permissions; future capabilities default off."""
    allowed = {'messages.send_direct', 'messages.send_channel', 'handoffs.create', 'handoffs.work',
               'handoffs.cancel', 'artifacts.put', 'events.read', 'identity.update_profile',
               'workspaces.list', 'shared_md.render', 'health.read'}
    flags = {group: {flag: f'{group}.{flag}' in allowed for flag in values}
             for group, values in PERMISSION_REGISTRY.items() if group != 'limits'}
    flags['limits'] = dict(PERMISSION_REGISTRY['limits'], messages_per_minute=60, max_recipients=10)
    result = {'role': 'Project assistant', 'permissions': flags}
    return result | {'defaults_hash': 'sha256:' + hashlib.sha256(canonical_json(result)).hexdigest()}


def configuration(*, adapter_id, project, label, provider_home=None):
    return parse_connection_configuration(dict(
        format='okto-nexus-connection', version=1, adapter_id=adapter_id, execution_location='local',
        runtime_enabled=True, session_policy='per_sender', workspace_root=project, workspace_label=label,
        provider_home=provider_home, secret_bindings={}, alias=label, harness_settings={},
        automatic_reply=True, tool_access='ask', authorization={'minutes': 60, 'actions': 20}))


def effects():
    return [
        'Use the selected agent and project workspace through the existing managed connection.',
        'Allow authorized sessions and eligible Nexus messages for 60 minutes and at most 20 runtime actions.',
        'Keep native tool decisions and existing model/project instructions; no sandbox settings are replaced.',
        'The connection test opens the harness and requests a model response; provider usage may be charged.',
        'Finish saves the connection and execution grant. It does not submit a project task.',
    ]


def read_project_preset(deps, context):
    """Describe the same recommendation used by connect; reading applies nothing."""
    from .connection_setup import require_operator
    from ..bootstrap.execution_authority import build_execution_access
    with deps.connection_factory.unit_of_work(write=False) as uow:
        require_operator(build_execution_access(deps), context, uow)
    defaults = configuration(adapter_id=CLIENTS['codex'], project='', label='Project')
    fields = ('runtime_enabled', 'session_policy', 'harness_settings', 'tool_access', 'authorization')
    return dict(format_version=1, origin=dict(ORIGIN), identity=identity_defaults(),
                configuration={name: defaults[name] for name in fields}, effects=effects())

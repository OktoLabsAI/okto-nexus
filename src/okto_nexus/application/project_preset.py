"""One versioned project preset, resolved into the ordinary setup contract."""
from nexus_connector_core.connection_configuration import parse_connection_configuration

ORIGIN = {'id': 'project-generalist', 'revision': 1}
CLIENTS = {'codex': 'codex_app_server', 'claude': 'claude_stream', 'pi': 'pi_rpc'}


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

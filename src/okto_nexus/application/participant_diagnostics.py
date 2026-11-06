"""Independent participant evidence; passive inspection never repairs setup."""
from .project_diagnostics import ProjectDiagnostics, diagnostic_code
from .terminal_connection import ConnectionError, document_revision
from .terminal_cooperation import TerminalCooperation
from .terminal_participant import TerminalParticipant
from ..adapters.outbound import participant_files
from ..adapters.outbound.participant_client import ParticipantHTTP, participant_key
from ..adapters.outbound.participant_mcp import inspect_mcp
from ..adapters.outbound.cooperation_files import CooperationFiles

LEVELS = ('participant_profile', 'local_service', 'server_reachability', 'participant_authentication',
    'client_configuration', 'credential_store', 'credential_environment', 'client_reload',
    'mcp_negotiation', 'mcp_surface', 'coordination_participation', 'handoff_test', 'work_result')


class ParticipantDiagnostics(ProjectDiagnostics):
    def __init__(self, profile):
        self.profile, self.topology = profile, 'external_participant'
        self.credential_read, self.mcp_checked = False, False
        self.checks = {level: dict(id=level, status='UNKNOWN', code='NOT_CHECKED',
            reason='This level has not been observed.', next_action='Inspect the preceding checks.') for level in LEVELS}
        self.set('local_service', 'NOT_APPLICABLE', 'EXTERNAL_PARTICIPANT',
            'This profile selects an external client and Server origin, not local service ownership.',
            'Use service status on the service host when service lifecycle evidence is needed.')
        self.set('client_reload', 'UNKNOWN', 'CLIENT_RELOAD_NOT_OBSERVED',
            'A valid file does not prove that the external client loaded it.',
            'Restart/reconnect the intended client with the selected project/configuration.')
        self.set('credential_environment', 'UNKNOWN', 'CLIENT_CONTEXT_NOT_OBSERVED',
            'Vault storage and this doctor process do not prove the external client inherited the credential.',
            'Verify how the intended client receives the named reference in its own process.')
        for level, action in (
                ('coordination_participation', 'Run an explicitly consented directed exchange; negotiation alone is not participation.'),
                ('handoff_test', 'Inspect a separately consented canonical handoff claim and result.'),
                ('work_result', 'Inspect the canonical result of separately submitted work.')):
            self.set(level, 'UNKNOWN', 'NOT_OBSERVED', 'This check does not create or inspect productive work.', action)

    def error(self, level, error):
        code = diagnostic_code(getattr(error, 'code', None))
        unknown = code in {'CHECK_UNCONFIRMED', 'SERVER_UNREACHABLE', 'RESPONSE_UNCONFIRMED',
            'PARTICIPANT_VAULT_UNAVAILABLE', 'MCP_NEGOTIATION_UNCONFIRMED', 'MCP_RESPONSE_LIMIT', 'MCP_REQUEST_LIMIT'}
        self.set(level, 'UNKNOWN' if unknown else 'FAIL', code,
            'The check could not establish current evidence.' if unknown else 'Current configuration or authority refused this check.',
            'Inspect the retained setup, selected file, protected credential and Server policy. Doctor made no repair.')

    def result(self):
        value = super().result()
        value['effects'].update(credential_read=self.credential_read, mcp_checked=self.mcp_checked,
            tools_called=False, agent_session_opened=False)
        return value


def inspect_participant(report, home, saved, *, check_server=False, check_mcp=False,
                        check_environment=False, environment=None, timeout=10):
    def no_save(_value):
        raise RuntimeError('Diagnostics cannot save a setup.')
    flow = TerminalParticipant(home, report.profile, no_save)
    review, config = flow.validate(saved)
    report.set('participant_profile', 'PASS', 'PROFILE_READ',
        'The existing participant checkpoint was validated without modification.',
        'Resume the same init profile if setup is incomplete.', setup_run_id=review['setup_run_id'], state=saved['state'])
    _cooperation_history(report, home, saved, review)
    removal = saved.get('removal')
    if removal and removal['stage'] != 'review':
        report.set('participant_profile', 'NOT_APPLICABLE', 'PARTICIPANT_PROFILE_RETIRED',
            'Local removal was approved; this profile cannot be used for init or launch.',
            'Inspect participant remove --plan and resume its checkpoints if incomplete.',
            setup_run_id=review['setup_run_id'], removal_stage=removal['stage'])
        report.set('client_configuration', 'UNKNOWN', 'REMOVAL_RECEIPT_ONLY',
            'The removal receipt is historical evidence, not a current client observation.',
            'Close or reconfigure existing clients explicitly; local cleanup does not revoke their environment or the Server key.')
        return
    if review['file'] is None:
        report.set('client_configuration', 'UNKNOWN', 'MANUAL_CLIENT_CONFIGURATION',
            'This profile exports manual instructions and has no installed client file to inspect.',
            'Inspect the manually configured client on its actual host.')
    else:
        try:
            if saved['state'] == 'done':
                participant_files.current_owned_entry(review['file'], config)
                applied = True
            else:
                applied = participant_files.inspect_file(review['file'], config) == 'applied'
            report.set('client_configuration', 'PASS' if applied else 'UNKNOWN',
                'CLIENT_ENTRY_PRESENT' if applied else 'SETUP_NOT_APPLIED',
                'The reviewed reference-only entry is present.' if applied else 'The reviewed configuration is not applied.',
                'Reconnect the client; file presence does not prove reload or secret resolution.' if applied else
                'Apply/resume the same reviewed init operation; doctor does not write files.')
        except Exception as error:
            report.error('client_configuration', error)
    key = None
    if check_environment:
        report.credential_read = True
        value = (environment or {}).get(config.credential_environment)
        if value is None:
            report.set('credential_environment', 'FAIL', 'CREDENTIAL_ENVIRONMENT_ABSENT',
                'The selected reference is absent in this doctor process.',
                'Use protected credential delivery in the actual client launch context; do not print/export the secret.',
                context='doctor_process', reference=config.credential_environment)
            return
        try:
            key = participant_key(value)
        except ConnectionError as error:
            report.error('credential_environment', error)
            return
        report.set('credential_environment', 'UNKNOWN', 'CREDENTIAL_REFERENCE_PRESENT',
            'A key-shaped value is present only in this doctor process; it has not been authenticated.',
            'Add --check-server to authenticate this exact process environment. External client inheritance remains separate.',
            context='doctor_process', reference=config.credential_environment)
    if not (check_server or check_mcp):
        return
    if key is None:
        try:
            report.credential_read = True
            key = flow.key(saved, None)
            report.set('credential_store', 'PASS', 'PROTECTED_CREDENTIAL_READ',
                'The existing key was read from this setup\'s OS vault entry.',
                'Vault access here does not prove delivery to an external client.')
        except Exception as error:
            report.error('credential_store', error)
            return
    try:
        context = ParticipantHTTP(review['origin'], key, review['context']['agent_id'], timeout=timeout).context(
            review['context']['workspace']['workspace_id'])
        if context['server_id'] != review['context']['server_id']:
            raise ConnectionError('SERVER_CHANGED', 'The selected Server identity changed.')
        report.set('server_reachability', 'PASS', 'SERVER_RESPONSE_CONFIRMED',
            'The selected Server answered the authenticated preparation request.',
            'Server reachability does not prove client reload or productive work.')
        report.set('participant_authentication', 'PASS', 'PARTICIPANT_AUTHENTICATED',
            'The existing credential authenticated the selected identity and workspace under current MCP policy.',
            'Use --check-mcp for initialize and tools/list only; no tools or model are invoked.',
            server_id=context['server_id'], agent_id=context['agent_id'], context='participant_doctor')
        if check_environment:
            report.set('credential_environment', 'PASS', 'DOCTOR_ENVIRONMENT_AUTHENTICATED',
                'This doctor process resolved and authenticated the selected environment reference.',
                'This proves only the doctor environment, not a separate GUI, daemon or harness process.',
                context='doctor_process', reference=config.credential_environment)
    except Exception as error:
        report.error('participant_authentication', error)
        if getattr(error, 'code', None) == 'SERVER_UNREACHABLE':
            report.error('server_reachability', error)
        elif getattr(error, 'code', None) in {'AUTH_FAILED', 'PERMISSION_DENIED', 'SCOPE_MISMATCH', 'NOT_FOUND', 'SERVER_CHANGED'}:
            report.set('server_reachability', 'PASS', 'SERVER_RESPONSE_CONFIRMED',
                'The Server responded, but identity, workspace, policy or installation verification was refused.',
                'Inspect the selected profile and existing authorization; no credential rotation or repair was attempted.')
        return
    if check_mcp:
        report.mcp_checked = True
        try:
            result = inspect_mcp(review['origin'], key, context['agent_id'], timeout=timeout)
            report.set('mcp_negotiation', 'PASS', 'MCP_INITIALIZED',
                'The diagnostic client initialized the authenticated MCP transport.',
                'Negotiation by doctor is not external-client reload, tool use or participation.', **result)
            report.set('mcp_surface', 'PASS' if result['compatible_surface'] else 'FAIL',
                'MCP_SURFACE_COMPATIBLE' if result['compatible_surface'] else 'MCP_SURFACE_INCOMPATIBLE',
                'The listed surface contains the required tool names and basic input fields.' if result['compatible_surface'] else
                'The listed surface lacks required coordination entry points.',
                'Tool visibility does not grant permission to invoke any action; no tool was called.', context='participant_doctor')
        except Exception as error:
            report.error('mcp_negotiation', error)


def _cooperation_history(report, home, saved, review):
    """Show retained evidence without turning a local receipt into a live check."""
    scope = dict(origin=review['origin'], server_id=review['context']['server_id'],
        agent_id=review['context']['agent_id'], workspace_id=review['context']['workspace']['workspace_id'])
    binding = document_revision(dict(setup_run_id=review['setup_run_id'], review_revision=saved['review_revision']))
    try:
        store = CooperationFiles(home / 'terminal/cooperation' / report.profile, scope, binding)
        document = store.load()
        if document is None:
            return
        flow = TerminalCooperation(None, scope, lambda value: None, None, document)
        status = flow.status()
    except Exception:
        for level in ('coordination_participation', 'handoff_test'):
            report.set(level, 'UNKNOWN', 'COOPERATION_HISTORY_UNCONFIRMED',
                'The local cooperation reference could not be validated.',
                'Inspect participant smoke status for the selected profile; doctor does not repair or replay it.')
        return
    for level in ('coordination_participation', 'handoff_test'):
        check = status['checks'][level]
        report.set(level, 'UNKNOWN', 'HISTORICAL_EVIDENCE_ONLY',
            'A local cooperation receipt records an earlier observation; this diagnostic has not rechecked it.',
            'Use participant smoke observe for an explicit current Server read of the same attempt.',
            source='local_receipt', smoke_id=document['smoke_id'], qualification='identities_only',
            last_observed_status=check['status'], observation=check['evidence'],
            request_ids=status['request_ids'])

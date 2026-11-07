"""Pure, bounded Nexus projection for the opt-in diagnostics v1 contract.

This module neither observes state nor authorizes effects. Its input is the
existing typed diagnostic result; legacy rendering remains in the caller.
"""
from collections import Counter
import re

CONTRACT_SHA256 = '06dbbea77eb0870058bc2fe4c9afc81023ea99f857612984321d1f8e6d20c422'

STATUSES = ('PASS', 'FAIL', 'UNKNOWN', 'NOT_APPLICABLE')
TOPOLOGIES = {'local_server', 'remote_operator', 'external_participant', 'unconfirmed'}
SCOPES = {'managed_project', 'participant'}
EFFECT_KEYS = {
    'service_started', 'configuration_applied', 'harness_started',
    'work_submitted', 'grants_issued', 'credential_read', 'mcp_checked',
    'tools_called', 'agent_session_opened',
}
ID_KEYS = {
    'server_id', 'agent_id', 'binding_id', 'workspace_id', 'session_id',
    'setup_run_id', 'smoke_id',
}
STATES = {
    'starting', 'ready', 'stopping', 'stopped', 'failed', 'degraded', 'unknown',
    'review', 'approved', 'check_submitted', 'test_submitted', 'finish', 'done',
    'credential_pending', 'credential_stored', 'file_pending',
    'completed', 'blocked', 'decision_refused', 'submission_unconfirmed',
    'idle', 'needs_input', 'observing',
}
LIFECYCLE_STATES = {'OPEN_PENDING', 'READY', 'CLOSED', 'FAILED', 'CHECK_UNCONFIRMED'}
TECHNICAL_STATES = {
    # Public Core availability values, copied as data: no Core import/probe.
    'NOT_INSTALLED', 'UNSUPPORTED_PLATFORM', 'NOT_PROBED', 'UNQUALIFIED_BUILD',
    'CONTAINMENT_UNAVAILABLE', 'PREPARATION_REQUIRED', 'READY_FOR_RUNTIME',
}
POLICY_REASONS = {
    # execution_runtime_options plus binding and location-policy projections.
    'ADAPTER_UNSUPPORTED', 'AGENT_DISABLED', 'AGENT_RECOVERING', 'AUTHORIZATION_REQUIRED',
    'BINDING_REQUIRED', 'BINDING_SELECTION_REQUIRED', 'BINDING_REVOKED', 'BINDING_DISABLED',
    'BINDING_PENDING_REVIEW', 'BINDING_STALE', 'EXECUTION_LOCATION_RESTRICTED',
    'EXECUTION_UNAVAILABLE', 'EXECUTOR_OFFLINE', 'EXECUTOR_RECOVERING', 'FEATURE_DISABLED',
    'INSTALLATION_REQUIRED', 'INVENTORY_INCOMPATIBLE', 'INVENTORY_STALE',
    'LOCAL_OPERATOR_REQUIRED', 'METHOD_DISABLED', 'OPERATOR_APPROVAL_REQUIRED',
    'OPERATOR_REQUIRED', 'PREPARATION_REQUIRED', 'REALIZATION_SELECTION_REQUIRED',
    'RUNTIME_DRAINING', 'TECHNICAL_NOT_READY', 'WORKSPACE_REQUIRED', 'RUNTIME_DISABLED',
    'LOCAL_INTEGRATION_RESTRICTED', 'CHECK_UNCONFIRMED',
}
TECHNICAL_REASONS = {
    'build_not_qualified', 'no_build_observation', 'selection_required',
    'no_installed_candidate', 'platform_not_implemented', 'containment_unavailable',
    'containment_unverified', 'CHECK_UNCONFIRMED',
}
REQUIRED_TOOLS = {'session_open', 'message_create', 'handoff_create'}
FALLBACK_REASONS = {
    'PASS': 'The named check has current evidence in its declared scope.',
    'FAIL': 'The named check reports a current configuration or authority refusal.',
    'UNKNOWN': 'The named check has insufficient current evidence.',
    'NOT_APPLICABLE': 'The selected topology or role excludes this check.',
}
FALLBACK_ACTION = (
    'Inspect the same selected profile and its existing diagnostic controls; '
    'this report does not repair or retry anything.'
)


def _identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,160}', value):
        return None
    if value.lower().startswith(('nxs_', 'nxobs_', 'ept_', 'nxc_', 'nxp_', 'sk-', 'bearer')):
        return None
    return value


def _enum(value, choices):
    return value if isinstance(value, str) and value in choices else None


def _items(value, validator, maximum):
    if not isinstance(value, list):
        return None
    return [clean for item in value[:maximum] if (clean := validator(item)) is not None]


def _evidence(value):
    if not isinstance(value, dict):
        return {}
    result = {}
    for key in ID_KEYS:
        if (item := _identifier(value.get(key))) is not None:
            result[key] = item
    for key in ('installed_version', 'active_version'):
        item = value.get(key)
        if isinstance(item, str) and re.fullmatch(r'[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}(?:[+.-][A-Za-z0-9.-]{1,40})?', item):
            result[key] = item
    enums = {
        'state': STATES,
        'lifecycle_state': LIFECYCLE_STATES,
        'technical_state': TECHNICAL_STATES,
        'context': {'doctor_process', 'participant_doctor'},
        'source': {'local_receipt'},
        'qualification': {'identities_only'},
        'last_observed_status': set(STATUSES),
        'surface_check': {'names_and_input_fields_v1'},
        'removal_stage': {'review', 'file_pending', 'vault_pending', 'done'},
    }
    for key, choices in enums.items():
        if (item := _enum(value.get(key), choices)) is not None:
            result[key] = item
    reference = value.get('reference')
    if _identifier(reference) is not None and re.fullmatch(r'[A-Z_][A-Z0-9_]{0,159}', reference):
        result['reference'] = reference
    protocol = value.get('protocol_version')
    if isinstance(protocol, str) and re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', protocol):
        result['protocol_version'] = protocol
    count = value.get('tool_count')
    if type(count) is int and 0 <= count <= 512:
        result['tool_count'] = count
    for key in ('compatible_surface', 'agent_session_opened'):
        if type(value.get(key)) is bool:
            result[key] = value[key]
    if type(value.get('tools_called')) is int and value['tools_called'] == 0:
        result['tools_called'] = 0
    for key, validator, maximum in (
        ('operation_ids', _identifier, 100),
        ('policy_reasons', lambda item: _enum(item, POLICY_REASONS), 32),
        ('technical_reasons', lambda item: _enum(item, TECHNICAL_REASONS), 32),
        ('required_tools', lambda item: _enum(item, REQUIRED_TOOLS), 3),
    ):
        if (items := _items(value.get(key), validator, maximum)) is not None:
            result[key] = items
    requests = value.get('request_ids')
    if isinstance(requests, dict):
        result['request_ids'] = {
            key: clean for key in ('message_create', 'handoff_create')
            if (clean := _identifier(requests.get(key))) is not None
        }
    # Nested observation is deliberately excluded: it may contain heterogeneous
    # retained reply/result fields. IDs/status above retain its historical scope.
    return result


def project_report(value, *, scope, explicit_checks=False):
    """Project already-collected facts; perform no additional observation."""
    if not isinstance(scope, str) or scope not in SCOPES or type(explicit_checks) is not bool:
        raise ValueError('Invalid diagnostic projection context.')
    if not isinstance(value, dict) or not isinstance(value.get('checks'), list):
        raise ValueError('Invalid diagnostic report.')
    subject = {'kind': 'profile', 'id': _identifier(value.get('profile')) or 'selected'}
    checks, identities = [], set()
    for row in value['checks']:
        if not isinstance(row, dict) or not isinstance(row.get('id'), str) or row['id'] not in CHECK_IDS:
            raise ValueError('Invalid diagnostic check.')
        status = row.get('status')
        if status not in STATUSES:
            raise ValueError('Invalid diagnostic status.')
        identity = (row['id'], subject['kind'], subject['id'])
        if identity in identities:
            raise ValueError('Duplicate diagnostic check.')
        identities.add(identity)
        code = row.get('code')
        code = code if isinstance(code, str) and code in CODES else 'CHECK_UNCONFIRMED'
        reason, action = row.get('reason'), row.get('next_action')
        evidence = _evidence(row.get('evidence'))
        if row['id'] == 'local_service' and status == 'FAIL' and evidence.get('state') in {'stopped', 'failed'}:
            # Legacy uses SERVICE_UNCONFIRMED or a host-specific reason here.
            # The typed state proves the narrower shared predicate in v1.
            code = 'SERVICE_NOT_READY'
            reason = 'The selected local instance is confirmed stopped or failed.'
        check = dict(
            id=row['id'], subject=dict(subject), status=status, code=code,
            reason=reason if isinstance(reason, str) and reason in REASONS else FALLBACK_REASONS[status],
            next_action=action if isinstance(action, str) and action in ACTIONS else FALLBACK_ACTION,
            severity='error' if status == 'FAIL' else 'info',
        )
        if evidence:
            check['evidence'] = evidence
        checks.append(check)
    counts = Counter(row['status'] for row in checks)
    state = ('failed_checks' if counts['FAIL'] else
             'incomplete' if not checks or counts['UNKNOWN'] else 'checks_passed')
    effects = value.get('effects')
    effects = effects if isinstance(effects, dict) else {}
    return dict(
        schema='okto.diagnostics', format_version=1, component='nexus', scope=scope,
        topology=_enum(value.get('topology'), TOPOLOGIES) or 'unconfirmed',
        mode='explicit_checks' if explicit_checks else 'passive', state=state,
        counts={status: counts[status] for status in STATUSES}, checks=checks,
        effects={key: item for key, item in effects.items()
                 if key in EFFECT_KEYS and type(item) is bool},
    )


CHECK_IDS = frozenset(['client_configuration',
 'client_reload',
 'coordination_participation',
 'credential_environment',
 'credential_store',
 'handoff_test',
 'local_service',
 'managed_connection',
 'managed_session',
 'mcp_negotiation',
 'mcp_surface',
 'operator_authentication',
 'participant_authentication',
 'participant_profile',
 'project_identity',
 'project_profile',
 'provider_login',
 'runtime_eligibility',
 'server_reachability',
 'work_result'])


CODES = frozenset(['AGENT_DISABLED',
 'AUTHENTICATION_NOT_CHECKED',
 'AUTHORIZATION_REQUIRED',
 'AUTH_FAILED',
 'BINDING_APPROVED',
 'BINDING_UNAVAILABLE',
 'CHECK_UNCONFIRMED',
 'CLIENT_CONFIGURATION_NOT_CHECKED',
 'CLIENT_CONTEXT_NOT_OBSERVED',
 'CLIENT_ENTRY_PRESENT',
 'CLIENT_RELOAD_NOT_OBSERVED',
 'COOPERATION_HISTORY_UNCONFIRMED',
 'CREDENTIAL_ENVIRONMENT_ABSENT',
 'CREDENTIAL_REFERENCE_PRESENT',
 'DIAGNOSTIC_LIMIT',
 'DIAGNOSTIC_MUTATION_REFUSED',
 'DOCTOR_ENVIRONMENT_AUTHENTICATED',
 'EXECUTION_LOCATION_RESTRICTED',
 'EXTERNAL_PARTICIPANT',
 'FEATURE_DISABLED',
 'HANDOFF_TEST_NOT_OBSERVED',
 'HISTORICAL_EVIDENCE_ONLY',
 'IDENTITY_CREATION_UNCONFIRMED',
 'INSTALLATION_UNCONFIRMED',
 'LOCAL_READINESS_CONFIRMED',
 'MANAGED_PROJECT_PROFILE',
 'MANUAL_CLIENT_CONFIGURATION',
 'MCP_AUTH_REFUSED',
 'MCP_CLIENT_UPGRADE_REQUIRED',
 'MCP_INITIALIZED',
 'MCP_NEGOTIATION_NOT_OBSERVED',
 'MCP_NEGOTIATION_UNCONFIRMED',
 'MCP_ORIGIN_REFUSED',
 'MCP_REQUEST_LIMIT',
 'MCP_RESPONSE_LIMIT',
 'MCP_RESPONSE_UNCONFIRMED',
 'MCP_SURFACE_COMPATIBLE',
 'MCP_SURFACE_INCOMPATIBLE',
 'METHOD_DISABLED',
 'NOT_CHECKED',
 'NOT_FOUND',
 'NOT_OBSERVED',
 'OPEN_BLOCKED',
 'OPEN_ELIGIBLE',
 'OPERATOR_AUTHENTICATED',
 'OPERATOR_LOGIN_REQUIRED',
 'OPERATOR_REQUIRED',
 'OPERATOR_VAULT_UNAVAILABLE',
 'PARTICIPANT_AUTHENTICATED',
 'PARTICIPANT_NOT_AUTHENTICATED',
 'PARTICIPANT_PROFILE_RETIRED',
 'PARTICIPANT_VAULT_UNAVAILABLE',
 'PARTICIPATION_NOT_OBSERVED',
 'PERMISSION_DENIED',
 'PROFILE_ABSENT',
 'PROFILE_CONFLICT',
 'PROFILE_DRIFT',
 'PROFILE_INVALID',
 'PROFILE_PATH_UNSAFE',
 'PROFILE_READ',
 'PROJECT_IDENTITY_ACTIVE',
 'PROTECTED_CREDENTIAL_READ',
 'PROVIDER_LOGIN_NOT_CHECKED',
 'REMOTE_TOPOLOGY',
 'REMOVAL_RECEIPT_ONLY',
 'RESPONSE_UNCONFIRMED',
 'RUNTIME_DRAINING',
 'RUNTIME_UNCONFIRMED',
 'SCOPE_MISMATCH',
 'SERVER_CHANGED',
 'SERVER_CHECK_NOT_REQUESTED',
 'SERVER_ID_MISMATCH',
 'SERVER_REDIRECT_REFUSED',
 'SERVER_RESPONSE_CONFIRMED',
 'SERVER_UNREACHABLE',
 'SERVER_UPGRADE_REQUIRED',
 'SERVICE_NOT_READY',
 'SERVICE_READY',
 'SERVICE_UNCONFIRMED',
 'SESSION_CONTROL_AVAILABLE',
 'SESSION_NOT_CHECKED',
 'SESSION_NOT_INTERACTIVE',
 'SETUP_INCOMPLETE',
 'SETUP_NOT_APPLIED',
 'WORK_CHECKPOINT_INVALID',
 'WORK_NOT_CHECKED',
 'WORK_NOT_COMPLETED',
 'WORK_RESULT_CONFIRMED'])


REASONS = frozenset(['A key-shaped value is present only in this doctor process; it has not been authenticated.',
 'A local cooperation receipt records an earlier observation; this diagnostic has not rechecked '
 'it.',
 'A stored connection or running service does not prove MCP negotiation.',
 'A valid file does not prove that the external client loaded it.',
 'Current Server checks permit an open request; final admission still rechecks.',
 'Current configuration or authority refused this check.',
 'Current operator authority was verified through the canonical API.',
 'Discovery, a saved login directory and open eligibility do not prove provider authentication.',
 'Local instance ownership, generation, version and readiness are confirmed.',
 'Local removal was approved; this profile cannot be used for init or launch.',
 'No authenticated Server query was requested.',
 'No canonical test handoff claim and result were checked.',
 'No correlated participant session or directed test exchange was checked.',
 'No external client file or launcher environment was validated.',
 'No project checkpoint exists for this selection.',
 'No saved participant profile exists for this selection.',
 'No saved productive result has been checked against its canonical receipt.',
 'No saved session has been checked against the Server.',
 'Operator access does not authenticate the project agent MCP client.',
 'Saved profile metadata does not prove authentication.',
 'The Server responded, but identity, workspace, policy or installation verification was refused.',
 'The Server responded, but operator authentication or compatibility was refused.',
 'The canonical session reports its present control availability.',
 'The check could not establish current evidence.',
 'The current Server projection does not establish permission and technical readiness to open.',
 'The current inventory does not uniquely describe this binding.',
 'The diagnostic client initialized the authenticated MCP transport.',
 'The existing credential authenticated the selected identity and workspace under current MCP '
 'policy.',
 "The existing key was read from this setup's OS vault entry.",
 'The existing participant checkpoint was validated without modification.',
 'The existing project checkpoint was read without modification.',
 'The listed surface contains the required tool names and basic input fields.',
 'The listed surface lacks required coordination entry points.',
 'The local cooperation reference could not be validated.',
 'The removal receipt is historical evidence, not a current client observation.',
 'The retained setup has not committed.',
 'The retained setup has not confirmed its commit.',
 'The reviewed configuration is not applied.',
 'The reviewed reference-only entry is present.',
 'The saved productive operation has a canonical completed result.',
 'The saved project resolves to the canonical binding; execution eligibility is separate.',
 'The saved setup has no confirmed identity-creation receipt.',
 'The saved work is not proven completed; service/session readiness is insufficient.',
 'The selected Server answered the authenticated API request.',
 'The selected Server answered the authenticated preparation request.',
 'The selected canonical identity is active.',
 'The selected configuration or current authority refused this check.',
 'The selected identity is disabled.',
 'The selected local Server answered its identity-bound readiness check.',
 'The selected local instance is confirmed stopped or failed.',
 'The selected local instance is not confirmed ready; no start or repair was attempted.',
 'The selected reference is absent in this doctor process.',
 'This check could not establish the required current evidence.',
 'This check does not create or inspect productive work.',
 'This doctor process resolved and authenticated the selected environment reference.',
 'This level has not been checked.',
 'This level has not been observed.',
 'This profile exports manual instructions and has no installed client file to inspect.',
 'This profile selects a managed connection, not an external client configuration file.',
 'This profile selects an external client and Server origin, not local service ownership.',
 'This profile targets a remote Server; local service state is irrelevant.',
 'Vault storage and this doctor process do not prove the external client inherited the credential.',
 'compatible_surface',
 'is_active',
 'ready'])


ACTIONS = frozenset(['Add --check-server to authenticate this exact process environment. External client inheritance '
 'remains separate.',
 'Apply/resume the same reviewed init operation; doctor does not write files.',
 'Close or reconfigure existing clients explicitly; local cleanup does not revoke their '
 'environment or the Server key.',
 'Complete provider login with the selected harness on its execution host; doctor does not open '
 'it.',
 'Inspect a separately consented canonical handoff claim and result.',
 'Inspect a separately consented test handoff; doctor does not create or claim work.',
 'Inspect existing work with work status.',
 'Inspect participant remove --plan and resume its checkpoints if incomplete.',
 'Inspect participant smoke status for the selected profile; doctor does not repair or replay it.',
 'Inspect service ownership on the Server or Connector host itself.',
 'Inspect the canonical result of separately submitted work.',
 'Inspect the manually configured client on its actual host.',
 'Inspect the preceding checks.',
 'Inspect the retained setup, selected file, protected credential and Server policy. Doctor made '
 'no repair.',
 'Inspect the same work with work status/watch; doctor does not resume, answer or retry it.',
 'Inspect the same work with work status; request new work separately when intended.',
 'Inspect the selected Server/profile and current authorization; no automatic repair was '
 'attempted.',
 'Inspect the selected account/session and Server version; no login was attempted.',
 'Inspect the selected execution host inventory; doctor does not refresh or probe binaries.',
 'Inspect the selected profile and existing authorization; no credential rotation or repair was '
 'attempted.',
 'MCP client authentication remains a separate check.',
 'Negotiation by doctor is not external-client reload, tool use or participation.',
 'Reachability does not prove client participation or completed work.',
 'Reconnect the client; file presence does not prove reload or secret resolution.',
 'Reconnect the intended MCP client and inspect its authenticated negotiation.',
 'Restart/reconnect the intended client with the selected project/configuration.',
 'Resume or inspect the same setup; do not infer that another identity must be created.',
 'Resume the same connect review or pending setup; doctor never applies it.',
 'Resume the same init profile if setup is incomplete.',
 'Review current runtime eligibility before requesting work.',
 'Review the selected client configuration and protected credential delivery on its host.',
 'Run a separately consented coordination check; doctor does not send messages.',
 'Run an explicitly consented directed exchange; negotiation alone is not participation.',
 'Server reachability does not prove client reload or productive work.',
 'The project agent credential and execution authorization remain independent.',
 'This proves only the doctor environment, not a separate GUI, daemon or harness process.',
 'Tool visibility does not grant permission to invoke any action; no tool was called.',
 'Use --check-mcp for initialize and tools/list only; no tools or model are invoked.',
 'Use --check-server to check operator access and project state.',
 'Use connect when ready to review setup. Doctor does not create a profile.',
 'Use doctor --check-server for bounded GET requests.',
 'Use doctor --check-server on the operator client.',
 'Use init --mode participant to review setup. Doctor creates no files.',
 'Use participant smoke observe for an explicit current Server read of the same attempt.',
 'Use protected credential delivery in the actual client launch context; do not print/export the '
 'secret.',
 'Use service status for details and explicitly start or repair the selected instance when '
 'appropriate.',
 'Use service status on the service host when service lifecycle evidence is needed.',
 'Use work authorize for an explicit grant review when AUTHORIZATION_REQUIRED; inspect other '
 'reported blockers.',
 'Use work status to inspect continuity; do not assume native TUI attachment or reboot survival.',
 'Validate additional participant clients independently; their settings were not read.',
 'Validate the existing participant credential through its approved client.',
 'Vault access here does not prove delivery to an external client.',
 'Verify how the intended client receives the named reference in its own process.'])

"""Bounded, read-only project diagnostics over canonical terminal services."""
from collections import Counter
import re
import time
from urllib.parse import quote, urlencode

from .terminal_connection import ConnectionError, PREFIX, TerminalConnection, RemoteTerminalConnection
from .terminal_work import TerminalWork

LEVELS = (
    'project_profile', 'local_service', 'server_reachability', 'operator_authentication',
    'project_identity', 'managed_connection', 'runtime_eligibility', 'provider_login', 'client_configuration',
    'participant_authentication', 'mcp_negotiation', 'coordination_participation',
    'handoff_test', 'managed_session', 'work_result',
)


def diagnostic_code(value):
    # An arbitrary remote error may echo input/credentials. Only expose the
    # established bounded code vocabulary shape, never its raw message/details.
    return value if isinstance(value, str) and re.fullmatch(r'[A-Z][A-Z0-9_]{0,79}', value) else 'CHECK_UNCONFIRMED'


def technical_reason(value):
    # Core technical reasons use a separate lowercase vocabulary. Keep known
    # codes; omit arbitrary platform/backend suffixes and unknown remote text.
    if value in ('build_not_qualified', 'no_build_observation', 'selection_required', 'no_installed_candidate'):
        return value
    if isinstance(value, str) and value.partition(':')[0] in (
            'platform_not_implemented', 'containment_unavailable', 'containment_unverified'):
        return value.partition(':')[0]
    return 'CHECK_UNCONFIRMED'


class ProjectDiagnostics:
    def __init__(self, profile):
        self.profile, self.topology = profile, 'unconfirmed'
        self.checks = {level: dict(id=level, status='UNKNOWN', code='NOT_CHECKED',
            reason='This level has not been checked.', next_action='Inspect the preceding checks.') for level in LEVELS}
        self.set('server_reachability', 'UNKNOWN', 'SERVER_CHECK_NOT_REQUESTED',
            'No authenticated Server query was requested.', 'Use doctor --check-server for bounded GET requests.')
        self.set('operator_authentication', 'UNKNOWN', 'AUTHENTICATION_NOT_CHECKED',
            'Saved profile metadata does not prove authentication.', 'Use doctor --check-server on the operator client.')
        self.set('client_configuration', 'UNKNOWN', 'CLIENT_CONFIGURATION_NOT_CHECKED',
            'No external client file or launcher environment was validated.',
            'Review the selected client configuration and protected credential delivery on its host.')
        self.set('participant_authentication', 'UNKNOWN', 'PARTICIPANT_NOT_AUTHENTICATED',
            'Operator access does not authenticate the project agent MCP client.',
            'Validate the existing participant credential through its approved client.')
        self.set('mcp_negotiation', 'UNKNOWN', 'MCP_NEGOTIATION_NOT_OBSERVED',
            'A stored connection or running service does not prove MCP negotiation.',
            'Reconnect the intended MCP client and inspect its authenticated negotiation.')
        self.set('coordination_participation', 'UNKNOWN', 'PARTICIPATION_NOT_OBSERVED',
            'No correlated participant session or directed test exchange was checked.',
            'Run a separately consented coordination check; doctor does not send messages.')
        self.set('handoff_test', 'UNKNOWN', 'HANDOFF_TEST_NOT_OBSERVED',
            'No canonical test handoff claim and result were checked.',
            'Inspect a separately consented test handoff; doctor does not create or claim work.')
        self.set('provider_login', 'UNKNOWN', 'PROVIDER_LOGIN_NOT_CHECKED',
            'Discovery, a saved login directory and open eligibility do not prove provider authentication.',
            'Complete provider login with the selected harness on its execution host; doctor does not open it.')
        self.set('managed_session', 'UNKNOWN', 'SESSION_NOT_CHECKED',
            'No saved session has been checked against the Server.', 'Inspect existing work with work status.')
        self.set('work_result', 'UNKNOWN', 'WORK_NOT_CHECKED',
            'No saved productive result has been checked against its canonical receipt.',
            'Inspect the same work with work status; request new work separately when intended.')

    def set(self, level, status, code, reason, action, **evidence):
        assert level in self.checks and status in {'PASS', 'FAIL', 'UNKNOWN', 'NOT_APPLICABLE'}
        self.checks[level] = dict(id=level, status=status, code=diagnostic_code(code),
            reason=reason, next_action=action, **({'evidence': evidence} if evidence else {}))

    def error(self, level, error):
        code = diagnostic_code(getattr(error, 'code', None))
        unknown = code in {'CHECK_UNCONFIRMED', 'SERVER_UNREACHABLE', 'RESPONSE_UNCONFIRMED',
                          'DIAGNOSTIC_LIMIT', 'OPERATOR_VAULT_UNAVAILABLE', 'NOT_FOUND'}
        self.set(level, 'UNKNOWN' if unknown else 'FAIL', code,
            'This check could not establish the required current evidence.' if unknown else
            'The selected configuration or current authority refused this check.',
            'Inspect the selected Server/profile and current authorization; no automatic repair was attempted.')

    def result(self):
        counts = Counter(item['status'] for item in self.checks.values())
        return dict(format_version=1, profile=self.profile, topology=self.topology,
            state='failed_checks' if counts['FAIL'] else 'incomplete' if counts['UNKNOWN'] else 'checks_passed',
            checks=list(self.checks.values()), counts={status: counts[status] for status in ('PASS', 'FAIL', 'UNKNOWN', 'NOT_APPLICABLE')},
            effects=dict(service_started=False, configuration_applied=False, harness_started=False,
                         work_submitted=False, grants_issued=False))


class DiagnosticReads:
    """GET only, finite calls/time; response payloads never become the report."""
    def __init__(self, transport, *, timeout=10, max_calls=64, monotonic=time.monotonic):
        self.transport, self.clock, self.deadline = transport, monotonic, monotonic() + timeout
        self.remaining = max_calls

    def __call__(self, method, path, body=None):
        if method != 'GET' or body is not None:
            raise ConnectionError('DIAGNOSTIC_MUTATION_REFUSED', 'Diagnostics only read canonical state.')
        remaining = self.deadline - self.clock()
        if self.remaining <= 0 or remaining <= 0:
            raise ConnectionError('DIAGNOSTIC_LIMIT', 'Diagnostic observation budget ended; no work was cancelled.')
        self.remaining -= 1
        previous = getattr(self.transport, 'timeout', None)
        try:
            if previous is not None:
                self.transport.timeout = min(previous, remaining)
            return self.transport(method, path)
        finally:
            if previous is not None:
                self.transport.timeout = previous


def inspect_project(report, call, document, checkpoint=None):
    """The caller has authenticated the operator; every further operation is GET."""
    level = 'project_identity'
    try:
        me = call('GET', PREFIX + '/connections/me')
        if me['server_id'] != document['server_id']:
            raise ConnectionError('SERVER_ID_MISMATCH', 'Profile belongs to another installation.')
        agent = document['selection']['agent']
        if document['state'] != 'done' and document['selection'].get('create_agent'):
            report.set(level, 'UNKNOWN', 'IDENTITY_CREATION_UNCONFIRMED',
                'The saved setup has no confirmed identity-creation receipt.',
                'Resume or inspect the same setup; do not infer that another identity must be created.')
            report.set('managed_connection', 'UNKNOWN', 'SETUP_INCOMPLETE',
                'The retained setup has not confirmed its commit.',
                'Resume the same connect review or pending setup; doctor never applies it.')
            return
        identity = call('GET', '/api/v1/agents/' + quote(agent, safe=''))['data']
        if identity['agent_id'] != agent:
            raise ConnectionError('PROFILE_DRIFT', 'The Server returned another identity.')
        report.set(level, 'PASS' if identity['is_active'] else 'FAIL',
            'PROJECT_IDENTITY_ACTIVE' if identity['is_active'] else 'AGENT_DISABLED',
            'The selected canonical identity is active.' if identity['is_active'] else 'The selected identity is disabled.',
            'MCP client authentication remains a separate check.', agent_id=agent)
        level = 'managed_connection'
        if document['state'] != 'done':
            report.set(level, 'UNKNOWN', 'SETUP_INCOMPLETE', 'The retained setup has not committed.',
                'Resume the same connect review or pending setup; doctor never applies it.')
            return
        flow_type = RemoteTerminalConnection if document['selection'].get('operator_profile') else TerminalConnection
        observed = flow_type(call, _no_save).observe(document)
        binding = call('GET', PREFIX + '/connections/bindings/' + quote(observed['binding_id'], safe=''))
        if (binding['server_id'] != document['server_id'] or binding['agent_id'] != agent or
                binding['binding_id'] != observed['binding_id'] or binding['workspace_id'] != observed['workspace_id']):
            raise ConnectionError('PROFILE_DRIFT', 'The binding changed scope.')
        report.set(level, 'PASS' if binding['state'] == 'APPROVED' else 'FAIL',
            'BINDING_APPROVED' if binding['state'] == 'APPROVED' else 'BINDING_UNAVAILABLE',
            'The saved project resolves to the canonical binding; execution eligibility is separate.',
            'Review current runtime eligibility before requesting work.', binding_id=binding['binding_id'],
            workspace_id=binding['workspace_id'])
        report.set('client_configuration', 'NOT_APPLICABLE', 'MANAGED_PROJECT_PROFILE',
            'This profile selects a managed connection, not an external client configuration file.',
            'Validate additional participant clients independently; their settings were not read.')
        level = 'runtime_eligibility'
        options = call('GET', PREFIX + '/agents/' + quote(agent, safe='') + '/runtime-options?' +
            urlencode(dict(executor_id=binding['executor_id'], workspace_id=binding['workspace_id'])))
        if options['agent_id'] != agent or options['executor_id'] != binding['executor_id']:
            raise ConnectionError('PROFILE_DRIFT', 'The options changed scope.')
        matches = [row for row in options['options'] if (row.get('binding') or {}).get('binding_id') == binding['binding_id']]
        if len(matches) != 1:
            report.set(level, 'UNKNOWN', 'INSTALLATION_UNCONFIRMED',
                'The current inventory does not uniquely describe this binding.',
                'Inspect the selected execution host inventory; doctor does not refresh or probe binaries.')
        else:
            row = matches[0]
            reasons = [diagnostic_code(item) for item in row['policy_reasons'][:32]]
            failed = any(item in {'AUTHORIZATION_REQUIRED', 'AGENT_DISABLED', 'METHOD_DISABLED',
                'FEATURE_DISABLED', 'RUNTIME_DRAINING', 'EXECUTION_LOCATION_RESTRICTED'} or item.startswith('BINDING_') for item in reasons)
            ready = row['can_start'] is True
            report.set(level, 'PASS' if ready else 'FAIL' if failed else 'UNKNOWN',
                'OPEN_ELIGIBLE' if ready else 'OPEN_BLOCKED' if failed else 'RUNTIME_UNCONFIRMED',
                'Current Server checks permit an open request; final admission still rechecks.' if ready else
                'The current Server projection does not establish permission and technical readiness to open.',
                'Use work authorize for an explicit grant review when AUTHORIZATION_REQUIRED; inspect other reported blockers.',
                policy_reasons=reasons, technical_state=diagnostic_code(row['technical_state']),
                technical_reasons=[technical_reason(item) for item in row['technical_reasons'][:32]])
        if not checkpoint:
            return
        level = 'work_result'
        # Reuse the exact receipt/child-turn correlation from normal observation.
        # GET-only transport and _no_save forbid accidental recovery/submission.
        work = TerminalWork(call, _no_save, document, checkpoint).observe()
        session = work.get('session')
        if session:
            report.set('managed_session', 'PASS' if session['control_available'] else 'UNKNOWN',
                'SESSION_CONTROL_AVAILABLE' if session['control_available'] else 'SESSION_NOT_INTERACTIVE',
                'The canonical session reports its present control availability.',
                'Use work status to inspect continuity; do not assume native TUI attachment or reboot survival.',
                session_id=session['scope']['session_id'], lifecycle_state=diagnostic_code(session['lifecycle_state']))
        productive = [operation for operation in work.get('operations', []) if operation['action'] in {'turn.submit', 'turn.steer'}]
        completed = work['state'] == 'completed' and bool(productive) and all(op['executor_stage'] == 'SUCCEEDED' for op in productive)
        report.set(level, 'PASS' if completed else 'FAIL' if work['state'] in {'failed', 'blocked', 'decision_refused'} else 'UNKNOWN',
            'WORK_RESULT_CONFIRMED' if completed else 'WORK_NOT_COMPLETED',
            'The saved productive operation has a canonical completed result.' if completed else
            'The saved work is not proven completed; service/session readiness is insufficient.',
            'Inspect the same work with work status/watch; doctor does not resume, answer or retry it.',
            state=work['state'], operation_ids=[op['operation_id'] for op in productive])
    except (ConnectionError, KeyError, TypeError, ValueError, AttributeError) as error:
        report.error(level, error)


def _no_save(_):
    raise ConnectionError('DIAGNOSTIC_MUTATION_REFUSED', 'Diagnostics cannot write a project checkpoint.')

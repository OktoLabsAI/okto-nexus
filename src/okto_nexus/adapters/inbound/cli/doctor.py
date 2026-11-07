"""Passive diagnostics; authenticated Server reads require explicit selection."""
import argparse
import json
from pathlib import Path

from ....application.project_diagnostics import DiagnosticReads, ProjectDiagnostics, inspect_project, diagnostic_code
from ....application.terminal_connection import ConnectionError, PREFIX
from ....errors import OktoNexusError
from ...outbound.operator_client import OperatorProfile
from ...outbound.service_manager.context import read_json
from ...outbound.terminal_http import LocalOperatorHTTP
from .connect import project_profile
from .native_input import display_text
from .service import resolve_local_service
from .terminal_target import terminal_target_selection


def _profile(path):
    if not path.exists():
        return None
    try:
        document = read_json(path)
        if (document.get('format') != 1 or not isinstance(document.get('selection'), dict) or
                not isinstance(document.get('server_id'), str) or not document['server_id'] or
                not isinstance(document['selection'].get('agent'), str) or not document['selection']['agent'] or
                document.get('state') not in {'review', 'approved', 'check_submitted', 'test_submitted', 'finish', 'done'}):
            raise ValueError()
        return document
    except (ValueError, KeyError, TypeError, AttributeError):
        raise ConnectionError('PROFILE_INVALID', 'The saved project profile cannot be interpreted.') from None


def run_doctor(argv):
    modes = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    modes.add_argument('--mode', choices=('managed', 'participant'), default='managed')
    mode, argv = modes.parse_known_args(argv)
    if mode.mode == 'participant':
        from .participant_doctor import run_participant_doctor
        return run_participant_doctor(argv)
    parser = argparse.ArgumentParser(prog='okto-nexus doctor', description=
        'Inspect independent proof levels. Never start services/harnesses, apply setup, issue grants or submit work.')
    parser.add_argument('--mode', choices=('managed', 'participant'), default='managed', help='select the saved profile type')
    parser.add_argument('--profile', help='existing project profile; default is the current project')
    parser.add_argument('--project', type=Path)
    parser.add_argument('--operator-profile', help='existing human operator profile for a remote Server')
    parser.add_argument('--check-server', action='store_true', help=
        'permit bounded authenticated GETs, including the OS-vault session read for a remote operator; no MCP or native probes')
    parser.add_argument('--timeout', type=float, default=10, help='Server GET budget, 0 < seconds <= 30 (default 10)')
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--diagnostic-format', choices=('legacy', 'v1'), default='legacy',
        help='opt into the common diagnostic schema; legacy preserves existing output')
    args, service_args = parser.parse_known_args(argv)
    if not 0 < args.timeout <= 30:
        parser.error('--timeout must be greater than 0 and at most 30 seconds')
    report, level, read = ProjectDiagnostics(None), 'project_profile', None
    try:
        project, name = project_profile(args.project, args.profile)
        report.profile = name
        try:
            home, operator_name = terminal_target_selection(service_args, name, args.operator_profile)
        except (ValueError, KeyError, TypeError, AttributeError):
            raise ConnectionError('PROFILE_INVALID', 'The project topology cannot be interpreted.') from None
        document = _profile(home / 'terminal/profiles' / (name + '.json'))
        if document and (args.project is not None or not args.profile) and document['selection'].get('project') != project:
            raise ConnectionError('PROFILE_CONFLICT', 'The selected profile belongs to another project.')
        report.set(level, 'PASS' if document else 'UNKNOWN', 'PROFILE_READ' if document else 'PROFILE_ABSENT',
            'The existing project checkpoint was read without modification.' if document else 'No project checkpoint exists for this selection.',
            'Use connect when ready to review setup. Doctor does not create a profile.')
        if operator_name:
            report.topology = 'remote_operator'
            report.set('local_service', 'NOT_APPLICABLE', 'REMOTE_TOPOLOGY',
                'This profile targets a remote Server; local service state is irrelevant.',
                'Inspect service ownership on the Server or Connector host itself.')
            level = 'operator_authentication'
            operator = OperatorProfile(home, operator_name)
            operator.read()  # Validate non-secret origin metadata without opening the vault.
            if not args.check_server:
                return _finish(report, args.json, diagnostic_format=args.diagnostic_format,
                explicit_checks=args.check_server)
            transport = operator.client()
            read = DiagnosticReads(transport, timeout=args.timeout)
            me = transport.verify(call=read)
        else:
            report.topology = 'local_server'
            level = 'local_service'
            service = resolve_local_service(service_args, action='status')
            observed = service.inspect(timeout=min(2, args.timeout))
            state = observed['state']
            report.set(level, 'PASS' if state == 'ready' else 'FAIL' if state in {'stopped', 'failed'} else 'UNKNOWN',
                observed.get('reason') or ('SERVICE_READY' if state == 'ready' else 'SERVICE_UNCONFIRMED'),
                'Local instance ownership, generation, version and readiness are confirmed.' if state == 'ready' else
                'The selected local instance is not confirmed ready; no start or repair was attempted.',
                'Use service status for details and explicitly start or repair the selected instance when appropriate.',
                state=state, installed_version=observed.get('installed_version'), active_version=observed.get('active_version'))
            if state != 'ready':
                return _finish(report, args.json, diagnostic_format=args.diagnostic_format,
                explicit_checks=args.check_server)
            report.set('server_reachability', 'PASS', 'LOCAL_READINESS_CONFIRMED',
                'The selected local Server answered its identity-bound readiness check.',
                'Use --check-server to check operator access and project state.')
            if not args.check_server:
                return _finish(report, args.json, diagnostic_format=args.diagnostic_format,
                explicit_checks=args.check_server)
            level = 'operator_authentication'
            transport = LocalOperatorHTTP(host=service.adapter.host, port=service.adapter.port,
                timeout=args.timeout, max_response_bytes=8 * 1048576)
            read = DiagnosticReads(transport, timeout=args.timeout)
            me = read('GET', PREFIX + '/connections/me')
        if me.get('agent_id') != 'operator' or not isinstance(me.get('server_id'), str) or not me['server_id']:
            raise ConnectionError('OPERATOR_REQUIRED', 'The authenticated actor is not the operator.')
        report.set('server_reachability', 'PASS', 'SERVER_RESPONSE_CONFIRMED',
            'The selected Server answered the authenticated API request.',
            'Reachability does not prove client participation or completed work.')
        report.set('operator_authentication', 'PASS', 'OPERATOR_AUTHENTICATED',
            'Current operator authority was verified through the canonical API.',
            'The project agent credential and execution authorization remain independent.', server_id=me['server_id'])
        if document:
            # Checkpoint corruption must not hide the independently useful
            # identity/binding checks. No local lock, write or recovery occurs.
            checkpoint, checkpoint_error = None, None
            work_path = home / 'terminal/work' / (name + '.json')
            if work_path.exists():
                try:
                    checkpoint = read_json(work_path)
                    if checkpoint.get('format') != 1:
                        raise ValueError()
                except (OSError, ValueError, TypeError):
                    checkpoint_error = ConnectionError('WORK_CHECKPOINT_INVALID', 'Saved work cannot be interpreted.')
            inspect_project(report, read, document, checkpoint)
            if checkpoint_error:
                report.error('work_result', checkpoint_error)
    except (ConnectionError, OktoNexusError, OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        report.error(level, error)
        if level == 'operator_authentication':
            code = diagnostic_code(getattr(error, 'code', None))
            if read is not None and code in {'AUTH_FAILED', 'OPERATOR_LOGIN_REQUIRED', 'PERMISSION_DENIED', 'SERVER_UPGRADE_REQUIRED', 'OPERATOR_REQUIRED'}:
                report.set('server_reachability', 'PASS', 'SERVER_RESPONSE_CONFIRMED',
                    'The Server responded, but operator authentication or compatibility was refused.',
                    'Inspect the selected account/session and Server version; no login was attempted.')
            elif code == 'SERVER_UNREACHABLE':
                report.error('server_reachability', error)
    except KeyboardInterrupt:
        return 130
    return _finish(report, args.json, diagnostic_format=args.diagnostic_format,
                explicit_checks=args.check_server)


def _finish(report, as_json, *, diagnostic_format='legacy', scope='managed_project', explicit_checks=False):
    legacy = report.result()
    value = legacy
    if diagnostic_format == 'v1':
        from ....domain.diagnostic_report import project_report
        value = project_report(legacy, scope=scope, explicit_checks=explicit_checks)
    if as_json:
        print(json.dumps(value, ensure_ascii=False))
    else:
        print('Project diagnostics: ' + value['state'] + ' (not a readiness or task-completion guarantee)')
        for check in value['checks']:
            print(f"{check['status']} {check['id']}: {check['code']}")
            print('  ' + display_text(check['reason']))
            print('  Next: ' + display_text(check['next_action']))
    # UNKNOWN is visible uncertainty, not a fabricated failure. A report can
    # succeed as a diagnostic command while some levels remain unverified.
    return 3 if legacy['counts']['FAIL'] else 0

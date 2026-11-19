"""Find retained sessions in an exact project connection."""

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import quote, urlsplit
from uuid import uuid4

from ....application.terminal_connection import (
    PREFIX,
    ConnectionError,
    document_revision,
)
from ....application.terminal_work import (
    SUBMISSION,
    list_binding_sessions,
    read_binding_session,
)
from ....domain.quick_connect import normalize_connect_id
from ....errors import OktoNexusError
from ...outbound.local_presenter_client import (
    open_local_presentation,
    review_local_presentation,
)
from ...outbound.terminal_http import LocalOperatorHTTP
from .codex_viewer_process import present_codex, select_viewer
from .connect import project_profile
from .native_input import display_text
from .quick_connect_ids import binding_reference, public_ids
from .quick_connect_project import local_executor, project_context
from .service import resolve_local_service
from .session_commands import (
    COMMANDS,
    INTENT,
    execute_session_command,
    recover_session_command,
)
from .terminal_target import resolve_terminal_target, terminal_target_selection
from .work import open_work


def _connection(call, *, project, workspace_id, connect_id):
    me = call('GET', PREFIX + '/connections/me')
    if workspace_id is None:
        if urlsplit(call.base).hostname not in ('localhost', '127.0.0.1', '::1'):
            raise ConnectionError('PROJECT_SELECTION_REQUIRED', 'Select the exact workspace with --workspace-id.')
        executor_id = local_executor(call, me['agent_id'])
        mapped = project_context(call, server_id=me['server_id'], executor_id=executor_id,
                                 root=project)['mapped_workspace_ids']
        candidates = sorted(set(mapped))
        if len(candidates) != 1:
            raise ConnectionError('PROJECT_SELECTION_REQUIRED', 'Select one authorized workspace registered for this folder.',
                                  choices=candidates)
        workspace_id = candidates[0]
    rows = public_ids(call, server_id=me['server_id'], workspace_id=workspace_id)
    row = next((item for item in rows if item['connect_id'] == connect_id), None)
    if row is None or row['state'] != 'bound':
        raise ConnectionError('HARNESS_CONNECTION_UNAVAILABLE', 'This Harness ID has no bound connection in the selected workspace.')
    reference = binding_reference(row)
    current = call('GET', PREFIX + '/connections/bindings/' + quote(reference['binding_id'], safe=''))
    if any(current.get(key) != value for key, value in reference.items()):
        raise ConnectionError('CONNECTION_SELECTOR_CONFLICT', 'The canonical binding changed. Resolve this Harness ID again.')
    return current


def _view(call, binding):
    page = list_binding_sessions(call, binding)
    return {'state': 'listed', 'scope': {name: binding[name] for name in (
        'server_id', 'executor_id', 'binding_id', 'agent_id', 'workspace_id', 'workspace_binding_id')},
        **page, 'complete': not page['has_more']}


def _display(value, as_json):
    if as_json:
        print(json.dumps(value, ensure_ascii=True))
    elif value['state'] == 'listed':
        scope = value['scope']
        print('Workspace ' + display_text(scope['workspace_id']) + ' · host ' + display_text(scope['executor_id']))
        for item in value['sessions']:
            print(display_text(item['scope']['session_id']) + ' · ' + display_text(item['lifecycle_state'])
                  + ' · lease ' + display_text(item['lease_state']))
        if value['has_more']:
            print('The session list is incomplete. Use an exact session ID when attaching.')
        elif not value['sessions']:
            print('No retained sessions for this connection.')
    elif value['state'] == 'detached':
        print('Viewer detached. The session continues in Nexus.')
    else:
        print(display_text(value['message']))
        for item in value.get('choices') or ():
            print(display_text(item))


def _select_session(call, binding, explicit, *, interactive):
    if explicit is not None:
        return read_binding_session(call, binding, explicit)
    page = list_binding_sessions(call, binding)
    candidates = [row['scope']['session_id'] for row in page['sessions'] if row.get('control_available') is True]
    if not candidates and not page['has_more']:
        raise ConnectionError('NO_LIVE_SESSION', 'This connection has no available live session.')
    if page['has_more'] or len(candidates) > 1 and not interactive:
        raise ConnectionError('SESSION_SELECTION_REQUIRED', 'Select the exact live session with --session-id.',
                              choices=candidates)
    if len(candidates) == 1 and len(page['sessions']) <= 100:
        return read_binding_session(call, binding, candidates[0])
    print('Choose a live session to inspect:')
    for index, session_id in enumerate(candidates, 1):
        print(f'{index}. {display_text(session_id)}')
    try:
        choice = input('Session number or Enter to cancel: ').strip()
    except EOFError:
        return None
    if not choice:
        return None
    if not choice.isascii() or not choice.isdecimal() or len(choice) > 4 or not 1 <= int(choice) <= len(candidates):
        raise ConnectionError('SESSION_SELECTION_REQUIRED', 'Select a displayed session.', choices=candidates)
    return read_binding_session(call, binding, candidates[int(choice) - 1])


def attach_session(call, binding, *, session_id=None, interactive=False, viewer_executable=None, write=False):
    """Open a viewer for the exact existing session and return the detach receipt."""
    selected = _select_session(call, binding, session_id, interactive=interactive)
    if selected is None:
        return None
    source = selected['scope']
    if selected.get('control_available') is not True:
        raise ConnectionError('SESSION_UNAVAILABLE', 'This exact session is unavailable for live attachment.')
    if not interactive:
        raise ConnectionError('PRESENTATION_TTY_REQUIRED', 'Use a terminal to open this exact session.',
                              choices=[source['session_id']])
    if not getattr(call, 'token', None):
        raise ConnectionError('OPERATOR_LOGIN_REQUIRED', 'Sign in with operator login and pass --operator-profile.')
    scope = {name: source[name] for name in (
        'server_id', 'executor_id', 'binding_id', 'workspace_id', 'workspace_binding_id', 'agent_id', 'session_id')}
    generation = source['session_owner_generation']
    executable = select_viewer(viewer_executable)
    reviewed = review_local_presentation(call, scope=scope, expected_session_generation=generation,
                                         **({'write': True} if write else {}))
    writer = reviewed if write else None
    revision = writer.capability_revision if writer else reviewed
    if writer and writer.occupied:
        try:
            confirmation = input('Transfer terminal input from the current writer? [y/N] ')
        except EOFError:
            return None
        if confirmation.strip().lower() not in ('y', 'yes'):
            return None
    mode = 'Codex with session input' if writer else 'read-only Codex'
    print(f'Opening {mode} for {display_text(scope["session_id"])} '
          f'in workspace {display_text(scope["workspace_id"])} on host {display_text(scope["executor_id"])}.')
    if writer:
        print('Enter sends plain text when idle and opens a reorientation review during a turn.')
        print('Use Nexus to put a message in the durable queue while the turn runs.')
        print('Tab retains text in this viewer until it can send.')
    print('Press Ctrl+] to detach from this session.', flush=True)
    with open_local_presentation(call, scope=scope, expected_session_generation=generation,
                                 capability_revision=revision, client_intent_id='viewer_' + uuid4().hex,
                                 **({'writer': writer} if writer else {})) as link:
        print('Presentation ' + link.attachment_id, flush=True)
        present_codex(link, executable)
    _display({'state': 'detached'}, False)
    print('Session ' + display_text(scope['session_id']))
    return {'status': 'detached', 'scope': scope, 'attachment_id': link.attachment_id,
            'attach_strategy': 'codex_local_write' if writer else 'codex_local_read', 'capability_revision': revision}


def resume_saved_session(call, binding, session_id):
    if not getattr(call, 'token', None):
        raise ConnectionError('OPERATOR_LOGIN_REQUIRED', 'Sign in with operator login and pass --operator-profile.')
    source = read_binding_session(call, binding, session_id)['scope']
    generation = source.get('session_owner_generation')
    if type(generation) is not int or generation < 1:
        raise ConnectionError('SESSION_UNAVAILABLE', 'The exact source generation is unavailable.')
    scope_fields = ('server_id', 'executor_id', 'binding_id', 'agent_id', 'workspace_id', 'workspace_binding_id')
    identity = {field: source[field] for field in (*scope_fields, 'session_id', 'session_owner_generation')}
    intent_id = 'saved_resume_' + document_revision(identity)
    try:
        durable = call('GET', PREFIX + '/runtime/intents/' + intent_id)
    except ConnectionError as error:
        if error.http_status != 404:
            raise
        body = {key: binding[key] for key in ('agent_id', 'binding_id', 'workspace_binding_id')}
        resolution = call('POST', PREFIX + '/runtime/intents:resolve', body | {
            'client_intent_id': intent_id, 'intent': 'runtime.resume_saved',
            'session_id': session_id, 'source_session_generation': generation,
        })
        durable = {'resolution': resolution, 'operation': None}
    resolution = durable.get('resolution') or {}
    lineage = resolution.get('saved_resume') or {}
    scope = resolution.get('scope') or {}
    successor = scope.get('session_id')
    if (resolution.get('client_intent_id') != intent_id
            or lineage.get('source_session_id') != session_id or lineage.get('source_session_generation') != generation
            or any(scope.get(field) != binding[field] for field in scope_fields)
            or not isinstance(successor, str) or successor == session_id
            or not all(field in resolution for field in SUBMISSION)):
        raise ConnectionError('SAVED_RESUME_UNCONFIRMED', 'The resume receipt does not match the selected source.')
    operation = durable.get('operation')
    if operation is None:
        operation = call('POST', PREFIX + '/runtime/operations', {field: resolution[field] for field in SUBMISSION})
    if (operation.get('operation_id') != resolution['operation_id'] or operation.get('scope') != scope
            or operation.get('action') != 'runtime.open'):
        raise ConnectionError('SAVED_RESUME_UNCONFIRMED', 'The operation receipt does not match the selected successor.')
    stage = operation.get('executor_stage')
    unconfirmed = stage == 'OUTCOME_UNKNOWN'
    if stage == 'SUBMISSION_STARTED':
        # Recovery can retain only the opening fence after proving that the
        # successor process exited. The receipt still describes a possible effect.
        successor_view = read_binding_session(call, binding, successor)
        if successor_view['scope'].get('session_owner_generation') != scope.get('session_owner_generation'):
            raise ConnectionError('SAVED_RESUME_UNCONFIRMED', 'The stored successor generation changed.')
        unconfirmed = (successor_view.get('lifecycle_state') in ('CLOSED', 'FAILED')
                       and successor_view.get('lease_state') == 'CLOSED')
    status = 'outcome is unconfirmed' if unconfirmed else display_text(stage or 'pending')
    return {'state': 'resume_unconfirmed' if unconfirmed else 'resume_requested',
            'source_session_id': session_id, 'session_id': successor,
            'operation_id': resolution['operation_id'], 'executor_stage': stage,
            'message': f'Saved resume {status} for {display_text(session_id)}. '
                       f'Successor session {display_text(successor)}. Receipt {display_text(resolution["operation_id"])}.'}


def _target(args, service_args, profile):
    if args.connect_id:
        return resolve_terminal_target(service_args, None, args.operator_profile, resolve_local_service)
    _, retained = terminal_target_selection(service_args, profile, None)
    if retained and args.operator_profile not in (None, retained):
        raise ConnectionError('PROFILE_CONFLICT', 'The project profile names another operator topology.')
    return resolve_terminal_target(service_args, profile if retained or args.operator_profile is None else None,
                                  args.operator_profile, resolve_local_service)


def run_session(argv):
    parser = argparse.ArgumentParser(prog='okto-nexus session', description='Inspect or control an exact session.')
    parser.add_argument('action', choices=('list', 'attach', 'resume', *COMMANDS, 'receipt'))
    connection = parser.add_mutually_exclusive_group()
    connection.add_argument('--id', dest='connect_id', help='public Harness ID in the selected workspace')
    connection.add_argument('--profile', help='existing project profile')
    parser.add_argument('--project', type=Path, help='existing local project folder')
    parser.add_argument('--workspace-id', help='exact workspace for a public Harness ID')
    parser.add_argument('--operator-profile', help='saved human operator login')
    parser.add_argument('--session-id', help='exact runtime session')
    parser.add_argument('--message-file', type=Path, help='UTF-8 text to review for send or steer')
    parser.add_argument('--intent', help='terminal request identifier for receipt recovery')
    parser.add_argument('--owner-generation', type=int, help='original session owner generation for receipt recovery')
    parser.add_argument('--viewer-executable', type=Path, help='absolute path to the reviewed local viewer')
    parser.add_argument('--write', action='store_true', help='enable plain-text input for a supported local viewer')
    parser.add_argument('--json', action='store_true')
    args, service_args = parser.parse_known_args(argv)
    if args.workspace_id and not args.connect_id:
        parser.error('--workspace-id requires --id')
    if args.workspace_id and args.project is not None:
        parser.error('choose --workspace-id or --project')
    if args.viewer_executable is not None and args.action != 'attach':
        parser.error('--viewer-executable requires attach')
    if args.write and (args.action != 'attach' or args.json):
        parser.error('--write requires interactive attach')
    if args.action == 'list' and args.session_id is not None:
        parser.error('--session-id requires a specific session action')
    if args.action not in ('list', 'attach') and args.session_id is None:
        parser.error(f'{args.action} requires the exact --session-id')
    if args.message_file is not None and args.action not in ('send', 'steer'):
        parser.error('--message-file requires send or steer')
    if args.action in COMMANDS and args.json:
        parser.error('write actions require terminal confirmation')
    if args.action == 'receipt':
        if args.intent is None or INTENT.fullmatch(args.intent) is None or not 0 < (args.owner_generation or 0) < 2**63:
            parser.error('receipt requires the terminal --intent and original --owner-generation')
    elif args.intent is not None or args.owner_generation is not None:
        parser.error('--intent and --owner-generation require receipt')
    if args.session_id is not None and (not 1 <= len(args.session_id) <= 160 or not args.session_id.isprintable()):
        parser.error('invalid session ID')
    if args.connect_id is not None:
        try:
            args.connect_id = normalize_connect_id(args.connect_id)
        except ValueError:
            parser.error('invalid Harness ID')
    try:
        project, profile = project_profile(args.project, args.profile)
        service = _target(args, service_args, profile)
        status = service.inspect()
        drain_read = args.action in ('list', 'receipt') and status['state'] == 'stopping' and status.get('ready_for_queries')
        if status['state'] != 'ready' and not drain_read:
            raise ConnectionError('SERVICE_NOT_READY', 'The selected Server is unavailable for session reads.')
        if args.connect_id:
            call = service.operator_http if hasattr(service, 'operator_http') else LocalOperatorHTTP(
                host=service.adapter.host, port=service.adapter.port)
            binding = _connection(call, project=project, workspace_id=args.workspace_id, connect_id=args.connect_id)
        else:
            flow = open_work(service, profile)
            if (args.project is not None or args.profile is None) and flow.connection['selection']['project'] != project:
                raise ConnectionError('PROFILE_CONFLICT', 'This profile belongs to another project directory.')
            call, binding = flow.call, flow.binding()
        if status.get('server_id') not in (None, binding['server_id']):
            raise ConnectionError('SERVER_ID_MISMATCH', 'The session catalog belongs to another Server.')
        if args.action == 'attach':
            attach_session(call, binding, session_id=args.session_id, viewer_executable=args.viewer_executable,
                           interactive=not args.json and sys.stdin.isatty() and sys.stdout.isatty(), write=args.write)
            return 0
        if args.action == 'resume':
            if not args.json:
                print('Resume the saved conversation in a successor session. The source queue stays with the original session.')
            result = resume_saved_session(call, binding, args.session_id)
            _display(result, args.json)
            return int(result['state'] == 'resume_unconfirmed' or result['executor_stage'] in ('FAILED', 'CANCELLED'))
        if args.action in COMMANDS:
            result = execute_session_command(call, binding, args.session_id, args.action,
                interactive=sys.stdin.isatty() and sys.stdout.isatty(), message_file=args.message_file, read=input)
            _display(result, args.json)
            return int(result['state'] == 'unconfirmed')
        if args.action == 'receipt':
            result = recover_session_command(call, binding, args.session_id, args.owner_generation, args.intent)
            _display(result, args.json)
            return 0
        _display(_view(call, binding), args.json)
        return 0
    except ConnectionError as error:
        result = {'state': 'refused', 'code': error.code, 'message': error.message}
        if error.choices is not None:
            result['choices'] = error.choices
    except KeyboardInterrupt:
        return 130
    except (OSError, OktoNexusError, ValueError, KeyError):
        result = {'state': 'refused', 'code': 'SESSION_UNAVAILABLE',
                  'message': 'Could not confirm the session in the selected connection.'}
    _display(result, args.json)
    return 3

"""Messages are conversation; handoffs are work. Both use canonical MCP."""
import argparse
import json
import math
import os
from pathlib import Path
import sys
from uuid import uuid4

from ....application.terminal_connection import ConnectionError
from ....application.terminal_coordination import TerminalCoordination, OPERATIONS
from ....application.terminal_participant import TerminalParticipant
from ....config import load_config
from ...outbound.coordination_files import CoordinationFiles
from ...outbound.participant_client import ParticipantHTTP
from ...outbound.participant_coordination_mcp import ParticipantMCP
from ...outbound.participant_files import _check_private
from ...outbound.service_manager.context import read_json
from ...outbound.service_manager.locking import ExclusiveFileLock
from .connect import project_profile
from .native_input import display_text
from .participant import _key


def _json(value):
    try:
        return json.loads(value, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError, TypeError):
        raise argparse.ArgumentTypeError('Use valid finite JSON.') from None


def _parser(command):
    parser = argparse.ArgumentParser(prog='okto-nexus ' + command, description=__doc__)
    parser.add_argument('action', choices={'message': ('send',), 'handoff': ('create', 'wait'), 'request': ('inspect',)}[command])
    parser.add_argument('id', nargs='?')
    parser.add_argument('--home', type=Path)
    parser.add_argument('--profile')
    parser.add_argument('--project', type=Path)
    parser.add_argument('--workspace', '--workspace-id', dest='workspace_id')
    parser.add_argument('--json', action='store_true')
    keys = parser.add_mutually_exclusive_group()
    keys.add_argument('--key-stdin', action='store_true')
    keys.add_argument('--key-env', metavar='NAME')
    if command == 'request':
        parser.add_argument('--operation', choices=OPERATIONS)
    else:
        parser.add_argument('--request-id')
        parser.add_argument('--new-request', action='store_true', help='Explicitly start new work; otherwise resume the latest request.')
        target = parser.add_mutually_exclusive_group()
        target.add_argument('--to')
        target.add_argument('--target-json', type=_json, help='Exact canonical routing object, without strategy conversion')
        target.add_argument('--broadcast', action='store_true')
        body = parser.add_mutually_exclusive_group()
        body.add_argument('--body')
        body.add_argument('--body-file', type=Path)
        body.add_argument('--body-stdin', action='store_true')
        parser.add_argument('--trace-id')
        parser.add_argument('--session-id', help='Reuse this existing canonical session; no session is opened automatically')
        parser.add_argument('--session-secret-env', metavar='NAME')
        if command == 'message':
            parser.add_argument('--subject')
            parser.add_argument('--channel-id')
            parser.add_argument('--parent-message-id')
            parser.add_argument('--artifact', action='append', default=[])
            parser.add_argument('--no-reply', action='store_true')
        else:
            parser.add_argument('--title')
            parser.add_argument('--payload-json', type=_json)
            parser.add_argument('--visibility', choices=('private', 'eligible', 'public'), default='eligible')
            parser.add_argument('--acceptance-criteria', type=_json)
            parser.add_argument('--verify-by', type=_json)
            parser.add_argument('--depends-on', action='append', default=[])
            parser.add_argument('--wait', action='store_true')
            parser.add_argument('--timeout', type=float, default=300)
    return parser


def _arguments(command, args, parser):
    if args.body_stdin and args.key_stdin:
        parser.error('Content and credential cannot both consume stdin.')
    if not (args.to or args.broadcast or args.target_json is not None):
        parser.error('Select --to, --broadcast, or --target-json explicitly.')
    if args.target_json is not None and type(args.target_json) is not dict:
        parser.error('--target-json must be an object.')
    target = args.target_json if args.target_json is not None else (
        dict(strategy='direct', agent_id=args.to) if args.to else dict(strategy='broadcast'))
    body = args.body
    if args.body_file:
        with args.body_file.open('r', encoding='utf-8') as source:
            body = source.read(1048577)
    elif args.body_stdin:
        body = sys.stdin.read(1048577)
    if body is not None and len(body) > 1048576:
        parser.error('Content exceeds the 1 MiB client limit; use an artifact.')
    arguments = dict(target=target)
    if command == 'message':
        if body is None:
            parser.error('Select --body-file, --body-stdin or --body.')
        arguments.update(body=body, no_reply=args.no_reply)
        for key in ('subject', 'channel_id', 'parent_message_id'):
            if getattr(args, key) is not None:
                arguments[key] = getattr(args, key)
        if args.artifact:
            arguments['artifacts'] = args.artifact
    else:
        if args.payload_json is not None and (body is not None or args.title is not None):
            parser.error('--payload-json cannot be combined with --title or body options.')
        if args.payload_json is None and body is None:
            parser.error('Provide a body or --payload-json for the handoff.')
        arguments.update(visibility=args.visibility, payload=args.payload_json if args.payload_json is not None else
            dict(body=body, **({'title': args.title} if args.title is not None else {})))
        for key in ('acceptance_criteria', 'verify_by'):
            if getattr(args, key) is not None:
                arguments[key] = getattr(args, key)
        if args.depends_on:
            arguments['depends_on'] = args.depends_on
    if args.trace_id:
        arguments['trace_id'] = args.trace_id
    if args.session_id:
        arguments['from_session_id' if command == 'message' else 'session_id'] = args.session_id
    if args.session_secret_env:
        secret = os.environ.get(args.session_secret_env)
        if not secret:
            raise ConnectionError('SESSION_PROOF_REQUIRED', 'The explicitly selected session secret is unavailable.')
        arguments['session_secret'] = secret
    return arguments


def _display(value, as_json):
    if as_json:
        print(json.dumps(value, ensure_ascii=False, allow_nan=False))
    else:
        print(display_text(json.dumps(value, ensure_ascii=False, allow_nan=False)))


def run_coordination(command, argv):
    parser = _parser(command)
    args = parser.parse_args(argv)
    create = args.action in ('send', 'create')
    if args.action == 'wait' and not args.id:
        parser.error('Select the exact handoff ID.')
    if args.action == 'wait' and any(getattr(args, name) for name in (
            'request_id', 'new_request', 'to', 'target_json', 'broadcast', 'body', 'body_file', 'body_stdin',
            'title', 'payload_json', 'wait', 'trace_id', 'session_id', 'session_secret_env',
            'acceptance_criteria', 'verify_by', 'depends_on')):
        parser.error('handoff wait only observes its ID; creation options belong to handoff create.')
    if create and args.id:
        parser.error('Use --request-id for creation; positional IDs are for inspect/wait.')
    if command == 'handoff' and (not math.isfinite(args.timeout) or not 0 <= args.timeout <= 86400):
        parser.error('--timeout must be between zero and 86400 seconds.')
    guard, flow, identity, operation, confirmed = None, None, None, None, None
    try:
        arguments = _arguments(command, args, parser) if create else None
        project, profile = project_profile(args.project, args.profile)
        home = (args.home or load_config(os.environ, []).home_dir).expanduser().resolve()
        profile_path = home / 'terminal/participants' / (profile + '.json')
        if not profile_path.is_file():
            raise ConnectionError('PARTICIPANT_PROFILE_REQUIRED', 'Select an existing participant profile created by init --mode participant.')
        for path in (profile_path.parent, profile_path):
            if path.is_symlink() or getattr(path, 'is_junction', lambda: False)():
                raise ConnectionError('PROFILE_PATH_UNSAFE', 'Use regular private participant profile files.')
        _check_private(profile_path.parent)
        guard = ExclusiveFileLock(profile_path.with_suffix('.guard'))
        guard.acquire()
        saved = read_json(profile_path)
        participant = TerminalParticipant(home, profile, lambda _: None)
        participant.ensure_active(saved)
        review, _ = participant.validate(saved)
        if ((args.project is not None or not args.profile) and project != review['selection']['project'] or
                args.workspace_id is not None and args.workspace_id != review['context']['workspace']['workspace_id']):
            raise ConnectionError('PROFILE_CONFLICT', 'The selected project/workspace conflicts with the authenticated participant profile.')
        key = _key(args, participant, saved)
        context = ParticipantHTTP(review['origin'], key, review['context']['agent_id']).context(
            review['context']['workspace']['workspace_id'])
        if context['server_id'] != review['context']['server_id']:
            raise ConnectionError('SERVER_CHANGED', 'The Server installation changed. Preserve existing requests and review the origin.')
        scope = dict(origin=review['origin'], server_id=context['server_id'], agent_id=context['agent_id'],
                     workspace_id=context['workspace']['workspace_id'])
        store = CoordinationFiles(home / 'terminal/coordination' / profile, scope)
        index = store.index()
        mcp = ParticipantMCP(review['origin'], key, context['agent_id'])
        checkpoint = None
        if create:
            operation = 'message_create' if command == 'message' else 'handoff_create'
            identity = args.request_id or (None if args.new_request else index['latest'].get(operation)) or uuid4().hex
            checkpoint = store.load(operation, identity)
            if args.new_request and checkpoint is not None:
                raise ConnectionError('REQUEST_ALREADY_EXISTS', 'A new request needs a fresh ID. Existing IDs keep their original window.')
            if args.request_id and checkpoint is None and not args.new_request:
                raise ConnectionError('CHECKPOINT_NOT_FOUND', 'No local checkpoint proves this ID is new. Inspect it, or explicitly select --new-request for a new intention.')
            if identity == index['latest'].get(operation) and checkpoint is None:
                raise ConnectionError('CHECKPOINT_MISSING', 'The latest request checkpoint is missing. Review it before any replay.')
        elif command == 'request':
            candidates = [(op, args.id or index['latest'].get(op)) for op in OPERATIONS if args.operation in (None, op)]
            candidates = [(op, value) for op, value in candidates if value and (args.operation or store.load(op, value))]
            if len(candidates) != 1:
                raise ConnectionError('REQUEST_OPERATION_REQUIRED', 'Select --operation and the exact request ID; the local selection is absent or ambiguous.')
            operation, identity = candidates[0]
            checkpoint = store.load(operation, identity)
        flow = TerminalCoordination(mcp, scope, store.save, checkpoint)
        if not create:
            guard.release()
            guard = None
        if create:
            result = flow.submit(operation, identity, arguments, observation=command == 'handoff' and args.wait)
            confirmed = result
            guard.release()
            guard = None
            if command == 'handoff' and args.wait:
                result = flow.wait_request(result, timeout=args.timeout)
                result.update(client_request_id=identity, operation=operation)
            code = result.get('exit_code', 0 if result['state'] in ('created', 'pending_approval', 'approved_awaiting_execution') else 3)
        elif command == 'request':
            result, code = flow.inspect(operation, identity), 0
        else:
            result = flow.wait(args.id, timeout=args.timeout)
            code = result['exit_code']
        result['exit_code'] = code
        _display(result, args.json)
        return code
    except KeyboardInterrupt:
        _display(dict(format=1, state='interrupted', client_request_id=identity, operation=operation,
            handoff_id=args.id if args.action == 'wait' else (confirmed or {}).get('handoff_id'), exit_code=130,
            **({'creation': confirmed} if confirmed else {}),
            possible_effect=bool(flow and flow.document and flow.document['state'] == 'uncertain')),
            args.json)
        return 130
    except Exception as error:
        known = isinstance(error, ConnectionError)
        possible = error.possible_effect if known else bool(flow and flow.document and flow.document['state'] == 'uncertain')
        uncertain_read = known and error.code in {
            'MCP_RESPONSE_UNCONFIRMED', 'MCP_NEGOTIATION_UNCONFIRMED', 'SERVER_UNREACHABLE',
            'RESPONSE_UNCONFIRMED', 'EVENT_CURSOR_UNCONFIRMED', 'HANDOFF_RESULT_UNCONFIRMED'}
        code = 5 if possible or uncertain_read or args.action in ('wait', 'inspect') and not known else 3
        _display(dict(format=1, state='uncertain' if code == 5 else 'refused',
            code=error.code if known else 'COORDINATION_UNCONFIRMED', message=error.message if known else
            'The coordination command could not be confirmed. Preserve the checkpoint and inspect the same ID.',
            client_request_id=identity, operation=operation,
            handoff_id=args.id if args.action == 'wait' else (confirmed or {}).get('handoff_id'),
            **({'creation': confirmed} if confirmed else {}),
            possible_effect=possible, exit_code=code), args.json)
        return code
    finally:
        if guard is not None:
            guard.release()

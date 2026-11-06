"""An optional directed exchange, followed by a separately consented handoff."""
import argparse
import math
import os
from pathlib import Path
import sys
from types import SimpleNamespace

from ....application.terminal_connection import ConnectionError, document_revision
from ....application.terminal_cooperation import TerminalCooperation
from ....application.terminal_participant import TerminalParticipant
from ....config import load_config
from ...outbound.cooperation_files import CooperationFiles
from ...outbound.participant_client import ParticipantHTTP
from ...outbound.participant_coordination_mcp import ParticipantMCP
from ...outbound.participant_files import _check_private
from ...outbound.service_manager.context import read_json
from ...outbound.service_manager.locking import ExclusiveFileLock, LockBusy
from .connect import project_profile
from .coordination import _display
from .participant import _key


def _parser():
    parser = argparse.ArgumentParser(prog='okto-nexus participant smoke', description=__doc__)
    parser.add_argument('action', choices=('exchange', 'handoff', 'status', 'observe'))
    parser.add_argument('--home', type=Path)
    parser.add_argument('--profile')
    parser.add_argument('--project', type=Path)
    parser.add_argument('--workspace', '--workspace-id', dest='workspace_id')
    parser.add_argument('--attempt', help='Select a retained smoke ID instead of the latest review')
    parser.add_argument('--to', help='Exact peer identity for a new directed exchange')
    decision = parser.add_mutually_exclusive_group()
    decision.add_argument('--plan', action='store_true')
    decision.add_argument('--approve', metavar='REVISION')
    parser.add_argument('--new', action='store_true', help='Review an explicitly new attempt; retain old attempts')
    parser.add_argument('--session-id', help='Reuse explicit existing conversation context; no session is opened')
    parser.add_argument('--session-secret-env', metavar='NAME')
    parser.add_argument('--timeout', type=float, default=300, help='Observation budget in seconds, up to 86400')
    keys = parser.add_mutually_exclusive_group()
    keys.add_argument('--key-stdin', action='store_true')
    keys.add_argument('--key-env', metavar='NAME')
    parser.add_argument('--json', action='store_true')
    return parser


def _uncertain(flow, store, previous=None):
    if flow is None or flow.document is None or store is None or store.selected is None:
        return False
    try:
        for phase, operation in (('exchange', 'message_create'), ('handoff', 'handoff_create')):
            checkpoint = store.load_request(operation, flow.document['request_ids'][operation])
            if checkpoint is None:
                # Use the journal loaded before this command: a failed first
                # consent write must not imply a productive transmission.
                if previous and previous['consents'][phase] is not None and previous['receipts'][phase] is None:
                    return True
            elif checkpoint.get('state') == 'uncertain':
                return True
        return False
    except Exception:
        return True


def run_cooperation(argv):
    parser = _parser()
    args = parser.parse_args(argv)
    if not math.isfinite(args.timeout) or not 0 <= args.timeout <= 86400:
        parser.error('--timeout must be between zero and 86400 seconds.')
    if args.action in ('status', 'observe') and any((args.to, args.plan, args.approve, args.new,
                                                   args.session_id, args.session_secret_env)):
        parser.error('status/observe do not accept creation or consent options.')
    if args.action == 'handoff' and any((args.to, args.new, args.session_id)):
        parser.error('The handoff uses the peer and session of its original exchange.')
    if args.new and (args.action != 'exchange' or args.approve or args.attempt):
        parser.error('--new reviews a separate exchange; it cannot approve or select an old attempt.')
    if args.action == 'status' and (args.key_stdin or args.key_env):
        parser.error('status only reads historical local evidence and does not accept credentials.')
    profile_guard, attempt_guard, flow, store, document = None, None, None, None, None
    try:
        project, profile = project_profile(args.project, args.profile)
        home = (args.home or load_config(os.environ, []).home_dir).expanduser().resolve()
        profile_path = home / 'terminal/participants' / (profile + '.json')
        if not profile_path.is_file():
            raise ConnectionError('PARTICIPANT_PROFILE_REQUIRED', 'Select an existing participant profile.')
        for path in (profile_path.parent, profile_path):
            if path.is_symlink() or getattr(path, 'is_junction', lambda: False)():
                raise ConnectionError('PROFILE_PATH_UNSAFE', 'Use regular private participant profile files.')
        _check_private(profile_path.parent)
        # Historical snapshots and retained plans need no lock file. A new
        # review acquires exclusion below before it can persist anything.
        if args.action != 'status' and not (args.plan and not args.new):
            profile_guard = ExclusiveFileLock(profile_path.with_suffix('.guard'))
            profile_guard.acquire()
        saved = read_json(profile_path)
        participant = TerminalParticipant(home, profile, lambda value: None)
        review, _ = participant.validate(saved)
        if args.action != 'status':
            participant.ensure_active(saved)
        if ((args.project is not None or not args.profile) and project != review['selection']['project'] or
                args.workspace_id is not None and args.workspace_id != review['context']['workspace']['workspace_id']):
            raise ConnectionError('PROFILE_CONFLICT', 'The selected project/workspace conflicts with this participant profile.')
        scope = dict(origin=review['origin'], server_id=review['context']['server_id'],
            agent_id=review['context']['agent_id'], workspace_id=review['context']['workspace']['workspace_id'])
        binding = document_revision(dict(setup_run_id=review['setup_run_id'], review_revision=saved['review_revision']))
        store = CooperationFiles(home / 'terminal/cooperation' / profile, scope, binding)
        document = None if args.new else store.load(args.attempt)
        if document is None and args.action not in ('status', 'exchange'):
            raise ConnectionError('SMOKE_REVIEW_REQUIRED', 'Review a directed exchange before this action.')
        requests = SimpleNamespace(load=store.load_request, save=store.save_request)
        flow = TerminalCooperation(None, scope, store.save, requests, document)
        if args.action == 'status':
            result = dict(flow.status(), exit_code=0)
            _display(result, args.json)
            return 0
        if args.plan and document is not None:
            result = None
            if args.action == 'exchange':
                result = flow.review_exchange(args.to or document['peer'], binding,
                    session_id=args.session_id if args.session_id is not None else document['session_id'])
            elif document['reviews']['handoff'] is not None:
                result = flow.status()
            if result is not None:
                result['exit_code'] = 0
                _display(result, args.json)
                return 0
        if profile_guard is None:
            profile_guard = ExclusiveFileLock(profile_path.with_suffix('.guard'))
            profile_guard.acquire()
            if read_json(profile_path) != saved:
                raise ConnectionError('PROFILE_CONFLICT', 'The participant profile changed while planning. Reopen the same attempt.')
            if not args.new:
                document = store.load(args.attempt)
                flow = TerminalCooperation(None, scope, store.save, requests, document)
        if document is not None:
            attempt_guard = ExclusiveFileLock(store.guard_path())
            attempt_guard.acquire()
            # Another observer may have saved evidence before this lock was
            # acquired. Reload under attempt exclusion before changing it.
            document = store.load(document['smoke_id'])
            flow = TerminalCooperation(None, scope, store.save, requests, document)

        def connect():
            if flow.mcp is not None:
                return
            key = _key(args, participant, saved)
            context = ParticipantHTTP(scope['origin'], key, scope['agent_id']).context(scope['workspace_id'])
            current = dict(origin=scope['origin'], server_id=context['server_id'],
                agent_id=context['agent_id'], workspace_id=context['workspace']['workspace_id'])
            if current != scope:
                raise ConnectionError('SERVER_CHANGED', 'The current Server identity or participant scope changed. Preserve this attempt.')
            flow.mcp = ParticipantMCP(scope['origin'], key, scope['agent_id'])

        if args.action == 'observe':
            connect()
            profile_guard.release()
            profile_guard = None
            result = flow.observe(timeout=args.timeout)
        else:
            phase = args.action
            if phase == 'exchange':
                if flow.document is None and args.approve:
                    raise ConnectionError('SMOKE_REVIEW_REQUIRED', 'Review the exchange before approving it.')
                peer = args.to or (flow.document or {}).get('peer')
                session = args.session_id if args.session_id is not None else (flow.document or {}).get('session_id')
                result = flow.review_exchange(peer, binding, session_id=session)
                if attempt_guard is None:
                    attempt_guard = ExclusiveFileLock(store.guard_path())
                    attempt_guard.acquire()
            elif flow.document['reviews']['handoff'] is None:
                if args.approve:
                    raise ConnectionError('REVIEW_REQUIRED', 'Review the separately consented handoff before approving it.')
                connect()
                result = flow.review_handoff()
            else:
                result = flow.status()
            approval = args.approve or (None if args.plan else flow.document['consents'][phase])
            if approval is None and not args.plan and not args.json and sys.stdin.isatty():
                _display(result, False)
                if input('Approve this ' + phase + ' and its disclosed effects? [y/N] ').strip().lower() in ('y', 'yes'):
                    approval = result['review_revision']
            if approval is not None:
                if approval != flow.document['reviews'][phase]:
                    raise ConnectionError('REVIEW_REQUIRED', 'Approve the exact retained review revision for this phase.')
                connect()
                secret = None
                if args.session_secret_env:
                    secret = os.environ.get(args.session_secret_env)
                    if not secret or flow.document['session_id'] is None:
                        raise ConnectionError('SESSION_PROOF_REQUIRED', 'Supply the selected proof for the explicitly reviewed session.')
                result = (flow.send_exchange if phase == 'exchange' else flow.send_handoff)(approval, session_secret=secret)
                receipt = flow.document['receipts'][phase]
                result['exit_code'] = 0 if receipt and receipt['state'] in (
                    'created', 'pending_approval', 'approved_awaiting_execution') else 3
        code = result.setdefault('exit_code', 0)
        _display(result, args.json)
        return code
    except (KeyboardInterrupt, EOFError):
        result = dict(format=1, state='interrupted', exit_code=130, possible_effect=_uncertain(flow, store, document))
        if flow and flow.document:
            result['smoke'] = flow.status()
            result['smoke_id'] = flow.document['smoke_id']
        _display(result, args.json)
        return 130
    except Exception as error:
        known = isinstance(error, ConnectionError)
        possible = (error.possible_effect if known else False) or _uncertain(flow, store, document)
        code_name = error.code if known else ('SMOKE_BUSY' if isinstance(error, LockBusy) else 'SMOKE_UNCONFIRMED')
        unknown = possible or code_name in {'SMOKE_UNCONFIRMED', 'MCP_RESPONSE_UNCONFIRMED',
            'MCP_NEGOTIATION_UNCONFIRMED', 'SERVER_UNREACHABLE', 'RESPONSE_UNCONFIRMED',
            'EVENT_CURSOR_UNCONFIRMED', 'HANDOFF_RESULT_UNCONFIRMED'}
        result = dict(format=1, state='uncertain' if unknown else 'refused', code=code_name,
            message=error.message if known else ('Another command is observing or changing this attempt.'
                if isinstance(error, LockBusy) else 'The cooperation command could not be confirmed. Preserve and inspect the same attempt.'),
            possible_effect=possible, exit_code=5 if unknown else 3)
        if flow and flow.document:
            result['smoke_id'] = flow.document['smoke_id']
            result['smoke'] = flow.status()
        _display(result, args.json)
        return result['exit_code']
    finally:
        if attempt_guard is not None:
            attempt_guard.release()
        if profile_guard is not None:
            profile_guard.release()

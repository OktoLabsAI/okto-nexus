"""Project work and native decisions through the existing operator APIs."""
import argparse
import json
from pathlib import Path
import sys
import time

from ....application.terminal_connection import ConnectionError, document_revision
from ....application.terminal_work import TerminalWork
from ....errors import OktoNexusError
from ...outbound.service_manager.context import atomic_json, read_json
from ...outbound.service_manager.locking import ExclusiveFileLock, LockBusy
from ...outbound.terminal_http import LocalOperatorHTTP
from .native_input import answer, display_text
from .service import resolve_local_service

ACTIONS = ('chat', 'send', 'steer', 'interrupt', 'close', 'status', 'watch', 'events', 'sessions', 'answer', 'resume')


def display(value, as_json=False):
    if as_json:
        print(json.dumps(value, ensure_ascii=False))
        return
    if 'operations' in value:
        session = value['session']
        print(f"Work: {display_text(value['state'])} | Session: {display_text(session['scope']['session_id'])} ({display_text(session['lifecycle_state'])})")
        for operation in value['operations']:
            print(f"{display_text(operation['action'])} {display_text(operation['operation_id'])}: {display_text(operation['executor_stage'] or operation['admission_state'])}")
            if operation.get('error'):
                print(display_text(operation['error'].get('message', operation['error'].get('code'))))
            if operation.get('result'):
                print(display_text(operation['result']['output_text']))
                if operation['result'].get('output_truncated'):
                    print('Output is truncated in this view; canonical session events retain the available history.')
        for detail in value['requests']['items']:
            proposal = detail['request_payload']['kwargs']
            print(f"Request {display_text(detail['approval_id'])}: {display_text(proposal['approval_key']['kind'])} for {display_text(proposal.get('recipient_agent_id') or 'operator')}")
            print(display_text(json.dumps(proposal['display'], ensure_ascii=False, indent=2)))
        if value.get('decision'):
            display(value['decision'])
            error = value['decision'].get('operation', {}).get('error')
            if error:
                print(display_text(error.get('message') or error['code']))
        if value['events']['gap_pending']:
            print('Canonical event history has a pending gap.')
        if value['events']['has_more']:
            print('More canonical events are available with work events --after-sequence ' + str(value['events']['next_after_sequence']))
        if value['requests']['has_more']:
            print('The workspace has more pending requests than this bounded page; select a canonical request ID with work answer.')
    elif 'canonical_state' in value:
        print(f"Decision: {display_text(value['canonical_state'])} by {display_text(value['actor_agent_id'])}; native delivery: {display_text(value['native_stage'])}.")
        print('A recorded decision does not by itself prove application by the provider.')
    elif 'operation_id' in value:
        print(f"Request {display_text(value['operation_id'])} · session {display_text(value['scope']['session_id'])}: {display_text(value['executor_stage'] or value['admission_state'])}")
        if value.get('submission_turn_operation_id'):
            print('Work operation: ' + display_text(value['submission_turn_operation_id']))
        if value.get('result'):
            print(display_text(value['result']['output_text']))
    else:
        print(display_text(json.dumps(value, ensure_ascii=False, indent=2)))


def decide_interactively(flow, approval_id, *, session_id=None):
    detail = flow.decision_detail(approval_id, session_id=session_id)
    proposal = detail['request_payload']['kwargs']
    if (detail.get('executed_result') or {}).get('decision_id'):
        display(flow.decide(approval_id, 'approve', session_id=session_id))  # Read the durable result only.
        return False
    response = answer(proposal)
    if response is None:
        return False
    choice, value = response
    display(flow.decide(approval_id, choice, response=value, reviewed_revision=document_revision(proposal), session_id=session_id))
    return True


def watch(flow, *, timeout=300, as_json=False, interactive=False, session_id=None,
          slot_name='work', after_sequence=0, stream_epoch=None):
    deadline, previous = time.monotonic() + timeout, None
    while True:
        value = flow.observe(session_id=session_id, slot_name=slot_name,
                             after_sequence=after_sequence, stream_epoch=stream_epoch)
        # Only suppress repeated presentation in this observer; no local event
        # or conversation history is persisted, and observation never dispatches.
        digest = document_revision(value)
        if digest != previous:
            display(value, as_json)
            previous = digest
        if value['state'] == 'needs_input':
            if not interactive:
                return 3
            handled = False
            for detail in value['requests']['items']:
                handled = decide_interactively(flow, detail['approval_id'], session_id=session_id) or handled
            if not handled:
                return 3
        elif value['state'] in ('completed', 'idle'):
            return 0
        elif value['state'] in ('failed', 'blocked', 'submission_unconfirmed', 'decision_refused'):
            return 3
        if time.monotonic() >= deadline:
            if not as_json:
                print('Observation time ended. The service still owns the work; use work watch to return.')
            return 3
        time.sleep(min(.5, max(0, deadline - time.monotonic())))


def chat(flow, *, timeout=300):
    print('Enter project work. Commands: /status, /watch, /resume, /sessions, /answer ID, /interrupt, /close, /new TEXT, /quit.')
    print('Leaving this terminal ends observation; the service retains the session and work.')
    try:
        display(flow.observe())
    except ConnectionError as error:
        display({'state': 'unconfirmed', 'code': error.code, 'message': error.message})
    while True:
        try:
            text = input('nexus> ').strip()
            if not text:
                continue
            if text == '/quit':
                return 0
            if text in ('/status', '/sessions'):
                display(flow.observe() if text == '/status' else flow.sessions())
            elif text == '/watch':
                watch(flow, timeout=timeout, interactive=True)
            elif text == '/resume':
                display(flow.resume())
                watch(flow, timeout=timeout, interactive=True)
            elif text.startswith('/answer '):
                decide_interactively(flow, text.removeprefix('/answer ').strip())
            elif text in ('/interrupt', '/close'):
                flow.submit(action=text[1:])
                watch(flow, timeout=timeout, interactive=True, slot_name='control')
            elif text.startswith('/') and not text.startswith('/new '):
                print('Unknown command. Use /quit to leave or type a project request.')
            else:
                new = text.startswith('/new ')
                flow.submit(text.removeprefix('/new ') if new else text, new_session=new)
                watch(flow, timeout=timeout, interactive=True)
        except EOFError:
            return 0
        except ConnectionError as error:
            display({'state': 'unconfirmed' if error.possible_effect else 'refused',
                     'code': error.code, 'message': error.message, 'possible_effect': error.possible_effect})


def open_work(service, profile, connection=None):
    directory = service.adapter.home / 'terminal'
    if connection is None:
        connection = read_json(directory / 'profiles' / (profile + '.json'))
    target = directory / 'work' / (profile + '.json')
    checkpoint = read_json(target) if target.exists() else None
    def save(document):
        target.parent.mkdir(parents=True, exist_ok=True)
        atomic_json(target, document)
    # Results are bounded to 1 MiB by the Server; JSON escaping can require six
    # times that space. Keep a finite transport bound that fits valid results.
    return TerminalWork(LocalOperatorHTTP(host=service.adapter.host, port=service.adapter.port,
        max_response_bytes=8 * 1048576), save, connection, checkpoint)


def interactive_work(service, profile, *, timeout=300):
    # The calling connect/run_work already owns the shared project profile lock.
    return chat(open_work(service, profile), timeout=timeout)


def run_work(argv):
    from .connect import project_profile
    parser = argparse.ArgumentParser(prog='okto-nexus work',
        description='Submit project work and observe or decide canonical runtime requests.')
    args_list = list(argv)
    action = args_list.pop(0) if args_list and args_list[0] in ACTIONS else None
    parser.add_argument('--profile')
    parser.add_argument('--project', type=Path)
    parser.add_argument('--message')
    parser.add_argument('--session-id')
    parser.add_argument('--new-session', action='store_true')
    parser.add_argument('--request-id', help='stable client intent ID for an explicit submission/retry')
    parser.add_argument('--target-turn-id')
    parser.add_argument('--approval-id')
    parser.add_argument('--decision', choices=('approve', 'deny'))
    parser.add_argument('--review', help='hash of the exact displayed native question proposal')
    parser.add_argument('--answer-file', type=Path, help='UTF-8 JSON native response object, read only for this submission')
    parser.add_argument('--control', action='store_true', help='observe or resume the saved interrupt/close action')
    parser.add_argument('--after-sequence', type=int, default=0)
    parser.add_argument('--stream-epoch')
    parser.add_argument('--timeout', type=float, default=300)
    parser.add_argument('--json', action='store_true')
    args, service_args = parser.parse_known_args(args_list)
    action = action or ('chat' if sys.stdin.isatty() and not args.json else 'status')
    if not 0 < args.timeout <= 300 or args.after_sequence < 0:
        parser.error('timeout must be in (0, 300]; after-sequence must be nonnegative')
    if action in ('send', 'steer') and not args.message:
        parser.error('send and steer require --message')
    if args.message is not None and action not in ('send', 'steer', 'interrupt', 'close'):
        parser.error('--message requires send, steer, interrupt or close')
    if (args.decision or args.answer_file or args.review) and action != 'answer':
        parser.error('decision options require the answer command')
    if args.answer_file and not args.decision:
        parser.error('--answer-file requires an explicit --decision and --review')
    if args.new_session and action != 'send':
        parser.error('--new-session requires send')
    if args.target_turn_id and action not in ('steer', 'interrupt'):
        parser.error('--target-turn-id requires steer or interrupt')
    if action == 'answer' and not args.approval_id:
        parser.error('answer requires --approval-id')
    if action == 'chat' and (args.json or not sys.stdin.isatty()):
        parser.error('chat requires an interactive terminal; use send/status/watch/answer with --json')
    guard = None
    try:
        service = resolve_local_service(service_args)
        project, profile = project_profile(args.project, args.profile)
        target = service.adapter.home / 'terminal/profiles' / (profile + '.json')
        if not target.exists():
            raise ConnectionError('CONNECTION_REQUIRED', 'Run connect for this project before using work.')
        status = service.inspect()
        if status['state'] != 'ready':
            display({'state': 'service_not_ready', 'service': status}, args.json)
            return 3
        guard = ExclusiveFileLock(target.with_suffix('.guard'))
        guard.acquire()
        flow = open_work(service, profile)
        if (args.project is not None or not args.profile) and flow.connection['selection']['project'] != project:
            raise ConnectionError('PROFILE_CONFLICT', 'This profile belongs to another project directory.')
        slot = 'control' if args.control else 'work'
        if action == 'chat':
            return chat(flow, timeout=args.timeout)
        if action in ('send', 'steer', 'interrupt', 'close'):
            value = flow.submit(args.message, action=action, session_id=args.session_id,
                new_session=args.new_session, client_intent_id=args.request_id, target_turn_id=args.target_turn_id)
        elif action == 'resume':
            value = flow.resume(slot)
        elif action == 'sessions':
            value = flow.sessions()
        elif action in ('status', 'watch', 'events'):
            options = dict(session_id=args.session_id, slot_name=slot, after_sequence=args.after_sequence,
                           stream_epoch=args.stream_epoch)
            if action == 'watch':
                return watch(flow, timeout=args.timeout, as_json=args.json,
                             interactive=sys.stdin.isatty() and not args.json, **options)
            value = flow.observe(**options)
            if action == 'events':
                value = value.get('events', value)
        else:
            detail = flow.decision_detail(args.approval_id, session_id=args.session_id)
            proposal = detail['request_payload']['kwargs']
            if args.decision:
                response = None
                if args.answer_file:
                    raw = args.answer_file.read_bytes()
                    if len(raw) > 16384:
                        raise ConnectionError('ANSWER_TOO_LARGE', 'The answer file exceeds the native response limit.')
                    response = json.loads(raw.decode('utf-8'))
                    if not isinstance(response, dict):
                        raise ConnectionError('ANSWER_INVALID', 'The native response must be a JSON object.')
                value = flow.decide(args.approval_id, args.decision, response=response,
                                    reviewed_revision=args.review, session_id=args.session_id)
            elif sys.stdin.isatty() and not args.json:
                decide_interactively(flow, args.approval_id, session_id=args.session_id)
                return 0
            else:
                value = dict(state='decision_review', detail=detail, review_revision=document_revision(proposal))
        display(value, args.json)
        return 3 if value.get('state') in ('blocked', 'submission_unconfirmed', 'failed', 'decision_refused') else 0
    except EOFError:
        return 0  # Leaving a question never supplies an answer or stops the service.
    except KeyboardInterrupt:
        return 130
    except (ConnectionError, OktoNexusError, LockBusy, OSError, ValueError, KeyError, TypeError) as error:
        display({'state': 'unconfirmed' if getattr(error, 'possible_effect', False) else 'refused',
            'code': getattr(error, 'code', 'PROFILE_BUSY' if isinstance(error, LockBusy) else 'CONFIG_ERROR'),
            'message': getattr(error, 'message', 'Inspect the selected service and project profile.'),
            'possible_effect': getattr(error, 'possible_effect', False)}, args.json)
        return 3
    finally:
        if guard is not None:
            guard.release()

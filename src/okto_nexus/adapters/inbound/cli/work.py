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

ACTIONS = ('chat', 'send', 'steer', 'interrupt', 'close', 'status', 'watch', 'events', 'sessions', 'answer', 'resume', 'authorize')


def display(value, as_json=False):
    if as_json:
        print(json.dumps(value, ensure_ascii=False))
        return
    if value.get('state') == 'authorization_review':
        print('Project execution authorization: ' + display_text(value['scope']['agent_id']))
        for grant in value['current_grants']:
            print(f"{display_text(grant['grant_id'])}: {display_text(grant['state'])}; actions used {grant['used_executions']} / {grant['max_executions']}; permits " + ', '.join(display_text(action) for action in grant['actions']))
        if value.get('has_more_grants'):
            print(f"Showing 50 of {value['total_grants']} grants; all grants were checked for this review.")
        if not value['can_issue']:
            print('An authorization is already available. No additional grant is needed or issued.')
            return
        print(f"New grant: until {display_text(value['request']['expires_at'])}, at most {value['request']['max_executions']} runtime actions.")
        print('Permitted actions: ' + ', '.join(display_text(action) for action in value['actions']))
        for effect in value['effects']:
            print('- ' + display_text(effect))
        print('Review: ' + display_text(value['review_revision']))
    elif value.get('state') == 'authorization_committed':
        grant = value['result']['grant']
        print('Authorization receipt: ' + display_text(grant['grant_id']))
        print('Issued until ' + display_text(grant['expires_at']) + f", at most {grant['max_executions']} runtime actions.")
        print('This is the issuance receipt; current policy, expiry and revocation still apply. No work was resumed.')
    elif 'operations' in value:
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
            print('To continue with work events, keep the same connection and use '
                  f"--session-id for {display_text(session['scope']['session_id'])}, "
                  f"--stream-epoch for {display_text(value['events']['stream_epoch'])}, "
                  f"and --after-sequence {value['events']['next_after_sequence']}.")
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


def authorize_interactively(flow, *, minutes=60, max_executions=20):
    value = flow.authorization_review(minutes=minutes, max_executions=max_executions)
    display(value)
    if value['state'] == 'authorization_review' and value['can_issue']:
        if input('Issue this reviewed project authorization? [y/N] ').strip().lower() == 'y':
            display(flow.authorize(approval=value['review_revision']))


def watch(flow, *, timeout=300, as_json=False, interactive=False, session_id=None,
          slot_name='work', after_sequence=0, stream_epoch=None):
    deadline, previous = time.monotonic() + timeout, None
    watched_scope = None
    while True:
        value = flow.observe(session_id=session_id, slot_name=slot_name,
                             after_sequence=after_sequence, stream_epoch=stream_epoch)
        page = value.get('events')
        observation = value
        if page is not None:
            scope = tuple(page['scope'][key] for key in (
                'server_id', 'executor_id', 'binding_id', 'workspace_binding_id',
                'session_id', 'session_owner_generation'))
            if watched_scope is not None and scope != watched_scope:
                raise ConnectionError('WORK_EVENT_PAGE_MISMATCH', 'The observed session changed. Review the session before watching again.')
            watched_scope = scope
            if page['stream_epoch'] is not None:
                stream_epoch = page['stream_epoch']
                after_sequence = page['next_after_sequence']
            # After advancing, an empty poll at the same cursor is not a
            # second update. Keep lifecycle and gap changes in the comparison.
            observation = value | {'events': {key: field for key, field in page.items() if key not in ('count', 'events')}}
        more_events = page is not None and page['has_more']
        digest = document_revision(observation)
        if digest != previous:
            display(value, as_json)
            previous = digest
        if value['state'] == 'needs_input':
            if not interactive:
                return 3
            handled = False
            for detail in value['requests']['items']:
                handled = decide_interactively(flow, detail['approval_id'], session_id=page['scope']['session_id']) or handled
            if not handled:
                return 3
        elif value['state'] == 'idle' or value['state'] == 'completed' and not more_events:
            return 0
        elif value['state'] in ('failed', 'blocked', 'submission_unconfirmed', 'decision_refused'):
            return 3
        if time.monotonic() >= deadline:
            if value['state'] == 'completed':
                return 0
            if not as_json:
                print('Observation time ended. The service still owns the work; use work watch to return.')
            return 3
        if more_events:
            continue
        time.sleep(min(.5, max(0, deadline - time.monotonic())))


def chat(flow, *, timeout=300, session_id=None):
    from .session_picker import SessionSelection, choose_session, recover_before_selection, pending_slots
    print('Enter project work. Commands: /status, /watch, /resume, /sessions, /answer ID, /authorize, /interrupt, /close, /new TEXT, /quit.')
    print('Leaving this terminal ends observation; the service retains the session and work.')
    if not recover_before_selection(flow, display, read=input):
        return 0
    if session_id is not None:
        current = flow.session(flow.binding(), session_id)
        if not current['control_available']:
            raise ConnectionError('SESSION_UNAVAILABLE', 'This selected session cannot continue. Inspect it or explicitly request a new context.')
        selection = SessionSelection(session_id)
    else:
        selection = choose_session(flow, read=input)
    if selection is None:
        return 0
    if selection.session_id:
        display(flow.observe(session_id=selection.session_id))
    while True:
        try:
            if pending_slots(flow):
                if not recover_before_selection(flow, display, read=input):
                    return 0
                selection = choose_session(flow, read=input)
                if selection is None:
                    return 0
            text = input('nexus> ').strip()
            if not text:
                continue
            if text == '/quit':
                return 0
            if text in ('/status', '/sessions'):
                display((flow.observe(session_id=selection.session_id) if selection.session_id else
                    {'state': 'new_session_not_opened'}) if text == '/status' else flow.sessions())
            elif text == '/watch':
                if selection.session_id:
                    watch(flow, timeout=timeout, interactive=True, session_id=selection.session_id)
                else:
                    display({'state': 'new_session_not_opened'})
            elif text == '/resume':
                display(flow.resume())
                selection = SessionSelection(flow.document.get('session_id'))
                watch(flow, timeout=timeout, interactive=True)
            elif text.startswith('/answer '):
                if not selection.session_id:
                    raise ConnectionError('SESSION_REQUIRED', 'Select an existing session before answering its request.')
                decide_interactively(flow, text.removeprefix('/answer ').strip(), session_id=selection.session_id)
            elif text == '/authorize':
                authorize_interactively(flow)
            elif text in ('/interrupt', '/close'):
                if not selection.session_id:
                    raise ConnectionError('SESSION_REQUIRED', 'A new conversation has no session to control.')
                flow.submit(action=text[1:], session_id=selection.session_id)
                watch(flow, timeout=timeout, interactive=True, slot_name='control')
            elif text.startswith('/') and not text.startswith('/new '):
                print('Unknown command. Use /quit to leave or type a project request.')
            else:
                new = text.startswith('/new ')
                flow.submit(text.removeprefix('/new ') if new else text,
                    session_id=None if new else selection.session_id,
                    new_session=new or selection.new_session)
                selection = SessionSelection(flow.document.get('session_id'))
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
    call = service.operator_http if hasattr(service, 'operator_http') else LocalOperatorHTTP(
        host=service.adapter.host, port=service.adapter.port, max_response_bytes=8 * 1048576)
    return TerminalWork(call, save, connection, checkpoint)


def interactive_work(service, profile, *, timeout=300):
    # The calling connect/run_work already owns the shared project profile lock.
    return chat(open_work(service, profile), timeout=timeout)


def inspect_work_service(service, *, timeout=None):
    """Retry only identified local transport interruptions, without lifecycle effects."""
    if timeout is None or hasattr(service, 'operator_http'):
        # Without an explicit budget preserve the single canonical inspection:
        # its default two seconds bound HTTP, not Scheduler/OS inspection.
        # Remote verification retains its own transport/auth contract as well.
        return service.inspect()
    deadline = time.monotonic() + timeout
    anchor = None
    status = {'state': 'unknown', 'ready_for_queries': False}
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return {**status, 'state': 'unknown', 'ready_for_queries': False,
                    'reason': 'READINESS_DEADLINE_EXCEEDED'}
        status = service.inspect(timeout=min(2.0, remaining))
        transient = (status.get('reason') == 'SERVICE_UNREACHABLE'
                     and status.get('observation_retryable') is True)
        # OS I/O is not preemptible by this loop. A late successful response
        # must not authorize a handler after the selected preflight budget.
        if time.monotonic() >= deadline:
            if not transient and status.get('state') not in {'ready', 'stopping'}:
                return {**status, 'readiness_wait_expired': True}
            return {**status, 'state': 'unknown', 'ready_for_queries': False,
                    'reason': 'READINESS_DEADLINE_EXCEEDED'}
        owner = status.get('observed_owner') if transient else status
        identity = ({key: owner.get(key) for key in ('instance_id', 'pid', 'generation')}
                    if isinstance(owner, dict) else None)
        if (anchor is not None and (transient or status.get('state') in {'ready', 'stopping'})
                and identity != anchor):
            return {**status, 'state': 'unknown', 'ready_for_queries': False,
                    'reason': 'INSTANCE_CHANGED'}
        if not transient:
            return status
        if (identity is None or type(identity['pid']) is not int or identity['pid'] <= 0
                or not isinstance(identity['instance_id'], str) or not identity['instance_id']
                or not isinstance(identity['generation'], str) or not identity['generation']):
            return status
        anchor = identity
        time.sleep(min(.1, max(0, deadline - time.monotonic())))


def run_work(argv):
    from .connect import project_profile
    parser = argparse.ArgumentParser(prog='okto-nexus work',
        description='Submit project work and observe or decide canonical runtime requests.')
    args_list = list(argv)
    action = args_list.pop(0) if args_list and args_list[0] in ACTIONS else None
    parser.add_argument('--profile')
    parser.add_argument('--operator-profile', help='use this saved human operator profile on a remote Server')
    parser.add_argument('--project', type=Path)
    parser.add_argument('--message')
    parser.add_argument('--session-id')
    parser.add_argument('--new-session', action='store_true')
    parser.add_argument('--request-id', help='stable client intent ID for an explicit submission/retry')
    parser.add_argument('--target-turn-id')
    parser.add_argument('--approval-id')
    parser.add_argument('--decision', choices=('approve', 'deny'))
    parser.add_argument('--review', help='hash of the exact displayed native question or authorization review')
    parser.add_argument('--minutes', type=int, help='authorize: lifetime from review, 1..1440 minutes (default 60)')
    parser.add_argument('--actions', type=int, help='authorize: runtime action budget, 1..1000 (default 20)')
    parser.add_argument('--answer-file', type=Path, help='UTF-8 JSON native response object, read only for this submission')
    parser.add_argument('--control', action='store_true', help='observe or resume the saved interrupt/close action')
    parser.add_argument('--after-sequence', type=int, default=0)
    parser.add_argument('--stream-epoch')
    parser.add_argument('--timeout', type=float, default=300)
    parser.add_argument('--readiness-timeout', type=float,
                        help='opt in to local readiness retries within (0, 30] seconds; default: one inspection, no service start')
    parser.add_argument('--json', action='store_true')
    args, service_args = parser.parse_known_args(args_list)
    action = action or ('chat' if sys.stdin.isatty() and not args.json else 'status')
    if not 0 < args.timeout <= 300 or args.after_sequence < 0:
        parser.error('timeout must be in (0, 300]; after-sequence must be nonnegative')
    if args.readiness_timeout is not None and not 0 < args.readiness_timeout <= 30:
        parser.error('readiness-timeout must be in (0, 30]')
    if action in ('send', 'steer') and not args.message:
        parser.error('send and steer require --message')
    if args.message is not None and action not in ('send', 'steer', 'interrupt', 'close'):
        parser.error('--message requires send, steer, interrupt or close')
    if (args.decision or args.answer_file) and action != 'answer':
        parser.error('decision options require the answer command')
    if args.review and action not in ('answer', 'authorize'):
        parser.error('--review requires answer or authorize')
    if args.minutes is not None or args.actions is not None:
        if action != 'authorize' or args.review:
            parser.error('authorization limits require authorize without --review')
    if args.minutes is not None and not 1 <= args.minutes <= 1440 or args.actions is not None and not 1 <= args.actions <= 1000:
        parser.error('authorization limits are 1..1440 minutes and 1..1000 actions')
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
    guard = flow = checkpoint = None
    try:
        from .terminal_target import resolve_terminal_target, terminal_target_selection
        project, profile = project_profile(args.project, args.profile)
        # Read durable uncertainty before opening the operator vault/client.
        # Topology selection itself performs no authentication or lifecycle effect.
        home, _ = terminal_target_selection(service_args, profile, args.operator_profile)
        checkpoint_path = home / 'terminal/work' / (profile + '.json')
        checkpoint = read_json(checkpoint_path) if checkpoint_path.exists() else None
        service = resolve_terminal_target(service_args, profile, args.operator_profile, resolve_local_service)
        target = service.adapter.home / 'terminal/profiles' / (profile + '.json')
        if not target.exists():
            raise ConnectionError('CONNECTION_REQUIRED', 'Run connect for this project before using work.')
        status = inspect_work_service(service, timeout=args.readiness_timeout)
        # The inspected owner keeps its administrative channel during drain.
        # Permit only observation and controls of already admitted work; never
        # start a service, reopen admission or resume a productive submission.
        drain_control = (action == 'resume' and args.control and
            isinstance(checkpoint, dict) and isinstance(checkpoint.get('control'), dict) and
            checkpoint['control'].get('intent') in {'turn.interrupt', 'runtime.close'})
        drain_access = (status['state'] == 'stopping' and status.get('ready_for_queries') is True and
            (action in {'status', 'watch', 'events', 'sessions', 'answer', 'interrupt', 'close'} or drain_control))
        if status['state'] != 'ready' and not drain_access:
            display({'state': 'service_not_ready', 'service': status}, args.json)
            return 3
        guard = ExclusiveFileLock(target.with_suffix('.guard'))
        guard.acquire()
        flow = open_work(service, profile)
        if status['state'] == 'stopping' and action == 'resume':
            # Another CLI may replace the checkpoint before this lock is ours.
            # Classify the document actually used by resume, not the early read.
            control = flow.document.get('control')
            if not isinstance(control, dict) or control.get('intent') not in {'turn.interrupt', 'runtime.close'}:
                display({'state': 'service_not_ready', 'service': status}, args.json)
                return 3
        if (args.project is not None or not args.profile) and flow.connection['selection']['project'] != project:
            raise ConnectionError('PROFILE_CONFLICT', 'This profile belongs to another project directory.')
        slot = 'control' if args.control else 'work'
        if action == 'chat':
            return chat(flow, timeout=args.timeout, session_id=args.session_id)
        if (action == 'send' and not args.session_id and not args.new_session
                and not flow.document.get('session_id')):
            from .session_picker import session_inventory, pending_slots
            if not pending_slots(flow):
                sessions = session_inventory(flow)
                if sessions:
                    display(dict(state='selection_required', reason='session_selection_required',
                        effects_started=False, choices=[dict(session_id=row['scope']['session_id'],
                            executor_id=row['scope']['executor_id'], workspace_id=row['scope']['workspace_id'],
                            lifecycle_state=row.get('lifecycle_state'), control_available=row.get('control_available'))
                            for row in sessions]), args.json)
                    return 3
        if action in ('send', 'steer', 'interrupt', 'close'):
            value = flow.submit(args.message, action=action, session_id=args.session_id,
                new_session=args.new_session, client_intent_id=args.request_id, target_turn_id=args.target_turn_id)
        elif action == 'resume':
            value = flow.resume(slot)
        elif action == 'authorize':
            if args.review:
                value = flow.authorize(approval=args.review)
            elif sys.stdin.isatty() and not args.json:
                authorize_interactively(flow, minutes=args.minutes or 60, max_executions=args.actions or 20)
                return 0
            else:
                value = flow.authorization_review(minutes=args.minutes or 60, max_executions=args.actions or 20)
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
        retained = flow.document if flow is not None else checkpoint
        authorization = retained.get('authorization') if isinstance(retained, dict) else None
        pending_effect = isinstance(authorization, dict) and authorization.get('state') == 'submitted'
        possible_effect = bool(getattr(error, 'possible_effect', False) or pending_effect)
        display({'state': 'unconfirmed' if possible_effect else 'refused',
            'code': getattr(error, 'code', 'PROFILE_BUSY' if isinstance(error, LockBusy) else 'CONFIG_ERROR'),
            'message': getattr(error, 'message', 'Inspect the selected service and project profile.'),
            'possible_effect': possible_effect}, args.json)
        return 3
    finally:
        if guard is not None:
            guard.release()

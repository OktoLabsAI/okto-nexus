"""Review exact session actions and recover their canonical terminal receipts."""

import re
from urllib.parse import quote, urlencode
from uuid import uuid4

from ....application.terminal_connection import PREFIX, ConnectionError
from ....application.terminal_work import SCOPE, read_binding_session
from ....domain.session_interaction import (
    MAX_INPUT_BYTES,
    InputDeliveryState,
    validate_input_text,
)
from .native_input import display_text

COMMANDS = ('send', 'steer', 'interrupt')
INTENT = re.compile(r'terminal_(send|steer|interrupt)_[0-9a-f]{32}')
PI_INPUT_INTENT = re.compile(r'pi_input_[0-9a-f]{32}')
PI_STEER_INTENT = re.compile(r'pi_steer_[0-9a-f]{32}')
PI_RUN_REF = re.compile(r'prun_[0-9a-f]{32}')
_HANDLERS = {'send': 'enqueue', 'steer': 'review_steer', 'interrupt': 'review_interrupt'}
_DELIVERY_MESSAGES = {
    InputDeliveryState.DISPATCHING: 'The message is being delivered.',
    InputDeliveryState.ACCEPTED_NATIVE: 'The harness accepted the message.',
    InputDeliveryState.REFUSED_BEFORE_SEND: 'Delivery was refused before the message was sent.',
    InputDeliveryState.DELIVERY_UNKNOWN: 'Delivery is unconfirmed. Check this receipt before sending again.',
    InputDeliveryState.BLOCKED_AUTH: 'The current authorization blocks delivery.',
    InputDeliveryState.BLOCKED_SESSION: 'The selected session blocks delivery.',
    InputDeliveryState.PAUSED: 'The message is held in the paused queue.',
    InputDeliveryState.EXPIRED: 'The message expired in the queue.',
    InputDeliveryState.CANCELLED: 'The queued message was cancelled.',
}


def _identifier(value):
    return isinstance(value, str) and 1 <= len(value) <= 160 and value.isprintable()


def _session(call, binding, session_id):
    if not getattr(call, 'token', None):
        raise ConnectionError('OPERATOR_LOGIN_REQUIRED', 'Sign in with operator login and pass --operator-profile.')
    current = read_binding_session(call, binding, session_id)['scope']
    generation = current.get('session_owner_generation')
    if type(generation) is not int or generation < 1:
        raise ConnectionError('SESSION_UNAVAILABLE', 'The exact session owner is unavailable.')
    scope = {key: current[key] for key in (*SCOPE, 'workspace_binding_id', 'session_id')}
    return PREFIX + '/runtime/sessions/' + quote(session_id, safe=''), scope, generation


def _query(scope, generation, **extra):
    return urlencode({key: value for key, value in scope.items() if key != 'session_id'} |
                     {'expected_session_generation': generation} | extra)


def _matches(value, scope, generation, *, nested=False):
    actual = value.get('scope')
    if not isinstance(actual, dict) or any(actual.get(key) != item for key, item in scope.items()):
        return False
    retained = (actual if nested else value).get('session_owner_generation')
    return type(retained) is int and retained == generation


def _unavailable():
    return ConnectionError('SESSION_COMMAND_UNAVAILABLE', 'This action has no current review for the selected session.')


def _review(call, url, scope, generation, command):
    query = _query(scope, generation)
    try:
        catalog = call('GET', url + '/commands?' + query)
    except ConnectionError as error:
        if error.http_status in (404, 405) and not error.possible_effect:
            raise ConnectionError('SESSION_COMMAND_UNAVAILABLE',
                'The selected Server does not offer session commands for this session.',
                http_status=error.http_status) from None
        raise
    revision = catalog.get('capability_revision')
    items = catalog.get('items')
    if (not _matches(catalog, scope, generation) or catalog.get('version') != 1 or not _identifier(revision)
            or not isinstance(items, list) or len(items) > 100):
        raise _unavailable()
    options = [item for item in items if isinstance(item, dict) and item.get('command_id') == command]
    if (len(options) != 1 or options[0].get('state') != 'supported' or options[0].get('handler') != _HANDLERS[command]
            or options[0].get('requires_confirmation') is not True):
        raise _unavailable()
    body = {'scope': scope, 'expected_session_generation': generation, 'command': command,
            'catalog_revision': revision, 'confirmed': True}
    if command == 'send':
        checked = call('GET', url + '/interaction?' + query)
        capability = checked.get('next_turn')
        if (not _matches(checked, scope, generation, nested=True) or not isinstance(capability, dict)
                or capability.get('supported') is not True or not _identifier(capability.get('capability_revision'))):
            raise _unavailable()
        return body | {'capability_revision': capability['capability_revision']}
    checked = call('GET', url + '/' + command + '?' + query)
    control = checked.get('control')
    if not _matches(checked, scope, generation) or not isinstance(control, dict):
        raise _unavailable()
    revision, queue, target = (control.get(key) for key in ('capability_revision', 'queue_revision', 'target'))
    if not _identifier(revision) or type(queue) is not int or queue < 0 or not isinstance(target, dict):
        raise _unavailable()
    native_turn = (target.keys() == {'kind', 'turn_id'} and target['kind'] == 'native_turn'
                   and _identifier(target['turn_id']))
    pi_run = (command == 'steer' and target.keys() == {'kind', 'run_ref'} and target['kind'] == 'observed_run'
              and isinstance(target['run_ref'], str) and PI_RUN_REF.fullmatch(target['run_ref']))
    if not (native_turn or pi_run):
        raise _unavailable()
    body |= {'capability_revision': revision, 'expected_queue_revision': queue, 'target': target}
    if command == 'steer':
        if (control.get('effect') != ('next_boundary' if pi_run else 'same_turn')
                or not _identifier(control.get('effect_revision'))):
            raise _unavailable()
        body['confirmed_effect_revision'] = control['effect_revision']
    return body


def _message(read, message_file):
    try:
        if message_file is None:
            value = read('Message: ')
        else:
            with message_file.open('rb') as stream:
                value = stream.read(MAX_INPUT_BYTES + 1).decode('utf-8')
        if value.lstrip().startswith(('/', '!')):
            raise ValueError('Use plain text for session messages.')
        return validate_input_text(value)
    except (OSError, ValueError) as error:
        raise ConnectionError('SESSION_MESSAGE_INVALID', 'Provide a non-empty plain-text message in valid UTF-8.') from error


def _receipt(call, url, scope, generation, command, intent):
    resource = 'interrupt' if command == 'interrupt' else 'inputs'
    return call('GET', url + f'/terminal/{resource}/receipt?' + _query(scope, generation, client_intent_id=intent))


def _result(receipt, scope, generation, command, intent):
    interrupt = command == 'interrupt'
    if not _matches(receipt, scope, generation, nested=interrupt):
        raise ConnectionError('SESSION_RECEIPT_UNCONFIRMED', 'The receipt did not match this session.', possible_effect=True)
    if interrupt:
        control = receipt.get('interrupt')
        state = control.get('target_status') if isinstance(control, dict) else None
        if not _identifier(receipt.get('operation_id')) or state not in ('unconfirmed', 'running', 'interrupted', 'finished'):
            raise ConnectionError('SESSION_RECEIPT_UNCONFIRMED', 'The interruption result is unconfirmed.', possible_effect=True)
        message = {'running': 'The selected turn is still running.', 'interrupted': 'The selected turn was interrupted.',
                   'finished': 'The selected turn already finished.',
                   'unconfirmed': 'Interruption requested. The outcome is pending.'}[state]
        if control.get('queue_paused') is True:
            message += ' The message queue is paused.'
    else:
        if not _identifier(receipt.get('input_id')) or receipt.get('reorientation') is not (command == 'steer'):
            raise ConnectionError('SESSION_RECEIPT_UNCONFIRMED', 'The receipt did not match this action.', possible_effect=True)
        try:
            state = InputDeliveryState(receipt.get('status'))
        except ValueError:
            raise ConnectionError('SESSION_RECEIPT_UNCONFIRMED', 'Message delivery is unconfirmed.', possible_effect=True) from None
        if state == InputDeliveryState.QUEUED:
            message = 'Reorientation recorded.' if command == 'steer' else 'Message recorded in the Nexus session queue.'
        else:
            message = _DELIVERY_MESSAGES[state]
        if command == 'steer':
            boundary = receipt.get('steer_boundary')
            if boundary in ('awaiting_boundary', 'applied', 'discarded'):
                if not _identifier(receipt.get('operation_id')) or receipt.get('possible_effect') is not True:
                    raise ConnectionError('SESSION_RECEIPT_UNCONFIRMED',
                        'The reorientation receipt has an unconfirmed boundary.', possible_effect=True)
                message = {'awaiting_boundary': 'Pi queued the reorientation for the next boundary.',
                           'applied': 'Pi applied the reorientation.',
                           'discarded': 'The run ended before Pi applied the reorientation.'}[boundary]
            elif receipt.get('steer_submitted') is True:
                message = 'Reorientation sent. Application is unconfirmed.'
    return {'state': 'recorded', 'message': message, 'command': command, 'client_intent_id': intent,
            'receipt': receipt}


def execute_session_command(call, binding, session_id, command, *, interactive, message_file, read=input, write=print):
    if not interactive:
        raise ConnectionError('SESSION_COMMAND_TTY_REQUIRED', 'Use an interactive terminal to review and confirm this action.')
    url, scope, generation = _session(call, binding, session_id)
    body = _review(call, url, scope, generation, command)
    try:
        if command != 'interrupt':
            text = _message(read, message_file)
            body['content'] = [{'type': 'text', 'text': text}]
            if message_file is not None:
                write(display_text(text[:200]) + (' …' if len(text) > 200 else ''))
        write('Session ' + display_text(session_id))
        if command == 'send':
            prompt = 'Queue this message for the next turn? [y/N] '
        elif body['target']['kind'] == 'observed_run':
            prompt = 'Reorient the selected Pi run at its next available boundary? [y/N] '
        else:
            write('Turn ' + display_text(body['target']['turn_id']))
            prompt = ('Reorient this exact turn now? [y/N] ' if command == 'steer'
                      else 'Interrupt this exact turn and pause the queue? [y/N] ')
        if read(prompt).strip().lower() not in ('y', 'yes'):
            return {'state': 'cancelled', 'message': 'Action cancelled.'}
    except EOFError:
        return {'state': 'cancelled', 'message': 'Action cancelled.'}

    intent = 'terminal_' + command + '_' + uuid4().hex
    write(f'Receipt for session {display_text(session_id)}, owner generation {generation}, intent {intent}.')
    try:
        receipt = call('POST', url + '/terminal/commands:execute', body | {'client_intent_id': intent})
        if command != 'interrupt':
            return _result(receipt, scope, generation, command, intent)
    except ConnectionError as error:
        if not error.possible_effect and (error.http_status is None or error.http_status < 500):
            raise
    try:
        return _result(_receipt(call, url, scope, generation, command, intent), scope, generation, command, intent)
    except ConnectionError:
        return {'state': 'unconfirmed', 'message': 'Outcome unconfirmed. Use session receipt with the same session, owner generation and intent.',
                'client_intent_id': intent, 'session_owner_generation': generation}


def recover_session_command(call, binding, session_id, generation, intent):
    url, scope, current = _session(call, binding, session_id)
    if generation > current:
        raise _unavailable()
    if PI_INPUT_INTENT.fullmatch(intent) or PI_STEER_INTENT.fullmatch(intent):
        return recover_pi_input(call, scope, generation, intent)
    command = INTENT.fullmatch(intent)[1]
    return _result(_receipt(call, url, scope, generation, command, intent), scope, generation, command, intent)


def recover_pi_input(call, scope, generation, intent):
    route = PREFIX + '/runtime/sessions/' + quote(scope['session_id'], safe='') + '/presenter/inputs/receipt?'
    receipt = call('GET', route + _query(scope, generation, client_intent_id=intent))
    return _result(receipt, scope, generation, 'steer' if PI_STEER_INTENT.fullmatch(intent) else 'send', intent)

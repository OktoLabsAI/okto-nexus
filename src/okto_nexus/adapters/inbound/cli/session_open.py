"""Open one empty terminal session after its own confirmation and grant check."""

import re
import time
from typing import Literal
from urllib.parse import quote
from uuid import uuid4

from ....application.terminal_connection import ConnectionError, PREFIX, document_revision
from ....application.terminal_work import SCOPE, SUBMISSION, read_binding_session
from ...outbound.service_manager.context import atomic_json
from ...outbound.service_manager.locking import ExclusiveFileLock, LockBusy
from .connection_choices import _directory, _read
from .native_input import display_text

_SCOPE = (*SCOPE, 'workspace_binding_id')


def _checkpoint(path):
    try:
        return _read(path)
    except FileNotFoundError:
        return None
    except ValueError:
        if not path.exists() and not path.is_symlink():
            return None
        raise


def _admit_empty(call, binding, checkpoint, save, *, recovery, confirmed_in_viewer):
    intent = checkpoint['intent']
    route = PREFIX + '/runtime/intents/' + intent
    recovered = None
    if recovery:
        try:
            recovered = call('GET', route)
        except ConnectionError as error:
            if error.http_status != 404:
                raise

    operation = recovered['operation'] if recovered is not None else None
    if operation is None and recovery:
        print(f'Opening receipt {intent} has no recorded admission.')
        if confirmed_in_viewer:
            raise ConnectionError('OPENING_PENDING', 'Use session open to review the pending opening before requesting '
                                  'another session.', possible_effect=True)
        if input('Continue this same empty-session request? [y/N] ').strip().lower() != 'y':
            raise ConnectionError('OPENING_PENDING', 'The original opening remains available for recovery.', possible_effect=True)

    if operation is None and checkpoint['binding_revision'] != binding['binding_revision']:
        raise ConnectionError('OPENING_SCOPE_CHANGED', 'The binding changed. Review the opening receipt before continuing.')
    request = {'client_intent_id': intent, 'intent': 'runtime.start',
               'agent_id': binding['agent_id'], 'binding_id': binding['binding_id'],
               'workspace_binding_id': binding['workspace_binding_id']}
    # Checkpoints issued before explicit empty openings used the default
    # selection. Keep their original request shape during recovery.
    if checkpoint['format'] == 2:
        request['new_session'] = True
    try:
        resolution = recovered['resolution'] if recovered is not None else call(
            'POST', PREFIX + '/runtime/intents:resolve', request)
        scope = resolution['scope']
        session_id = scope['session_id']
        if (any(scope.get(field) != binding[field] for field in _SCOPE)
                or scope.get('binding_revision') != checkpoint['binding_revision']
                or not isinstance(session_id, str) or not 1 <= len(session_id) <= 160
                or not session_id.isprintable() or resolution.get('session_id') != session_id
                or resolution.get('client_intent_id') != intent
                or resolution['semantic_intent'].get('action') != 'runtime.open'
                or resolution.get('saved_resume') is not None
                or recovered is not None and recovered['initial_turn_operation_id'] is not None):
            raise ConnectionError('OPENING_RECEIPT_MISMATCH', 'The opening receipt does not match the confirmed request.', possible_effect=True)
        if resolution.get('reuse') or not resolution.get('can_submit'):
            raise ConnectionError('CONFLICT', 'The connection is unavailable for an empty opening. Inspect the connection and its current sessions.')
        if operation is None:
            operation = call('POST', PREFIX + '/runtime/operations', {key: resolution[key] for key in SUBMISSION})
    except ConnectionError as error:
        if not error.possible_effect and operation is None and error.code in ('PERMISSION_DENIED', 'CONFLICT', 'VALIDATION_ERROR'):
            save(checkpoint | {'state': 'settled'})
            if error.code == 'PERMISSION_DENIED':
                raise ConnectionError(error.code, 'Review the project execution authorization with work authorize before opening an empty session.') from error
        raise
    return scope, operation, resolution['operation_id'], resolution['intent_hash']


def _wait_for_opening(call, binding, scope, operation, operation_id, intent_hash) -> Literal['ready', 'refused', 'ended']:
    path = PREFIX + '/runtime/operations/' + quote(operation_id, safe='')
    deadline = time.monotonic() + 30
    while True:
        if (operation.get('operation_id') != operation_id or operation.get('action') != 'runtime.open'
                or operation.get('intent_hash') != intent_hash or operation.get('scope') != scope):
            raise ConnectionError('OPENING_RECEIPT_MISMATCH', 'The Server returned a different opening operation.', possible_effect=True)
        stage = operation.get('executor_stage')
        if stage == 'OUTCOME_UNKNOWN':
            break
        if stage in ('FAILED', 'CANCELLED') and operation.get('possible_effect') is False:
            return 'refused'
        if stage in ('SUBMITTED', 'SUCCEEDED'):
            session = read_binding_session(call, binding, scope['session_id'])
            if session['scope'].get('session_owner_generation') != scope['session_owner_generation']:
                break
            if (session.get('lifecycle_state') in ('CLOSED', 'FAILED')
                    and session.get('lease_state') == 'CLOSED' and session.get('control_available') is False):
                return 'ended'
            if session.get('control_available') is True:
                return 'ready'
        if time.monotonic() >= deadline:
            break
        time.sleep(.25)
        operation = call('GET', path)
    raise ConnectionError('OPENING_PENDING', f'Opening is unconfirmed. Inspect receipt {operation_id} or run the same command to recover it.', possible_effect=True)


def empty_session(service, call, binding, *, allow_new=False, confirmed_in_viewer=False):
    """Recover an exact pending opening or separately confirm a first empty one."""
    if not getattr(call, 'token', None):
        return None
    home = service.adapter.home
    scope = {field: binding[field] for field in _SCOPE}
    directory = home / 'terminal/session-openings'
    _directory(home / 'terminal')
    _directory(directory)
    if directory.resolve() != directory:
        raise ValueError('Invalid session opening directory')
    path = directory / (document_revision(scope) + '.json')
    prior = _checkpoint(path)
    if not allow_new and (prior is None or prior.get('state') == 'settled'):
        return None
    directory.mkdir(parents=True, exist_ok=True)
    guard = ExclusiveFileLock(path.with_suffix('.guard'))
    try:
        guard.acquire()
    except LockBusy as error:
        raise ConnectionError('OPENING_BUSY', 'Another terminal is checking this connection’s opening receipt.') from error
    try:
        prior = _checkpoint(path)
        actor = {'origin': call.base, 'username': call.username}
        pending = prior is not None and prior.get('state') != 'settled'
        if pending:
            if (prior.get('format') not in (1, 2) or prior.get('state') != 'pending' or prior.get('scope') != scope
                    or prior.get('actor') != actor or not isinstance(prior.get('intent'), str)
                    or not re.fullmatch(r'empty_open_[0-9a-f]{32}', prior['intent'])):
                raise ConnectionError('OPENING_CHECKPOINT_UNCONFIRMED', 'The saved opening belongs to a different scope or operator.')
            checkpoint = prior
        elif not allow_new:
            return None
        else:
            policy = call('GET', '/api/v1/agents/' + quote(binding['agent_id'], safe='') + '/runtime-policy')['data']['effective']
            if policy['session_policy'] == 'one_shot':
                raise ConnectionError('OPENING_POLICY_REFUSED', 'This connection opens a session per message or handoff.')
            print(f"An empty session will use the existing execution authorization and policy ({display_text(policy['session_policy'])}). No prompt will be sent.")
            if not confirmed_in_viewer and input('Open an empty session? [y/N] ').strip().lower() != 'y':
                return None
            checkpoint = {'format': 2, 'state': 'pending', 'scope': scope, 'actor': actor,
                          'intent': 'empty_open_' + uuid4().hex, 'binding_revision': binding['binding_revision']}
            atomic_json(path, checkpoint)

        def save(value):
            atomic_json(path, value)

        print('Opening request ' + checkpoint['intent'])
        admitted_scope, operation, operation_id, intent_hash = _admit_empty(
            call, binding, checkpoint, save, recovery=pending, confirmed_in_viewer=confirmed_in_viewer)
        state = _wait_for_opening(call, binding, admitted_scope, operation, operation_id, intent_hash)
        session_id = admitted_scope['session_id']
        save(checkpoint | {'state': 'settled', 'operation_id': operation_id, 'session_id': session_id})
        if state == 'ended':
            raise ConnectionError('OPENING_CLOSED', f'Opening receipt {operation_id} confirms session {session_id}. '
                                  'The session has ended.', possible_effect=True)
        if state == 'refused':
            raise ConnectionError('OPENING_FAILED', f'Opening {operation_id} was refused before launch. Review the project execution authorization and receipt.')
        return session_id
    finally:
        guard.release()

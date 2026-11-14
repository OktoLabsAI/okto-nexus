"""Offline candidate primitives, NOT an authorized or integrated campaign runner.

Only supplied canonical GET transports and supplied stop-owner capability are used.
The watchdog bounds selection of a stop; it cannot prove process exit or account
for tokens while an external synchronous collector is blocked.
"""
from copy import deepcopy
import re
import threading
import time
from urllib.parse import quote, urlsplit

SCOPE = ('server_id', 'executor_id', 'binding_id', 'agent_id', 'workspace_id', 'session_id')
TERMINAL = frozenset(('SUCCEEDED', 'FAILED', 'CANCELLED'))
PREFIX = '/api/v1/runtime-management'
KNOWN_CODES = frozenset(('SERVER_UNREACHABLE', 'OUTCOME_UNKNOWN', 'RESPONSE_UNCONFIRMED',
    'EVENT_STREAM_UNAVAILABLE', 'PREPARATION_FAILED', 'DB_ERROR', 'SCOPE_MISMATCH',
    'WORK_SCOPE_CHANGED', 'WORK_RECEIPT_MISMATCH', 'NOT_FOUND', 'INTENT_NOT_FOUND',
    'PROFILE_DRIFT', 'AUTH_FAILED', 'OPERATION_CONFLICT', 'DEADLINE_REACHED'))
KNOWN_STAGES = frozenset(('http', 'unknown', 'm1_response_loss', 'authentication',
    'local_configuration', 'agent runtime history', 'observation', 'transport'))


class ObservationInvalid(RuntimeError):
    pass


def route_template(path):
    # Never retain query values, arbitrary identifiers, URLs or unknown paths.
    route = urlsplit(path).path
    fixed = (PREFIX + '/connections/me', PREFIX + '/runtime/intents:resolve',
             PREFIX + '/runtime/operations', PREFIX + '/runtime/approval-decisions')
    if route in fixed:
        return route
    for section in ('runtime/intents', 'runtime/operations', 'runtime/approval-decisions',
                    'connections/bindings', 'runtime/sessions'):
        base = PREFIX + '/' + section + '/'
        if route.startswith(base):
            tail = route[len(base):].split('/')
            if len(tail) == 1 and tail[0]:
                return base + ':id'
            if section == 'runtime/sessions' and len(tail) == 2 and tail[1] == 'events':
                return base + ':id/events'
    if route == '/api/v1/approvals':
        return route
    if route.startswith('/api/v1/approvals/') and route.count('/') == 4:
        return '/api/v1/approvals/:id'
    return 'OTHER_ROUTE'


def diagnostic(error, method, path):
    code, stage = getattr(error, 'code', None), getattr(error, 'stage', None)
    name = type(error).__name__
    return {'exception_type': name if re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,79}', name) else 'Exception',
            'method': method if method in ('GET', 'POST') else 'OTHER',
            'route': route_template(path), 'code': code if type(code) is str and code in KNOWN_CODES else 'OTHER',
            'stage': stage if type(stage) is str and stage in KNOWN_STAGES else 'OTHER',
            'possible_effect': getattr(error, 'possible_effect', None)
                if type(getattr(error, 'possible_effect', None)) is bool else None}


class FailureHistory:
    def __init__(self):
        self.primary = None
        self.later = []
        self.discarded = 0

    def record(self, error, method, path):
        item = diagnostic(error, method, path)
        if self.primary is None:
            self.primary = item
        elif len(self.later) < 15:
            self.later.append(item)
        else:
            self.discarded += 1

    def snapshot(self):
        return deepcopy({'primary': self.primary, 'later': self.later, 'discarded': self.discarded})


def _scope(value, expected):
    actual = value.get('scope', {})
    if any(actual.get(k) != expected[k] for k in SCOPE):
        raise ObservationInvalid('SCOPE_MISMATCH')


def read_control(get, control, expected):
    """GET only, including unresolved/blocked intent; never calls resume/submit."""
    intent = control['client_intent_id']
    receipt = get(PREFIX + '/runtime/intents/' + quote(intent, safe=''))
    resolution = receipt['resolution']
    if resolution['client_intent_id'] != intent:
        raise ObservationInvalid('INTENT_MISMATCH')
    _scope(resolution, expected)
    if resolution.get('semantic_intent', {}).get('action') != control['intent']:
        raise ObservationInvalid('ACTION_MISMATCH')
    operation = receipt.get('operation')
    if operation is None:
        return {'state': 'BLOCKED' if resolution.get('can_submit') is False else 'UNCONFIRMED',
                'client_intent_id': intent, 'operation_id': resolution.get('operation_id'),
                'control_terminal': False, 'native_exit_confirmed': False, 'replayed': False}
    _scope(operation, expected)
    operation_id = operation['operation_id']
    if operation_id != resolution['operation_id']:
        raise ObservationInvalid('OPERATION_MISMATCH')
    current = get(PREFIX + '/runtime/operations/' + quote(operation_id, safe=''))
    _scope(current, expected)
    if current['operation_id'] != operation_id or current.get('action') != control['intent']:
        raise ObservationInvalid('OPERATION_MISMATCH')
    stage = current.get('executor_stage')
    return {'state': stage if stage in TERMINAL else 'UNCONFIRMED', 'client_intent_id': intent,
            'operation_id': operation_id, 'control_terminal': stage in TERMINAL,
            'native_exit_confirmed': False, 'replayed': False}


def read_preopen_failure(get, client_intent_id, expected):
    """Correlate a failed opening before attempting a nonexistent event stream.

    Failure stays failure, keeps its reservation, and does not assert billed zero.
    This receipt alone does not replace independent native/slot retirement proof.
    """
    receipt = get(PREFIX + '/runtime/intents/' + quote(client_intent_id, safe=''))
    resolution = receipt['resolution']
    if resolution['client_intent_id'] != client_intent_id:
        raise ObservationInvalid('INTENT_MISMATCH')
    _scope(resolution, expected)
    opening = receipt.get('operation')
    if opening is None:
        return None
    _scope(opening, expected)
    if opening['operation_id'] != resolution['operation_id'] or opening.get('action') != 'runtime.open':
        raise ObservationInvalid('OPENING_MISMATCH')
    if not (opening.get('executor_stage') == 'FAILED' and opening.get('possible_effect') is False
            and (opening.get('error') or {}).get('code') == 'PREPARATION_FAILED'):
        return None
    session = get(PREFIX + '/runtime/sessions/' + quote(expected['session_id'], safe='') +
                  '?executor_id=' + quote(expected['executor_id'], safe=''))
    _scope(session, expected)
    if session.get('stream_epoch') is not None:
        return None
    return {'state': 'FAILED_BEFORE_STREAM', 'opening_operation_id': opening['operation_id'],
            'initial_turn_operation_id': receipt.get('initial_turn_operation_id'),
            'error_code': 'PREPARATION_FAILED', 'possible_effect': False,
            'session_closed': session.get('lifecycle_state') == 'CLOSED' and session.get('lease_state') == 'CLOSED',
            'reservation_preserved': True, 'useful_result_confirmed': False,
            'native_exit_confirmed': False, 'billed_tokens': None}


def next_observation_action(record, owner_stop):
    if record.get('settled'):
        return 'ACCOUNTING_SETTLED'
    selected = record.get('stop_selected')
    if not selected:
        return 'CONTINUE'
    if selected['action'] in ('interrupt', 'close'):
        return 'GET_CONTROL_AND_WORK'
    if selected['action'] == 'stop_owner' and owner_stop is not None and owner_stop.get('returned') is True:
        return 'HANDOFF_FOR_EXIT_PROOF'
    return 'CONTINUE'


class DeadlineFence:
    """Independent deadline selection, no Controller mutation in watchdog thread.

    on_stop must durably reserve the already authorized one-shot owner stop before
    dispatch. Its own returned handle is retained by the owner. It is called once,
    even if it raises; no retry/force. A POST already in flight remains uncertain.
    This bounds stop selection, not native exit or synchronous token collection.
    """
    def __init__(self, seconds, on_stop, *, clock=time.monotonic, interval=.05):
        if seconds <= 0 or not 0 < interval <= .2:
            raise ValueError('invalid deadline')
        self.clock, self.deadline = clock, clock() + seconds
        self.on_stop, self.interval = on_stop, interval
        self._lock = threading.Lock()
        self._done = threading.Event()
        self.fenced = threading.Event()
        self.selection = None
        self._thread = None

    def select(self, reason='DEADLINE_REACHED'):
        with self._lock:
            if self.selection is not None:
                return
            self.fenced.set()
            self.selection = {'reason': reason, 'stop_selected': True, 'stop_returned': False,
                              'native_exit_confirmed': False, 'replayed': False}
        try:
            self.on_stop()
        except BaseException as error:
            with self._lock:
                self.selection['error_type'] = type(error).__name__
        else:
            with self._lock:
                self.selection['stop_returned'] = True

    def check(self):
        if self.clock() >= self.deadline:
            self.select()

    def before_request(self, method):
        self.check()
        if method != 'GET' and self.fenced.is_set():
            raise ObservationInvalid('DEADLINE_REACHED')

    def start(self):
        if self._thread is not None:
            raise RuntimeError('watchdog already started')
        def watch():
            while not self._done.wait(self.interval):
                self.check()
                if self.fenced.is_set():
                    return
        self._thread = threading.Thread(target=watch, name='candidate-deadline-watchdog')
        self._thread.start()

    def close(self):
        self._done.set()
        if self._thread is not None:
            self._thread.join()


class ObservedTransport:
    def __init__(self, transport, history, fence):
        self.transport, self.history, self.fence = transport, history, fence

    def __call__(self, method, path, body=None):
        self.fence.before_request(method)
        try:
            return self.transport(method, path, body)
        except Exception as error:
            self.history.record(error, method, path)
            raise

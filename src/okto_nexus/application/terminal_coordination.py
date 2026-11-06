"""Thin coordination client: durable intent metadata, canonical MCP, passive wait."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import re
import time

from .terminal_connection import ConnectionError

OPERATIONS = ('message_create', 'handoff_create')
FIELDS = {
    'message_create': {'body', 'subject', 'target', 'channel_id', 'artifacts', 'parent_message_id',
                       'trace_id', 'no_reply', 'from_session_id', 'session_secret'},
    'handoff_create': {'payload', 'target', 'visibility', 'trace_id', 'acceptance_criteria',
                       'verify_by', 'depends_on', 'session_id', 'session_secret'},
}
STATES = {'created', 'pending_approval', 'approved_awaiting_execution', 'rejected',
          'approval_archived', 'approval_removed', 'resource_removed', 'expired'}
REFERENCE = {'server_id', 'actor_agent_id', 'workspace_id', 'operation', 'client_request_id',
             'state', 'resource_id', 'approval_id', 'created_at', 'expires_at'}


def utc_now():
    return datetime.now(timezone.utc)


def timestamp(value):
    if type(value) is not str:
        raise ValueError('Missing timestamp')
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ValueError('Expected UTC timestamp')
    return parsed


def _require(condition):
    # Checkpoints and Server responses are runtime input. Their validation must
    # remain active when Python runs with optimization enabled.
    if not condition:
        raise ValueError('Invalid coordination contract')


def request_id(value):
    if type(value) is not str or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,127}', value):
        raise ConnectionError('REQUEST_ID_INVALID', 'Use a 1..128 character ASCII request ID starting with a letter or digit.')
    return value


def intent_hash(value):
    try:
        raw = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
        return hashlib.sha256(raw.encode()).hexdigest()
    except (ValueError, TypeError, UnicodeError):
        raise ConnectionError('REQUEST_INVALID', 'Use valid finite JSON for the original request.') from None


class TerminalCoordination:
    def __init__(self, mcp, scope, save, checkpoint=None, *, now=utc_now,
                 monotonic=time.monotonic, sleep=time.sleep):
        self.mcp, self.scope, self.save = mcp, dict(scope), save
        self.document = deepcopy(checkpoint) if checkpoint is not None else None
        self.now, self.monotonic, self.sleep = now, monotonic, sleep
        if self.document is not None:
            self.validate()

    def validate(self):
        try:
            doc = self.document
            _require(set(doc) <= {'revision', 'scope', 'operation', 'client_request_id', 'intent_hash', 'state',
                'context', 'local_first', 'local_last', 'local_deadline', 'server_first', 'server_last', 'server_deadline', 'receipt'})
            _require(doc['revision'] == 1 and doc['scope'] == self.scope)
            _require(doc['operation'] in OPERATIONS)
            request_id(doc['client_request_id'])
            _require(re.fullmatch('[0-9a-f]{64}', doc['intent_hash']))
            _require(doc['state'] in ('prepared', 'uncertain', 'refused', 'confirmed'))
            _require(set(doc['context']) <= {'session_id', 'from_session_id'})
            for prefix in ('local', 'server'):
                first, last, deadline = (timestamp(doc[f'{prefix}_{name}']) for name in ('first', 'last', 'deadline'))
                _require(first <= last and deadline == first + timedelta(days=30))
            if doc.get('receipt') is not None:
                self._reference(doc['receipt'], doc['operation'], doc['client_request_id'])
        except (KeyError, TypeError, ValueError, ConnectionError):
            raise ConnectionError('CHECKPOINT_INVALID', 'Preserve the invalid coordination checkpoint for review; no request was sent.') from None

    def discover(self, *, observation=False):
        discovery = self.mcp.discover()
        try:
            info, schemas = discovery['info'], discovery['schemas']
            contract = info['coordination_requests']
            _require(contract['revision'] == 1 and type(contract['retention_days']) is int and contract['retention_days'] == 30)
            _require(set(contract['operations']) == set(OPERATIONS))
            _require(contract['recovery_tool'] == 'coordination_request_get' and contract['response'] == 'references')
            observed = timestamp(contract['observed_at'])
            for name in OPERATIONS:
                _require({'client_request_id', 'workspace_id', 'from_agent_id'} <= schemas[name]['properties'].keys())
            _require({'workspace_id', 'operation', 'client_request_id'} <= schemas['coordination_request_get']['properties'].keys())
            if observation:
                support = info['coordination_observation']
                _require(support['revision'] == 1 and support['passive'] is True and support['workspace_selector'] is True)
                for name in ('handoff_get', 'event_cursor', 'event_wait'):
                    _require({'passive', 'workspace_id', 'agent_id'} <= schemas[name]['properties'].keys())
        except (KeyError, TypeError, ValueError):
            raise ConnectionError('SERVER_UPGRADE_REQUIRED',
                'This Server does not advertise the required durable coordination or passive observation contract. No legacy replay fallback is used.') from None
        return observed

    def _store(self):
        self.save(deepcopy(self.document))

    def _check_time(self, observed, *, replay):
        doc, local = self.document, self.now()
        if local < timestamp(doc['local_last']) or observed < timestamp(doc['server_last']):
            raise ConnectionError('REQUEST_CLOCK_CHANGED', 'A clock moved backwards. Review this request before any replay.')
        if replay and (local >= timestamp(doc['local_deadline']) or observed >= timestamp(doc['server_deadline'])):
            raise ConnectionError('REQUEST_WINDOW_EXPIRED', 'The original replay window elapsed. Inspect the same ID and request human review; do not create a replacement automatically.')
        doc.update(local_last=local.isoformat(), server_last=observed.isoformat())

    def _reference(self, value, operation, identity):
        if type(value) is not dict or set(value) != REFERENCE:
            raise ValueError('Invalid receipt fields')
        expected = dict(server_id=self.scope['server_id'], actor_agent_id=self.scope['agent_id'],
            workspace_id=self.scope['workspace_id'], operation=operation, client_request_id=identity)
        if any(value.get(key) != expected_value for key, expected_value in expected.items()):
            raise ValueError('Receipt scope changed')
        created, expires = timestamp(value['created_at']), timestamp(value['expires_at'])
        if expires != created + timedelta(days=30) or value['state'] not in STATES:
            raise ValueError('Invalid receipt window/state')
        for key in ('resource_id', 'approval_id'):
            if value[key] is not None and (type(value[key]) is not str or not value[key] or len(value[key]) > 160):
                raise ValueError('Invalid reference')
        if value['resource_id'] is None and value['approval_id'] is None:
            raise ValueError('Missing resource/approval')
        if value['state'] in ('created', 'resource_removed') and value['resource_id'] is None:
            raise ValueError('Missing canonical resource')
        if value['state'] not in ('created', 'resource_removed', 'expired') and value['approval_id'] is None:
            raise ValueError('Missing canonical approval')
        return {key: value[key] for key in REFERENCE}

    def _accept(self, result, operation, identity, *, save=True):
        try:
            receipt = self._reference(result['request_receipt'], operation, identity)
            _require(result['status'] == receipt['state'] and result['workspace_id'] == self.scope['workspace_id'])
            previous = self.document.get('receipt') if self.document else None
            if previous:
                _require((previous['created_at'], previous['expires_at'], previous['approval_id']) == (
                    receipt['created_at'], receipt['expires_at'], receipt['approval_id']))
                _require(previous['resource_id'] is None or previous['resource_id'] == receipt['resource_id'])
        except (KeyError, TypeError, ValueError):
            raise ConnectionError('REQUEST_RESULT_UNCONFIRMED', 'The Server reference does not match the original request. Inspect it before any replay.', possible_effect=True) from None
        if save and self.document is not None:
            self.document.update(receipt=receipt, state='confirmed')
            try:
                self._store()
            except Exception:
                raise ConnectionError('CHECKPOINT_WRITE_UNCONFIRMED', 'The canonical result was received but could not be saved. Recover the same request ID.', possible_effect=True) from None
        return dict(format=1, state=receipt['state'], scope=self.scope, operation=operation,
            client_request_id=identity, request_receipt=receipt, possible_effect=False,
            **({'message_id' if operation == 'message_create' else 'handoff_id': receipt['resource_id']} if receipt['resource_id'] else {}),
            **({'approval_id': receipt['approval_id']} if receipt['approval_id'] else {}))

    def inspect(self, operation, identity):
        request_id(identity)
        self.discover()
        try:
            result = self.mcp.call('coordination_request_get', dict(workspace_id=self.scope['workspace_id'],
                operation=operation, client_request_id=identity))
        except ConnectionError as error:
            if error.code != 'NOT_FOUND':
                raise
            if self.document and self.document.get('receipt'):
                raise ConnectionError('REQUEST_RECEIPT_MISSING', 'A previously confirmed receipt is missing. Review it; do not recreate the object.', possible_effect=True) from None
            raise ConnectionError('NOT_FOUND', 'No retained receipt was found. Absence does not prove that this request never committed.', possible_effect=True) from None
        return self._accept(result, operation, identity, save=False)

    def submit(self, operation, identity, arguments, *, observation=False):
        request_id(identity)
        if operation not in OPERATIONS or type(arguments) is not dict or set(arguments) - FIELDS[operation]:
            raise ConnectionError('REQUEST_INVALID', 'Use only the public fields of the selected creation tool.')
        arguments = deepcopy(arguments)
        if self.document:
            if (operation, identity) != (self.document['operation'], self.document['client_request_id']):
                raise ConnectionError('REQUEST_CONFLICT', 'The checkpoint belongs to another request.')
            for key, value in self.document['context'].items():
                arguments.setdefault(key, value)
        semantic = {key: value for key, value in arguments.items() if key != 'session_secret'}
        digest = intent_hash(dict(operation=operation, scope=self.scope, arguments=semantic))
        if self.document and digest != self.document['intent_hash']:
            raise ConnectionError('REQUEST_CONFLICT', 'The original target, content and context must be unchanged. Use a separately requested new ID for new work.')
        observed = self.discover(observation=observation)
        if self.document:
            self._check_time(observed, replay=False)
            try:
                result = self.mcp.call('coordination_request_get', dict(workspace_id=self.scope['workspace_id'],
                    operation=operation, client_request_id=identity))
            except ConnectionError as error:
                if error.code != 'NOT_FOUND':
                    raise
                if self.document.get('receipt'):
                    raise ConnectionError('REQUEST_RECEIPT_MISSING', 'A previously confirmed receipt is missing. Review it; do not recreate the object.', possible_effect=True) from None
            else:
                return self._accept(result, operation, identity)
            self._check_time(observed, replay=True)
        else:
            local = self.now()
            self.document = dict(revision=1, scope=self.scope, operation=operation,
                client_request_id=identity, intent_hash=digest, state='prepared',
                context={key: value for key, value in semantic.items() if key in ('session_id', 'from_session_id')},
                local_first=local.isoformat(), local_last=local.isoformat(), local_deadline=(local + timedelta(days=30)).isoformat(),
                server_first=observed.isoformat(), server_last=observed.isoformat(), server_deadline=(observed + timedelta(days=30)).isoformat())
        # Both the ID and possible-transmission state survive process death.
        self.document['state'] = 'uncertain'
        try:
            self._store()  # A failed write means no productive call.
        except Exception:
            raise ConnectionError('CHECKPOINT_WRITE_FAILED', 'The request checkpoint could not be saved. No productive call was sent by this attempt.') from None
        try:
            result = self.mcp.call(operation, dict(arguments, workspace_id=self.scope['workspace_id'],
                from_agent_id=self.scope['agent_id'], client_request_id=identity))
        except ConnectionError as error:
            if not error.possible_effect:
                self.document['state'] = 'refused'
                self._store()
            raise
        except BaseException:
            # Keep the on-disk uncertain state, including on Ctrl+C.
            raise
        return self._accept(result, operation, identity)

    def wait(self, handoff_id, *, timeout=300):
        self._timeout(timeout)
        self.discover(observation=True)
        return self._wait_handoff(handoff_id, timeout=timeout)

    @staticmethod
    def _timeout(value):
        if type(value) not in (float, int) or not math.isfinite(value) or not 0 <= value <= 86400:
            raise ConnectionError('OBSERVATION_TIMEOUT_INVALID', 'Use a finite observation timeout between zero and 86400 seconds.')

    def _wait_handoff(self, handoff_id, *, timeout):
        deadline = self.monotonic() + timeout
        args = dict(workspace_id=self.scope['workspace_id'], agent_id=self.scope['agent_id'], passive=True)
        cursor = self.mcp.call('event_cursor', dict(args, stream='handoff'))['cursor']
        if type(cursor) is not int or cursor < 0:
            raise ConnectionError('EVENT_CURSOR_UNCONFIRMED', 'The Server returned an invalid observation cursor.')
        while True:
            value = self.mcp.call('handoff_get', dict(args, handoff_id=handoff_id))
            if value.get('handoff_id') != handoff_id:
                raise ConnectionError('HANDOFF_RESULT_UNCONFIRMED', 'The Server returned a different handoff.')
            status = value.get('status')
            if status not in ('OPEN', 'CLAIMED', 'VERIFYING', 'COMPLETED', 'REJECTED', 'CANCELLED'):
                raise ConnectionError('HANDOFF_RESULT_UNCONFIRMED', 'The Server did not confirm a known handoff state.')
            output = dict(format=1, scope=self.scope, handoff_id=handoff_id, handoff=value, possible_effect=False)
            if status == 'COMPLETED':
                return dict(output, state='completed', exit_code=0)
            if status in ('REJECTED', 'CANCELLED'):
                return dict(output, state=status.lower(), exit_code=3)
            remaining = deadline - self.monotonic()
            if remaining <= 0:
                return dict(output, state='timed_out', exit_code=4)
            page = self.mcp.call('event_wait', dict(args, stream='handoff', cursor=cursor,
                filters={'handoff_id': handoff_id}, timeout_seconds=min(30, remaining)),
                timeout=min(35, remaining + 2))
            following = page.get('next_cursor')
            if type(following) is not int or following < cursor:
                raise ConnectionError('EVENT_CURSOR_UNCONFIRMED', 'The observation cursor did not advance safely.')
            cursor = following
            # Always reread: creators can read results while their events are hidden.

    def wait_request(self, result, *, timeout=300):
        self._timeout(timeout)
        self.discover(observation=True)
        deadline = self.monotonic() + timeout
        while True:
            if result.get('handoff_id') and result['state'] == 'created':
                return self._wait_handoff(result['handoff_id'], timeout=max(0, deadline - self.monotonic()))
            if result['state'] not in ('pending_approval', 'approved_awaiting_execution'):
                return dict(result, exit_code=3)
            remaining = deadline - self.monotonic()
            if remaining <= 0:
                return dict(result, state='timed_out', exit_code=4)
            self.sleep(min(2, remaining))
            result = self.inspect(result['operation'], result['client_request_id'])

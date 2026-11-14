"""Finite M1 client instrumentation, not a product transport or provider proxy.

Wrap the existing decoded operator callable. Never receives HTTP headers. Two
explicitly armed faults maximum; no automatic retry or provider calls. Use one
serial controller and one state file shared by the local/connector lanes.
"""
from copy import deepcopy
import json
import os
from pathlib import Path
import threading

from okto_nexus.application.terminal_connection import ConnectionError, PREFIX

ROUTES = {'admission': PREFIX + '/runtime/operations',
          'decision': PREFIX + '/runtime/approval-decisions'}
LANES = {'local', 'connector'}
SCOPE = ('server_id', 'executor_id', 'binding_id', 'agent_id', 'workspace_id')


class DriverRefusal(RuntimeError):
    pass


def require(value, code):
    if not value:
        raise DriverRefusal(code)


def safe_id(value):
    require(type(value) is str and 0 < len(value) <= 200 and value.isprintable(), 'INVALID_ID')
    return value


class CampaignState:
    """Durable single-controller journal; unexpected external writes fail closed."""
    def __init__(self, path, *, campaign_id=None):
        self.path = Path(path)
        self.lock = threading.Lock()
        if campaign_id is not None:
            self.data = {'format': 1, 'campaign_id': safe_id(campaign_id),
                         'admissions': [], 'decisions': [], 'faults': {}, 'blocked': False}
            with self.path.open('x', encoding='utf-8') as stream:
                json.dump(self.data, stream, sort_keys=True)
                stream.flush()
                os.fsync(stream.fileno())
        self.raw = self.path.read_bytes()
        self.data = json.loads(self.raw)
        require(self.data.get('format') == 1 and set(self.data) == {
            'format', 'campaign_id', 'admissions', 'decisions', 'faults', 'blocked'}, 'STATE_INVALID')
        require(len(self.data['admissions']) <= 6 and len(self.data['decisions']) <= 2,
                'STATE_LIMIT_INVALID')
        require(set(self.data['faults']) <= set(ROUTES), 'STATE_FAULT_INVALID')

    def check(self):
        require(self.path.read_bytes() == self.raw, 'EXTERNAL_STATE_CHANGE')

    def save(self):
        self.check()
        raw = (json.dumps(self.data, sort_keys=True, indent=2) + '\n').encode()
        pending = self.path.with_name(self.path.name + '.pending')
        with pending.open('xb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(pending, self.path)
        self.raw = raw

    def arm(self, kind, lane, target):
        """target = exact client_intent_id or canonical approval_id, not text."""
        with self.lock:
            self.check()
            require(kind in ROUTES and lane in LANES, 'FAULT_SELECTION_INVALID')
            require(not self.data['blocked'] and kind not in self.data['faults'], 'FAULT_ALREADY_USED')
            self.data['faults'][kind] = {'lane': lane, 'target': safe_id(target), 'phase': 'armed'}
            self.save()

    def snapshot(self):
        self.check()
        return deepcopy(self.data)


class FiniteResponseLoss:
    def __init__(self, call, checkpoint_load, state, lane):
        require(lane in LANES, 'LANE_INVALID')
        self.call, self.load, self.state, self.lane = call, checkpoint_load, state, lane

    def __call__(self, method, path, body=None):
        kind = next((k for k, route in ROUTES.items() if method == 'POST' and path == route), None)
        if kind is None:
            return self.call(method, path, body)
        # A single controller serializes the entire request including response.
        require(self.state.lock.acquire(blocking=False), 'CONCURRENT_CONTROLLER_REFUSED')
        try:
            return self._protected(kind, method, path, body)
        finally:
            self.state.lock.release()

    def _protected(self, kind, method, path, body):
        self.state.check()
        checkpoint = deepcopy(self.load())
        require(isinstance(checkpoint, dict) and isinstance(body, dict), 'CHECKPOINT_REQUIRED')
        scope = checkpoint.get('scope', {})
        require(all(type(scope.get(k)) is str and scope[k] for k in SCOPE), 'CHECKPOINT_SCOPE_REQUIRED')
        session = checkpoint.get('session_id')
        safe_id(session)
        if kind == 'admission':
            slots = [checkpoint.get(name, {}) for name in ('work', 'control')]
            slot = next((s for s in slots if s.get('submission') == body), None)
            require(slot is not None and slot.get('state') == 'submit_submitted', 'ADMISSION_CHECKPOINT_MISMATCH')
            # Controls remain canonical and do not consume productive allocation.
            if slot.get('action') in ('interrupt', 'close'):
                return self.call(method, path, body)
            require(slot.get('action') == 'send' and slot.get('intent') in ('runtime.start', 'turn.submit'),
                    'UNPLANNED_PRODUCTIVE_ACTION')
            target, operation = safe_id(body.get('client_intent_id')), safe_id(body.get('operation_id'))
            collection = self.state.data['admissions']
            require(len(collection) < 6, 'PRODUCTIVE_ALLOCATION_EXHAUSTED')
        else:
            slot = checkpoint.get('decision', {})
            expected = {k: v for k, v in slot.items() if k != 'response_hash'}
            supplied = {k: v for k, v in body.items() if k != 'response'}
            require(expected == supplied, 'DECISION_CHECKPOINT_MISMATCH')
            # Use the product's exact hash normalization instead of approximating it.
            from okto_nexus.application.terminal_connection import document_revision
            require(slot.get('response_hash') == document_revision(body.get('response')), 'DECISION_RESPONSE_CHANGED')
            key = body.get('approval_key', {})
            require(all(key.get(k) == scope[k] for k in SCOPE) and key.get('session_id') == session,
                    'DECISION_SCOPE_MISMATCH')
            target = safe_id(key.get('canonical_request_id'))
            operation = safe_id(body.get('client_intent_id'))
            collection = self.state.data['decisions']
            require(len(collection) < 2, 'DECISION_ALLOCATION_EXHAUSTED')
        require(not self.state.data['blocked'] and not any(
            r.get('phase') in ('forwarding', 'unconfirmed')
            for name in ('admissions', 'decisions') for r in self.state.data[name]),
            'CAMPAIGN_REQUIRES_RECONCILIATION')
        require(not any(r['operation_id'] == operation or
                        (r['lane'] == self.lane and r['target'] == target) for r in collection),
                'REPEATED_POST_REFUSED_USE_CANONICAL_RECOVERY')
        fault = self.state.data['faults'].get(kind)
        armed = fault is not None and fault == {'lane': self.lane, 'target': target, 'phase': 'armed'}
        record = {'lane': self.lane, 'target': target, 'operation_id': operation, 'phase': 'forwarding'}
        collection.append(record)
        self.state.save()  # Durable reservation before any effect; a crash cannot re-arm it.
        try:
            result = self.call(method, path, body)
            require(isinstance(result, dict), 'RESPONSE_SHAPE_UNCONFIRMED')
            if kind == 'admission':
                require(result.get('operation_id') == operation and result.get('intent_hash') == body.get('intent_hash'),
                        'ADMISSION_IDENTITY_UNCONFIRMED')
                received = result.get('scope', {})
                require(all(received.get(k) == scope[k] for k in SCOPE) and received.get('session_id') == session,
                        'ADMISSION_SCOPE_UNCONFIRMED')
            else:
                require(result.get('canonical_state') == 'CONFIRMED' and result.get('decision_id') and
                        result.get('approval_key') == body.get('approval_key') and
                        result.get('request_hash') == body.get('request_hash') and
                        result.get('client_intent_id') == operation, 'DECISION_ACK_UNCONFIRMED')
                record['decision_id'] = safe_id(result['decision_id'])
        except BaseException:
            record['phase'] = 'unconfirmed'
            self.state.data['blocked'] = True
            if armed:
                fault['phase'] = 'unconfirmed'
            self.state.save()
            raise
        record['phase'] = 'response_discarded' if armed else 'confirmed'
        if armed:
            fault['phase'] = 'consumed'
        self.state.save()
        if armed:
            raise ConnectionError('OUTCOME_UNKNOWN', 'Injected response loss after confirmed canonical acceptance.',
                                  stage='m1_response_loss', possible_effect=True)
        return result

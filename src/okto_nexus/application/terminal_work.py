"""Terminal work uses canonical intents, receipts, sessions and native decisions.

The local document is a bounded checkpoint, not a conversation store. Text,
answers, events and results stay in the existing Server services.
"""
from copy import deepcopy
from datetime import datetime, timezone
from urllib.parse import quote, urlencode
import uuid

from .terminal_connection import ConnectionError, PREFIX, TerminalConnection, RemoteTerminalConnection, document_revision
from .terminal_authorization import TerminalAuthorization

SUBMISSION = ('client_intent_id', 'operation_id', 'resolution_revision', 'intent_hash')
SCOPE = ('server_id', 'executor_id', 'binding_id', 'agent_id', 'workspace_id')
TERMINAL = {'SUCCEEDED', 'FAILED', 'CANCELLED'}


def _verify_session_binding(value, binding):
    scope = value.get('scope') if isinstance(value, dict) else None
    if not isinstance(scope, dict) or any(
            scope.get(key) != binding[key] for key in (*SCOPE, 'workspace_binding_id')):
        raise ConnectionError('WORK_SCOPE_CHANGED', 'The Server result does not match the selected project binding.')
    return scope


def list_binding_sessions(call, binding, *, after_session_id=''):
    """Read bounded pages for one authorized binding, reporting an incomplete inventory."""
    items, cursor = [], after_session_id
    for _ in range(10):
        page = call('GET', PREFIX + '/runtime/sessions?' + urlencode(dict(
            executor_id=binding['executor_id'], binding_id=binding['binding_id'],
            agent_id=binding['agent_id'], after_session_id=cursor, limit=100)))
        if (not isinstance(page, dict) or not isinstance(page.get('sessions'), list)
                or len(page['sessions']) > 100 or type(page.get('has_more')) is not bool):
            raise ConnectionError('SESSION_LIST_UNCONFIRMED', 'The session inventory is invalid.')
        following = cursor
        for session in page['sessions']:
            session_id = _verify_session_binding(session, binding).get('session_id')
            if (not isinstance(session_id, str) or not 1 <= len(session_id) <= 160
                    or not session_id.isprintable() or session_id <= following):
                raise ConnectionError('SESSION_LIST_UNCONFIRMED', 'The session inventory contains invalid or unordered references.')
            following = session_id
        items.extend(page['sessions'])
        if not page['has_more']:
            return {'sessions': items, 'has_more': False}
        if following == cursor or page.get('next_after_session_id') != following:
            raise ConnectionError('SESSION_LIST_UNCONFIRMED', 'The session list cursor did not advance.')
        cursor = following
    return {'sessions': items, 'has_more': True, 'next_after_session_id': cursor}


def read_binding_session(call, binding, session_id):
    value = call('GET', PREFIX + '/runtime/sessions/' + quote(session_id, safe='') + '?' +
                 urlencode({'executor_id': binding['executor_id']}))
    if _verify_session_binding(value, binding).get('session_id') != session_id:
        raise ConnectionError('WORK_SCOPE_CHANGED', 'The Server returned another session.')
    return value


class TerminalWork(TerminalAuthorization):
    def __init__(self, call, save, connection, checkpoint=None):
        self.call, self.save, self.connection = call, save, connection
        self.document = deepcopy(checkpoint) if checkpoint else {'format': 1}

    def api(self, method, path, body=None):
        return self.call(method, PREFIX + path, body)

    def _save(self):
        self.save(deepcopy(self.document))

    def binding(self):
        me = self.api('GET', '/connections/me')
        if me['server_id'] != self.connection['server_id']:
            raise ConnectionError('SERVER_ID_MISMATCH', 'This project belongs to another Server installation.')
        identity = self.connection['selection']['agent']
        binding_id = self.connection.get('result', {}).get('binding', {}).get('binding_id')
        if self.connection.get('state') != 'done' or not binding_id:
            raise ConnectionError('CONNECTION_REQUIRED', 'Finish connect before submitting project work.')
        flow_type = RemoteTerminalConnection if (self.connection['selection'].get('operator_profile')
            or self.connection.get('remote_scope')) else TerminalConnection
        flow_type(self.call, lambda value: None).observe(self.connection)
        binding = self.api('GET', '/connections/bindings/' + quote(binding_id, safe=''))
        if binding['server_id'] != me['server_id'] or binding['agent_id'] != identity:
            raise ConnectionError('PROFILE_DRIFT', 'The binding no longer belongs to this project identity.')
        scope = {key: binding[key] for key in (*SCOPE, 'workspace_binding_id')}
        if self.document.get('scope') not in (None, scope):
            raise ConnectionError('WORK_SCOPE_CHANGED', 'The saved work belongs to another binding or workspace.')
        return binding

    def _check_scope(self, value, binding):
        if any(value.get(key) != binding[key] for key in SCOPE):
            raise ConnectionError('WORK_SCOPE_CHANGED', 'The Server result does not match the selected project binding.')

    def sessions(self):
        return list_binding_sessions(self.call, self.binding())

    def session(self, binding, session_id):
        return read_binding_session(self.call, binding, session_id)

    def submit(self, text=None, *, action='send', session_id=None, new_session=False,
               client_intent_id=None, target_turn_id=None):
        binding = self.binding()
        if action not in ('send', 'steer', 'interrupt', 'close'):
            raise ConnectionError('ACTION_INVALID', 'Select send, steer, interrupt or close.')
        slot_name = 'work' if action in ('send', 'steer') else 'control'
        previous = self.document.get(slot_name)
        pending = previous and previous['state'] in ('resolve_submitted', 'resolved', 'submit_submitted')
        if previous and (pending or client_intent_id == previous['client_intent_id']):
            request = dict(previous['request_context'])
            if (previous['action'] != action or client_intent_id not in (None, previous['client_intent_id']) or
                    session_id is not None and session_id != request.get('session_id') or
                    new_session and not request.get('new_session') or
                    target_turn_id is not None and target_turn_id != request.get('target', {}).get('expected_turn_id')):
                raise ConnectionError('WORK_REQUEST_CONFLICT', 'Recover the original request before changing its selection.')
            if text is not None:
                request['text'] = text
            if document_revision(request) != previous['request_hash']:
                raise ConnectionError('WORK_REQUEST_CONFLICT', 'Recover the saved request before changing its content.')
            try:
                return self.resume(slot_name)
            except ConnectionError as error:
                if error.code != 'INTENT_NOT_FOUND':
                    raise
            resolution = self.api('POST', '/runtime/intents:resolve', request)
            self._resolved(previous, resolution, binding)
            return self._admit(previous, binding)
        if new_session and (action != 'send' or session_id):
            raise ConnectionError('SESSION_SELECTION_REQUIRED', 'A new session requires send without an existing session ID.')
        selected_session = None if new_session else session_id or self.document.get('session_id')
        if action != 'send' and not selected_session:
            raise ConnectionError('SESSION_REQUIRED', 'Select an existing session for this action.')
        if selected_session:
            current = self.session(binding, selected_session)
            if action in ('send', 'steer') and not current['control_available']:
                raise ConnectionError('SESSION_UNAVAILABLE', 'This session cannot continue. Inspect it or explicitly request --new-session.')
        intent = 'runtime.start' if action == 'send' and not selected_session else {
            'send': 'turn.submit', 'steer': 'turn.steer', 'interrupt': 'turn.interrupt', 'close': 'runtime.close'}[action]
        intent_id = client_intent_id or 'terminal_' + uuid.uuid4().hex
        request = dict(client_intent_id=intent_id, agent_id=binding['agent_id'], intent=intent,
                       binding_id=binding['binding_id'], workspace_binding_id=binding['workspace_binding_id'])
        if selected_session:
            request['session_id'] = selected_session
        elif new_session:
            request['new_session'] = True
        if text is not None:
            request['text'] = text
        if action in ('steer', 'interrupt'):
            if action == 'steer' and binding['adapter_id'] == 'codex_app_server' and not target_turn_id:
                raise ConnectionError('TURN_SELECTION_REQUIRED', 'Codex steering requires the current native turn ID.')
            request['target'] = dict(kind='native_turn_id' if target_turn_id else 'current_run',
                                     expected_turn_id=target_turn_id)
        digest = document_revision(request)
        self.document['scope'] = {key: binding[key] for key in (*SCOPE, 'workspace_binding_id')}
        slot = dict(client_intent_id=intent_id, request_hash=digest, intent=intent,
                    state='resolve_submitted', has_text=text is not None, action=action,
                    request_context={key: value for key, value in request.items() if key != 'text'})
        self.document[slot_name] = slot
        self._save()
        resolution = self.api('POST', '/runtime/intents:resolve', request)
        self._resolved(slot, resolution, binding)
        return self._admit(slot, binding)

    def _resolution_session(self, slot, resolution, binding):
        scope = _verify_session_binding(resolution, binding)
        session_id = resolution['session_id']
        requested = slot['request_context'].get('session_id')
        confirmed = slot.get('submission')
        if (resolution['client_intent_id'] != slot['client_intent_id'] or
                resolution['semantic_intent']['action'] != ('runtime.open' if slot['intent'] == 'runtime.start' else slot['intent'])
                or session_id != scope.get('session_id') or (requested is not None and session_id != requested)
                or (confirmed is not None and any(resolution[key] != confirmed[key] for key in SUBMISSION))):
            raise ConnectionError('WORK_RECEIPT_MISMATCH', 'The recovered intent does not match this request.')
        return session_id

    def _check_operation_receipt(self, operation, submission, binding, session_id):
        self._check_scope(operation['scope'], binding)
        if (operation['operation_id'] != submission['operation_id'] or
                operation['intent_hash'] != submission['intent_hash'] or
                operation['scope']['session_id'] != session_id):
            raise ConnectionError('WORK_RECEIPT_MISMATCH', 'The admission belongs to another operation.', possible_effect=True)

    def _resolved(self, slot, resolution, binding, operation=None, *, expected_session_id=None):
        session_id = self._resolution_session(slot, resolution, binding)
        if expected_session_id is not None and session_id != expected_session_id:
            raise ConnectionError('WORK_REQUEST_CONFLICT', 'The saved request belongs to a different session.')
        if operation is not None:
            self._check_operation_receipt(operation, resolution, binding, session_id)
        slot['submission'] = {key: resolution[key] for key in SUBMISSION}
        slot['state'] = 'resolved' if resolution['can_submit'] else 'blocked'
        slot['blockers'] = resolution['blockers']
        self.document['session_id'] = session_id
        if operation is None:
            self._save()

    def _admit(self, slot, binding):
        if slot['state'] == 'blocked':
            return {'state': 'blocked', 'client_intent_id': slot['client_intent_id'], 'blockers': slot['blockers']}
        slot['state'] = 'submit_submitted'
        self._save()
        try:
            operation = self.api('POST', '/runtime/operations', slot['submission'])
        except ConnectionError as error:
            if not error.possible_effect and error.code in ('CONFLICT', 'PERMISSION_DENIED', 'VALIDATION_ERROR'):
                slot['state'] = 'blocked'
                slot['blockers'] = [error.code]
                self._save()
            raise
        self._check_operation_receipt(operation, slot['submission'], binding, self.document['session_id'])
        child = None
        if slot['intent'] == 'runtime.start' and slot['has_text']:
            # The opening was confirmed, but its requested turn still needs
            # correlation. Retain the pending checkpoint if that read fails.
            slot['admission_confirmed'] = True
            self._save()
            try:
                receipt = self.api('GET', '/runtime/intents/' + quote(slot['client_intent_id'], safe=''))
                session_id = self._resolution_session(slot, receipt['resolution'], binding)
                self._check_operation_receipt(operation, receipt['resolution'], binding, session_id)
                if receipt['operation'] is None:
                    raise ConnectionError('WORK_CORRELATION_UNAVAILABLE', 'Recover the confirmed admission with work resume.')
                self._check_operation_receipt(receipt['operation'], slot['submission'], binding, session_id)
                child = self._initial_turn(slot, receipt)
            except ConnectionError as error:
                raise ConnectionError(error.code, error.message, possible_effect=True, stage=error.stage,
                                      choices=error.choices, http_status=error.http_status) from None
        return self._admitted(slot, operation, child)

    def _admitted(self, slot, operation, child):
        slot['state'] = 'admitted'
        slot.pop('admission_confirmed', None)
        if child is not None:
            slot['initial_turn_operation_id'] = child
        self._save()
        return operation | {'submission_turn_operation_id': child}

    @staticmethod
    def _initial_turn(slot, receipt):
        if slot['intent'] == 'runtime.start' and slot['has_text']:
            value = receipt.get('initial_turn_operation_id')
            if not isinstance(value, str) or not value or value == receipt['resolution']['operation_id']:
                raise ConnectionError('WORK_CORRELATION_UNAVAILABLE',
                    'The initial turn could not be correlated. The request may be running; inspect it before another submission.',
                    possible_effect=True)
            if slot.get('initial_turn_operation_id', value) != value:
                raise ConnectionError('WORK_RECEIPT_MISMATCH', 'The initial turn is different from the confirmed request.',
                                      possible_effect=True)
            return value
        return None

    def resume(self, slot_name='work', *, session_id=None, client_intent_id=None):
        slot = self.document.get(slot_name)
        if slot and client_intent_id is not None and client_intent_id != slot['client_intent_id']:
            raise ConnectionError('WORK_REQUEST_CONFLICT', 'The request ID does not match the saved request.')
        binding = self.binding()
        if not slot:
            raise ConnectionError('WORK_REQUIRED', 'There is no saved submission to resume.')
        confirmed = slot.get('admission_confirmed') is True or slot.get('initial_turn_operation_id') is not None
        try:
            receipt = self.api('GET', '/runtime/intents/' + quote(slot['client_intent_id'], safe=''))
        except ConnectionError as error:
            if error.code == 'NOT_FOUND':
                if confirmed:
                    raise ConnectionError('WORK_CORRELATION_UNAVAILABLE', 'The confirmed admission could not be recovered.',
                                          possible_effect=True) from None
                raise ConnectionError('INTENT_NOT_FOUND', 'The saved intent was not found. Re-enter the exact original request to retry resolution.') from None
            raise
        operation = receipt['operation']
        if operation is None and confirmed:
            raise ConnectionError('WORK_CORRELATION_UNAVAILABLE', 'The confirmed admission could not be recovered.',
                                  possible_effect=True)
        child = self._initial_turn(slot, receipt) if operation is not None else None
        self._resolved(slot, receipt['resolution'], binding, operation, expected_session_id=session_id)
        return self._admit(slot, binding) if operation is None else self._admitted(slot, operation, child)

    def operation(self, operation_id, binding):
        value = self.api('GET', '/runtime/operations/' + quote(operation_id, safe=''))
        self._check_scope(value['scope'], binding)
        if value['operation_id'] != operation_id:
            raise ConnectionError('WORK_RECEIPT_MISMATCH', 'The Server returned another operation.')
        return value

    def pending(self, binding, session_id):
        items = []
        for offset in range(0, 1000, 100):
            page = self.call('GET', '/api/v1/approvals?' + urlencode(dict(
                workspace=binding['workspace_id'], status='pending', offset=offset, limit=100)))['data']['items']
            for row in page:
                detail = self.call('GET', '/api/v1/approvals/' + quote(row['approval_id'], safe=''))['data']
                proposal = detail.get('request_payload', {}).get('kwargs', {})
                key = proposal.get('approval_key', {})
                if (all(key.get(name) == binding[name] for name in SCOPE) and
                        key.get('session_id') == session_id):
                    items.append(detail)
            if len(page) < 100:
                return {'items': items, 'has_more': False}
        return {'items': items, 'has_more': True}

    def observe(self, *, session_id=None, after_sequence=0, stream_epoch=None, slot_name='work'):
        binding = self.binding()
        slot = self.document.get(slot_name)
        operations = []
        selected_session = session_id or self.document.get('session_id')
        if slot and not session_id:
            receipt = self.api('GET', '/runtime/intents/' + quote(slot['client_intent_id'], safe=''))
            resolution = receipt['resolution']
            selected_session = self._resolution_session(slot, resolution, binding)
            operation = receipt['operation']
            if operation is None:
                return dict(state='submission_unconfirmed' if resolution['can_submit'] else 'blocked',
                    client_intent_id=slot['client_intent_id'], blockers=resolution['blockers'], session_id=selected_session)
            self._check_operation_receipt(operation, resolution, binding, selected_session)
            child = self._initial_turn(slot, receipt)
            operations = [operation] + ([self.operation(child, binding)] if child else [])
            if any(item['scope']['session_id'] != selected_session for item in operations):
                raise ConnectionError('WORK_RECEIPT_MISMATCH', 'The work result belongs to another session.')
        if not selected_session:
            return {'state': 'idle', 'sessions': self.sessions()}
        session = self.session(binding, selected_session)
        query = dict(executor_id=binding['executor_id'], after_sequence=after_sequence, limit=200)
        if stream_epoch is not None:
            query['stream_epoch'] = stream_epoch
        events = self.api('GET', '/runtime/sessions/' + quote(selected_session, safe='') + '/events?' + urlencode(query))
        page_scope = _verify_session_binding(events, binding)
        epoch, items = events.get('stream_epoch'), events.get('events')
        count, cursor = events.get('count'), events.get('next_after_sequence')
        committed, has_more = events.get('committed_contiguous'), events.get('has_more')
        event_scope = binding['server_id'], binding['executor_id'], selected_session, epoch
        if (page_scope.get('session_id') != selected_session
                or page_scope.get('session_owner_generation') != session['scope']['session_owner_generation']
                or 'stream_epoch' not in events
                or (stream_epoch is not None and epoch != stream_epoch)
                or not isinstance(items, list) or len(items) > query['limit'] or (items and not epoch)
                or type(count) is not int or count != len(items)
                or type(cursor) is not int or cursor != after_sequence + count
                or type(committed) is not int or committed < 0 or (count and cursor > committed)
                or type(has_more) is not bool or has_more != (cursor < committed) or (has_more and not count)
                or type(events.get('gap_pending')) is not bool
                or any(not isinstance(item, dict)
                       or tuple(item.get(key) for key in ('server_id', 'executor_id', 'session_id', 'stream_epoch'))
                       != event_scope or item.get('sequence') != sequence
                       for sequence, item in enumerate(items, after_sequence + 1))):
            raise ConnectionError('WORK_EVENT_PAGE_MISMATCH', 'The event page does not match the selected session or cursor.')
        requests = self.pending(binding, selected_session)
        targets = operations[1:] if len(operations) > 1 else operations
        done = bool(targets and all(item['executor_stage'] in TERMINAL or
                    item['admission_state'] == 'RESOLVED_TERMINAL' for item in targets))
        state = ('completed' if all(item['executor_stage'] == 'SUCCEEDED' for item in targets) else 'failed') if done else (
            'needs_input' if requests['items'] else 'observing')
        decision = None
        saved_decision = self.document.get('decision')
        if saved_decision and saved_decision['approval_key']['session_id'] == selected_session:
            detail = self.call('GET', '/api/v1/approvals/' + quote(
                saved_decision['approval_key']['canonical_request_id'], safe=''))['data']
            result = detail.get('executed_result')
            if result and result.get('decision_id'):
                key = saved_decision['approval_key']
                decision = self._decision_receipt(result['decision_id'], key, saved_decision['request_hash'])
                if decision['native_stage'] == 'REFUSED_BEFORE_EFFECT':
                    operation = self.operation(decision['native_operation_id'], binding)
                    scope = _verify_session_binding(operation, binding)
                    action = 'input.provide' if key['kind'] == 'native_input' else 'approval.decide'
                    if (scope['session_id'] != selected_session
                            or scope['session_owner_generation'] != key['session_owner_generation']
                            or operation['action'] != action):
                        raise ConnectionError('DECISION_RECEIPT_MISMATCH', 'The native operation belongs to another request.')
                    decision['operation'] = operation
                    if not done:
                        state = 'decision_refused'
        return dict(state=state, session=session, operations=operations, requests=requests, events=events, decision=decision)

    def decision_detail(self, approval_id, *, session_id=None):
        binding = self.binding()
        detail = self.call('GET', '/api/v1/approvals/' + quote(approval_id, safe=''))['data']
        proposal = detail.get('request_payload', {}).get('kwargs', {})
        key = proposal.get('approval_key', {})
        self._check_scope(key, binding)
        if key.get('canonical_request_id') != approval_id or key.get('session_id') != (session_id or self.document.get('session_id')):
            raise ConnectionError('DECISION_SCOPE_CHANGED', 'This request does not belong to the selected session.')
        return detail

    def _decision_receipt(self, decision_id, approval_key, request_hash):
        receipt = self.api('GET', '/runtime/approval-decisions/' + quote(decision_id, safe=''))
        if (receipt['decision_id'] != decision_id or receipt['approval_key'] != approval_key
                or receipt['request_hash'] != request_hash):
            raise ConnectionError('DECISION_RECEIPT_MISMATCH', 'The recorded decision belongs to another native request.')
        return receipt

    def decide(self, approval_id, decision, *, response=None, reviewed_revision=None, session_id=None):
        detail = self.decision_detail(approval_id, session_id=session_id)
        proposal = detail['request_payload']['kwargs']
        me = self.api('GET', '/connections/me')
        if me['agent_id'] != (proposal.get('recipient_agent_id') or 'operator'):
            raise ConnectionError('APPROVAL_AUTHORITY_REQUIRED', 'This request is addressed to another recipient.')
        last = self.document.get('decision')
        pending = dict(self.document.get('pending_decisions', {}))
        if 'pending_decisions' not in self.document and last:
            pending[last['approval_key']['canonical_request_id']] = last
        existing = detail.get('executed_result')
        if existing and existing.get('decision_id'):
            result = self._decision_receipt(existing['decision_id'], proposal['approval_key'], proposal['request_hash'])
            if pending.pop(approval_id, None) is not None:
                self.document['pending_decisions'] = pending
                self._save()
            return result
        if reviewed_revision != document_revision(proposal):
            raise ConnectionError('DECISION_REVIEW_REQUIRED', 'Review the current question and its scope before answering.')
        if datetime.fromisoformat(proposal['expires_at'].replace('Z', '+00:00')) <= datetime.now(timezone.utc):
            raise ConnectionError('DECISION_EXPIRED', 'This request has expired.')
        metadata = {key: deepcopy(proposal[key]) for key in ('approval_key', 'expected_revision', 'request_hash', 'cas_token')}
        metadata.update(decision=decision, response_hash=document_revision(response))
        previous = pending.get(approval_id)
        if previous is None and last and last['approval_key']['canonical_request_id'] == approval_id:
            previous = last
        if previous is not None:
            if any(previous[key] != value for key, value in metadata.items()):
                raise ConnectionError('DECISION_CONFLICT', 'Recover the original decision; its response cannot be changed.')
            metadata['client_intent_id'] = previous['client_intent_id']
        else:
            metadata['client_intent_id'] = 'terminal_decision_' + uuid.uuid4().hex
        pending[approval_id] = metadata
        self.document['pending_decisions'] = pending
        self.document['decision'] = metadata
        self._save()
        request = {key: value for key, value in metadata.items() if key != 'response_hash'}
        if response is not None:
            request['response'] = response
        try:
            result = self.api('POST', '/runtime/approval-decisions', request)
        except ConnectionError as error:
            if error.code == 'VALIDATION_ERROR' and not error.possible_effect:
                current = self.decision_detail(approval_id, session_id=session_id)
                if current['status'] == 'pending' and not current.get('executed_result'):
                    # A confirmed validation refusal did not record a decision.
                    # The user may correct that answer; uncertainty never clears
                    # its original metadata or permits a different response.
                    pending.pop(approval_id)
                    self.document.pop('decision', None)
                    self._save()
            raise
        if (result['approval_key'] != metadata['approval_key'] or result['client_intent_id'] != metadata['client_intent_id'] or
                result['request_hash'] != metadata['request_hash']):
            raise ConnectionError('DECISION_RECEIPT_MISMATCH', 'The decision result does not match this request.', possible_effect=True)
        pending.pop(approval_id)
        self._save()
        return result

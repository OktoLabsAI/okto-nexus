"""Terminal work uses canonical intents, receipts, sessions and native decisions.

The local document is a bounded checkpoint, not a conversation store. Text,
answers, events and results stay in the existing Server services.
"""
from copy import deepcopy
from datetime import datetime, timezone
from urllib.parse import quote, urlencode
import uuid

from .terminal_connection import ConnectionError, PREFIX, TerminalConnection, document_revision

SUBMISSION = ('client_intent_id', 'operation_id', 'resolution_revision', 'intent_hash')
SCOPE = ('server_id', 'executor_id', 'binding_id', 'agent_id', 'workspace_id')
TERMINAL = {'SUCCEEDED', 'FAILED', 'CANCELLED'}


class TerminalWork:
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
        TerminalConnection(self.call, lambda value: None).observe(self.connection)
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
        binding = self.binding()
        items, cursor = [], ''
        for _ in range(10):
            page = self.api('GET', '/runtime/sessions?' + urlencode(dict(
                executor_id=binding['executor_id'], binding_id=binding['binding_id'],
                agent_id=binding['agent_id'], after_session_id=cursor, limit=100)))
            for session in page['sessions']:
                self._check_scope(session['scope'], binding)
            items.extend(page['sessions'])
            if not page['has_more']:
                return {'sessions': items, 'has_more': False}
            following = page['next_after_session_id']
            if following <= cursor:
                raise ConnectionError('SESSION_LIST_UNCONFIRMED', 'The session list cursor did not advance.')
            cursor = following
        return {'sessions': items, 'has_more': True, 'next_after_session_id': cursor}

    def session(self, binding, session_id):
        value = self.api('GET', '/runtime/sessions/' + quote(session_id, safe='') + '?' +
                         urlencode({'executor_id': binding['executor_id']}))
        self._check_scope(value['scope'], binding)
        if value['scope']['session_id'] != session_id:
            raise ConnectionError('WORK_SCOPE_CHANGED', 'The Server returned another session.')
        return value

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

    def _resolved(self, slot, resolution, binding):
        self._check_scope(resolution['scope'], binding)
        if (resolution['client_intent_id'] != slot['client_intent_id'] or
                resolution['semantic_intent']['action'] != ('runtime.open' if slot['intent'] == 'runtime.start' else slot['intent'])):
            raise ConnectionError('WORK_RECEIPT_MISMATCH', 'The recovered intent does not match this request.')
        slot['submission'] = {key: resolution[key] for key in SUBMISSION}
        slot['state'] = 'resolved' if resolution['can_submit'] else 'blocked'
        slot['blockers'] = resolution['blockers']
        self.document['session_id'] = resolution['session_id']
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
        self._check_scope(operation['scope'], binding)
        if (operation['operation_id'] != slot['submission']['operation_id'] or
                operation['intent_hash'] != slot['submission']['intent_hash'] or
                operation['scope']['session_id'] != self.document['session_id']):
            raise ConnectionError('WORK_RECEIPT_MISMATCH', 'The admission belongs to another operation.', possible_effect=True)
        slot['state'] = 'admitted'
        self._save()
        receipt = self.api('GET', '/runtime/intents/' + quote(slot['client_intent_id'], safe=''))
        return operation | {'submission_turn_operation_id': self._initial_turn(slot, receipt)}

    @staticmethod
    def _initial_turn(slot, receipt):
        if slot['intent'] == 'runtime.start' and slot['has_text']:
            value = receipt.get('initial_turn_operation_id')
            if not isinstance(value, str) or not value:
                raise ConnectionError('WORK_CORRELATION_UNAVAILABLE',
                    'The initial turn could not be correlated. The request may be running; inspect it before another submission.',
                    possible_effect=True)
            return value
        return None

    def resume(self, slot_name='work'):
        binding = self.binding()
        slot = self.document.get(slot_name)
        if not slot:
            raise ConnectionError('WORK_REQUIRED', 'There is no saved submission to resume.')
        try:
            receipt = self.api('GET', '/runtime/intents/' + quote(slot['client_intent_id'], safe=''))
        except ConnectionError as error:
            if error.code == 'NOT_FOUND':
                raise ConnectionError('INTENT_NOT_FOUND', 'The saved intent was not found. Re-enter the exact original request to retry resolution.') from None
            raise
        self._resolved(slot, receipt['resolution'], binding)
        operation = receipt['operation']
        if operation is None:
            return self._admit(slot, binding)
        self._check_scope(operation['scope'], binding)
        if (operation['operation_id'] != slot['submission']['operation_id'] or
                operation['intent_hash'] != slot['submission']['intent_hash'] or
                operation['scope']['session_id'] != self.document['session_id']):
            raise ConnectionError('WORK_RECEIPT_MISMATCH', 'The recovered operation does not match the saved request.')
        slot['state'] = 'admitted'
        self._save()
        return operation | {'submission_turn_operation_id': self._initial_turn(slot, receipt)}

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
            self._check_scope(resolution['scope'], binding)
            selected_session = resolution['session_id']
            operation = receipt['operation']
            if operation is None:
                return dict(state='submission_unconfirmed' if resolution['can_submit'] else 'blocked',
                    client_intent_id=slot['client_intent_id'], blockers=resolution['blockers'], session_id=selected_session)
            self._check_scope(operation['scope'], binding)
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
        self._check_scope(events['scope'], binding)
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
                decision = self.api('GET', '/runtime/approval-decisions/' + quote(result['decision_id'], safe=''))
                if decision['approval_key'] != saved_decision['approval_key']:
                    raise ConnectionError('DECISION_RECEIPT_MISMATCH', 'The saved decision belongs to another request.')
                if decision['native_stage'] == 'REFUSED_BEFORE_EFFECT':
                    decision['operation'] = self.operation(decision['native_operation_id'], binding)
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

    def decide(self, approval_id, decision, *, response=None, reviewed_revision=None, session_id=None):
        detail = self.decision_detail(approval_id, session_id=session_id)
        proposal = detail['request_payload']['kwargs']
        me = self.api('GET', '/connections/me')
        if me['agent_id'] != (proposal.get('recipient_agent_id') or 'operator'):
            raise ConnectionError('APPROVAL_AUTHORITY_REQUIRED', 'This request is addressed to another recipient.')
        existing = detail.get('executed_result')
        if existing and existing.get('decision_id'):
            result = self.api('GET', '/runtime/approval-decisions/' + quote(existing['decision_id'], safe=''))
            if (result['approval_key'] != proposal['approval_key'] or
                    result['request_hash'] != proposal['request_hash']):
                raise ConnectionError('DECISION_RECEIPT_MISMATCH', 'The recorded decision belongs to another native request.')
            return result
        if reviewed_revision != document_revision(proposal):
            raise ConnectionError('DECISION_REVIEW_REQUIRED', 'Review the current question and its scope before answering.')
        if datetime.fromisoformat(proposal['expires_at'].replace('Z', '+00:00')) <= datetime.now(timezone.utc):
            raise ConnectionError('DECISION_EXPIRED', 'This request has expired.')
        metadata = {key: deepcopy(proposal[key]) for key in ('approval_key', 'expected_revision', 'request_hash', 'cas_token')}
        metadata.update(decision=decision, response_hash=document_revision(response))
        previous = self.document.get('decision')
        if previous and previous['approval_key']['canonical_request_id'] == approval_id:
            if any(previous[key] != value for key, value in metadata.items()):
                raise ConnectionError('DECISION_CONFLICT', 'Recover the original decision; its response cannot be changed.')
            metadata['client_intent_id'] = previous['client_intent_id']
        else:
            metadata['client_intent_id'] = 'terminal_decision_' + uuid.uuid4().hex
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
                    self.document.pop('decision', None)
                    self._save()
            raise
        if (result['approval_key'] != metadata['approval_key'] or result['client_intent_id'] != metadata['client_intent_id'] or
                result['request_hash'] != metadata['request_hash']):
            raise ConnectionError('DECISION_RECEIPT_MISMATCH', 'The decision result does not match this request.', possible_effect=True)
        return result

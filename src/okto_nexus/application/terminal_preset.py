"""Retain one optional preset review and recover its ordinary Finish receipt."""
from copy import deepcopy
from urllib.parse import quote, urlencode
import uuid

from .terminal_connection import TerminalConnection, RemoteTerminalConnection, ConnectionError, document_revision


class TerminalPreset(TerminalConnection):
    def __init__(self, call, save, connection, **kwargs):
        super().__init__(call, save, **kwargs)
        self.connection = connection
        self.last_refusal = None

    def api(self, method, path, body=None):
        try:
            return super().api(method, path, body)
        except ConnectionError as error:
            if (method == 'POST' and path in ('/connections/setup:test', '/connections/setup:finish')
                    and not error.possible_effect and error.code in
                    {'CONFLICT', 'VALIDATION_ERROR', 'PERMISSION_DENIED', 'AUTH_FAILED', 'OPERATOR_LOGIN_REQUIRED'}):
                self.last_refusal = dict(code=error.code, step=path.rsplit(':', 1)[1])
            raise

    def connection_state(self):
        if self.connection.get('state') != 'done':
            raise ConnectionError('CONNECTION_REQUIRED', 'Finish the existing connection before reviewing a preset update.')
        flow = RemoteTerminalConnection if self.connection['selection'].get('operator_profile') else TerminalConnection
        return flow(self.call, lambda _: None).observe(self.connection)

    def review(self):
        observed = self.connection_state()
        plan = self.api('GET', '/connections/setup/' + quote(observed['agent_id'], safe='') + '/preset-update?' +
            urlencode(dict(binding_id=observed['binding_id'])))
        if plan['state'] == 'up_to_date':
            return dict(state='up_to_date', agent_id=observed['agent_id'], binding_id=observed['binding_id'],
                origin=plan['target_origin'], message='This connection already records the current preset revision. Customized settings are preserved.')
        request = deepcopy(plan['request'])
        if request['agent_id'] != observed['agent_id'] or request['binding_id'] != observed['binding_id']:
            raise ConnectionError('PROFILE_DRIFT', 'The preset review belongs to another project connection.')
        request['client_intent_id'] = 'preset_' + uuid.uuid4().hex
        check = False
        if plan['local_test_required']:
            available = self.options(request)
            selected = next((row for row in available['options'] if row.get('candidate_ref') == request['candidate_ref']
                and row['adapter_id'] == request['configuration']['adapter_id']
                and (row.get('binding') or {}).get('binding_id') == observed['binding_id']), None)
            if selected is None or not selected.get('can_configure'):
                raise ConnectionError('INSTALLATION_UNCONFIRMED', 'Inspect the selected project installation before reviewing its update.')
            check = selected['technical_state'] != 'READY_FOR_RUNTIME'
            request['inventory_revision'] = available['inventory_revision']
        effects = list(plan['effects'])
        if not self.connection['selection'].get('operator_profile'):
            effects.append('Applying from this local profile may start or reuse the configured Server service; no service installation is requested.')
        review = dict(server_id=self.connection['server_id'], selection=deepcopy(self.connection['selection']),
            request=request, version_check_required=check, effects=effects,
            preset_review={key: value for key, value in plan.items() if key != 'request'})
        document = dict(review, format=1, state='review', review_request=deepcopy(request),
            review_revision=document_revision(review))
        self.save(document)
        return document

    def observe(self, document):
        observed = self.connection_state()
        current = self.current(observed['agent_id'], observed['binding_id'])
        return dict(state='preset_applied', agent_id=observed['agent_id'], binding_id=observed['binding_id'],
            setup_run_id=document['request']['client_intent_id'],
            applied_origin=document['result']['project_preset'], current_origin=current.get('project_preset'),
            configuration=current, work_state='not_submitted')

    def apply(self, document, *, approval=None, timeout=300):
        if document['state'] == 'refused':
            raise ConnectionError('REVIEW_REQUIRED', 'The Server refused this update. Use --refresh to review current effects before another approval.')
        self.last_refusal = None
        try:
            result = self._apply(document, approval=approval, timeout=timeout)
            if result['state'] == 'test_failed' and result['test'].get('retryable_failure') is True:
                document.update(state='refused', refusal=dict(code='CONNECTION_TEST_FAILED', step='test'))
                self.save(document)
            return result
        except ConnectionError:
            if self.last_refusal is not None:
                document.update(state='refused', refusal=self.last_refusal)
                self.save(document)
            raise

    def _apply(self, document, *, approval, timeout):
        if document['preset_review']['local_test_required']:
            return super().apply(document, approval=approval, timeout=timeout)
        self.connection_state()
        if document['state'] == 'done':
            return self.observe(document)
        request = self.approve_review(document, approval)
        if document['state'] not in ('approved', 'finish'):
            raise ConnectionError('CHECKPOINT_INVALID', 'Inspect the retained preset update before applying it.')
        if document['state'] == 'finish':
            try:
                receipt = self.api('POST', '/connections/setup:recover', request)
            except ConnectionError as error:
                if (error.code, error.stage) != ('NOT_FOUND', 'connection.setup_commit'):
                    raise
            else:
                if (receipt.get('setup_run_id') != request['client_intent_id'] or receipt.get('state') != 'committed'
                        or receipt.get('result', {}).get('agent_id') != request['agent_id']):
                    raise ConnectionError('RECEIPT_UNCONFIRMED', 'The Server returned an inconsistent preset receipt.', possible_effect=True)
                document.update(state='done', result=receipt['result'])
                self.save(document)
                return self.observe(document)
        document['state'] = 'finish'
        self.save(document)
        result = self.api('POST', '/connections/setup:finish', request)
        document.update(state='done', result=result)
        self.save(document)
        return self.observe(document)

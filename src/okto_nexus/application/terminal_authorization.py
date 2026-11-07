"""Thin reviewed authorization flow; only the Server issues or recovers grants."""
from copy import deepcopy
import uuid

from .terminal_connection import ConnectionError, document_revision


class TerminalAuthorization:
    def authorization_review(self, *, minutes=60, max_executions=20):
        prior = self.document.get('authorization')
        if prior and prior['state'] == 'submitted':
            return self.authorize()  # Resolve an uncertain issuance before a new review.
        binding = self.binding()
        review = self.api('POST', '/connections/authorizations:review', dict(
            binding_id=binding['binding_id'], client_request_id='authorize_' + uuid.uuid4().hex,
            minutes=minutes, max_executions=max_executions))
        self._check_scope(review['scope'], binding)
        revision = document_revision(review)
        self.document['authorization'] = dict(state='review', review=deepcopy(review), review_revision=revision)
        self._save()
        return review | {'review_revision': revision}

    def authorize(self, *, approval=None):
        try:
            return self._authorize(approval=approval)
        except ConnectionError as error:
            pending = self.document.get('authorization')
            if pending and pending.get('state') == 'submitted' and not error.possible_effect:
                # An unavailable login or recovery endpoint cannot resolve an
                # earlier issuance whose response was never confirmed.
                raise ConnectionError(error.code, error.message, stage=error.stage, possible_effect=True) from error
            raise

    def _authorize(self, *, approval=None):
        pending = self.document.get('authorization')
        if not pending:
            raise ConnectionError('REVIEW_REQUIRED', 'Run work authorize to review the project authorization first.')
        review = pending['review']
        if document_revision(review) != pending['review_revision']:
            raise ConnectionError('REVIEW_CHANGED', 'The saved authorization no longer matches its displayed review.')
        scope = review['scope']
        if (self.api('GET', '/connections/me')['server_id'] != self.connection['server_id'] or
                scope['server_id'] != self.connection['server_id'] or
                scope['binding_id'] != self.connection['result']['binding']['binding_id'] or
                scope['agent_id'] != self.connection['selection']['agent']):
            raise ConnectionError('WORK_SCOPE_CHANGED', 'The saved authorization belongs to another project or Server.')
        if pending['state'] == 'review':
            self._check_scope(scope, self.binding())
            if not review['can_issue']:
                raise ConnectionError('AUTHORIZATION_AVAILABLE', 'This project already has an available authorization.')
            if approval != pending['review_revision']:
                raise ConnectionError('REVIEW_REQUIRED', 'Approve the exact displayed authorization review before issuance.')
            pending['state'] = 'submitted'
            self._save()  # Checkpoint the stable request before any possible grant effect.
        if pending['state'] not in ('submitted', 'done'):
            raise ConnectionError('CHECKPOINT_INVALID', 'The saved authorization checkpoint is not recognized.')
        request = review['request']
        try:
            receipt = self.api('POST', '/connections/authorizations:recover', request)
        except ConnectionError as error:
            if pending['state'] == 'done':
                # Recovery is read-only. Generic POST transport uncertainty
                # cannot make an already confirmed issuance uncertain again.
                raise ConnectionError(error.code, error.message, stage=error.stage, possible_effect=False) from error
            if (error.code, error.stage) != ('NOT_FOUND', 'connection.authorization'):
                raise
            try:
                receipt = self.api('POST', '/connections/authorizations:issue', request)
            except ConnectionError as error:
                if not error.possible_effect and error.code in ('CONFLICT', 'PERMISSION_DENIED', 'VALIDATION_ERROR'):
                    pending['state'] = 'review'  # A new explicit review may replace a definitely refused request.
                    self._save()
                    raise
                raise ConnectionError(error.code, error.message, stage=error.stage, possible_effect=True) from error
        grant = receipt['result']['grant']
        if (receipt['state'] != 'authorization_committed' or receipt['client_request_id'] != request['client_request_id'] or
                receipt['result']['scope'] != scope or
                receipt['request_hash'] != 'sha256:' + document_revision(request) or
                grant['actor_agent_id'] != scope['agent_id'] or grant['endpoint_id'] != scope['endpoint_id'] or
                grant['represented_agent_id'] != scope['agent_id'] or grant['workspace_id'] != scope['workspace_id'] or
                grant['expires_at'] != request['expires_at'] or
                grant['max_executions'] != request['max_executions'] or set(grant['actions']) != set(review['actions'])):
            raise ConnectionError('RECEIPT_UNCONFIRMED', 'The Server returned an inconsistent authorization receipt.', possible_effect=True)
        pending['state'] = 'done'
        pending['result'] = deepcopy(receipt)
        self._save()
        return receipt

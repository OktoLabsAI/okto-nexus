"""Review and decide an immutable Connector proposal through canonical HTTP."""
from urllib.parse import quote

from .terminal_connection import ConnectionError, PREFIX, document_revision


class TerminalBindingApproval:
    def __init__(self, call):
        self.call = call

    def review(self, approval_id):
        me = self.call('GET', PREFIX + '/connections/me')
        detail = self.call('GET', '/api/v1/approvals/' + quote(approval_id, safe=''))['data']
        if detail['action'] != 'execution.binding.authorize':
            raise ConnectionError('APPROVAL_KIND_UNSUPPORTED', 'This command reviews Connector binding proposals. Use work answer for native requests.')
        evidence = detail.get('decision_detail')
        if not evidence or not evidence.get('proposal'):
            raise ConnectionError('SERVER_UPGRADE_REQUIRED', 'Upgrade the Server to expose the canonical binding proposal review.')
        proposal = evidence['proposal']
        if proposal['server_id'] != me['server_id']:
            raise ConnectionError('SERVER_ID_MISMATCH', 'The proposal belongs to another Server installation.')
        reviewed = dict(approval_id=detail['approval_id'], server_id=me['server_id'],
            actor_agent_id=me['agent_id'], agent_id=detail['agent_id'], workspace_id=detail['workspace_id'],
            request=detail['request_payload'], proposal=proposal)
        return dict(state='binding_approval_review', **reviewed,
            review_revision=document_revision(reviewed), status=detail['status'],
            proposal_state=evidence['proposal_state'], expired=evidence['expired'],
            decided_by=detail.get('decided_by'), decided_at=detail.get('decided_at'),
            executed_result=detail.get('executed_result'), justification=detail.get('justification'))

    def decide(self, approval_id, decision, revision):
        if decision not in ('approve', 'reject'):
            raise ConnectionError('DECISION_REQUIRED', 'Choose approve or reject explicitly.')
        current = self.review(approval_id)
        if current['review_revision'] != revision:
            raise ConnectionError('REVIEW_CHANGED', 'The proposal review changed. Inspect the current scope before deciding.')
        target = 'approved' if decision == 'approve' else 'rejected'
        if current['status'] != 'pending':
            if (current['status'] != target or current['decided_by'] != current['actor_agent_id'] or
                    current['justification'] is not None or current['executed_result'] is None):
                raise ConnectionError('DECISION_CONFLICT', 'The request already has another decision or is archived. Inspect its canonical receipt.')
            return dict(state='binding_approval_decided', recovered=True, approval_id=approval_id,
                status=current['status'], decided_by=current['decided_by'], decided_at=current['decided_at'],
                executed_result=current['executed_result'])
        if decision == 'approve' and (current['expired'] or current['proposal_state'] != 'PREPARED' or
                                      not current['proposal']['can_apply']):
            raise ConnectionError('PROPOSAL_UNAVAILABLE', 'The proposal expired or cannot be applied. Return to the original Connector request for diagnosis.')
        result = self.call('POST', '/api/v1/approvals/' + quote(approval_id, safe='') + '/decision',
            {'decision': decision})['data']
        return dict(state='binding_approval_decided', recovered=False, **result)

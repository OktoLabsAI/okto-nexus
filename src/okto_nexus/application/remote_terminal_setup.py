"""Human-operator orchestration of the existing remote Connections setup.

Only metadata enters the local checkpoint. The one-shot canonical agent key is
delivered through an explicit caller-owned sink, never through a result document.
"""
from copy import deepcopy
import re
from urllib.parse import quote

from ..domain.keys import is_well_formed_api_key
from .project_preset import CLIENTS
from .remote_setup_contract import normalize_draft, validate_review
from .terminal_binding_approval import TerminalBindingApproval
from .terminal_connection import (
    ConnectionError, RemoteTerminalConnection, TerminalConnection, document_revision,
)


class RemoteProjectSetup(TerminalConnection):
    KIND = 'remote_project_setup'
    STATES = {'review_submitted', 'review', 'approved', 'bootstrap_submitted', 'awaiting_host',
              'decision_submitted', 'awaiting_finish', 'review_required', 'done'}

    def __init__(self, call, save, *, origin, material_sink=None, handoff_sink=None, **kwargs):
        super().__init__(call, save, **kwargs)
        self.origin, self.material_sink = origin, material_sink
        self.handoff_sink = handoff_sink

    def _me(self):
        me = self.api('GET', '/connections/me')
        capabilities = me.get('capabilities') if type(me) is dict else None
        capability = capabilities.get('remote_setup') if type(capabilities) is dict else None
        if type(capability) is not dict or any(type(capability.get(key)) is not int or capability[key] != 1
               for key in ('revision', 'draft_version', 'handoff_version')):
            raise ConnectionError('SERVER_UPGRADE_REQUIRED',
                'This Server does not support the reviewed remote setup contract. No bootstrap was sent.')
        return me

    def review(self, selection, *, previous=None):
        selection = deepcopy(selection)
        draft = normalize_draft(selection['remote_draft'])
        if draft['server_origin'] != self.origin:
            raise ConnectionError('SERVER_ORIGIN_MISMATCH',
                'The host draft belongs to another Server origin. Select its operator profile.')
        if selection.get('binding_id') or selection.get('provider_home'):
            raise ConnectionError('REMOTE_SETUP_CONFLICT',
                'A new host draft cannot replace a binding or select a provider home on this operator client.')
        client = next((name for name, adapter in CLIENTS.items()
                       if adapter == draft['installation']['adapter_id']), None)
        if (client is None or selection.get('client') not in (None, client)
                or selection.get('candidate_ref') not in (None, draft['installation']['candidate_ref'])):
            raise ConnectionError('REMOTE_SETUP_CONFLICT',
                'The selected harness or installation differs from the host draft.')
        selection['client'] = client
        selection['remote_draft'] = draft
        me = self._me()
        body = dict(draft=draft,
            identity=dict(mode='create' if selection['create_agent'] else 'select',
                agent_id=selection['agent'], display_name=selection.get('display_name') or selection['agent']),
            workspace=dict(mode='select' if selection.get('workspace_id') else 'create',
                workspace_id=selection.get('workspace_id'), display_name=draft['project_label']))
        if previous is not None:
            self._validate(previous)
            if previous['remote_review']['draft']['setup_run_id'] != draft['setup_run_id']:
                raise ConnectionError('PROFILE_CONFLICT', 'A setup revision must retain its original root ID.')
            body['expected_review_revision'] = previous['review_revision']
            if previous.get('bootstrap') is not None:
                # The project label is host metadata. A new local directory
                # does not rename or replace its committed canonical workspace.
                body['workspace'] = deepcopy(previous['remote_review']['selection']['workspace'])
        pending = deepcopy(previous) if previous is not None else dict(format=1, kind=self.KIND)
        pending.update(state='review_submitted', selection=selection, server_id=me['server_id'],
            pending_review_request=deepcopy(body))
        self.save(pending)  # Retain generated identity/root and CAS before the POST.
        return self._accept_review(pending, self.api('POST', '/connections/remote-setup:review', body))

    def _accept_review(self, pending, response):
        body, selection = pending['pending_review_request'], pending['selection']
        draft = normalize_draft(body['draft'])
        review = validate_review(response['review'])
        if (review['selection']['server_id'] != pending['server_id']
                or review['selection']['identity']['agent_id'] != selection['agent']
                or review['selection']['identity']['mode'] != body['identity']['mode']
                or any(review['selection']['workspace'][key] != body['workspace'][key]
                       for key in ('mode', 'workspace_id')) or review['draft'] != draft):
            raise ConnectionError('REVIEW_UNCONFIRMED', 'The Server review does not match this setup request.')
        document = dict(format=1, kind=self.KIND, state='review', selection=selection,
            server_id=pending['server_id'], remote_review=review,
            review_revision=review['review_revision'])
        # A new review does not discard the existing bootstrap or child receipts.
        for key in ('bootstrap', 'handoff', 'material_delivery', 'approval', 'final_binding'):
            if key in pending:
                document[key] = deepcopy(pending[key])
        self.save(document)
        return document

    def recover_review(self, pending):
        """Recover an uncertain review as unconfirmed, never as product consent."""
        if (pending.get('kind') != self.KIND or pending.get('state') != 'review_submitted'
                or self._me()['server_id'] != pending['server_id']):
            raise ConnectionError('REVIEW_UNCONFIRMED', 'The pending review has another Server or checkpoint scope.')
        body = pending['pending_review_request']
        draft = normalize_draft(body['draft'])
        if draft != pending['selection']['remote_draft'] or draft['server_origin'] != self.origin:
            raise ConnectionError('REVIEW_CHANGED', 'The pending review request changed.')
        try:
            response = self.api('POST', '/connections/remote-setup:recover', dict(setup_run_id=draft['setup_run_id']))
        except ConnectionError as error:
            if error.code != 'NOT_FOUND':
                raise
            response = None
        if (response is None or body.get('expected_review_revision') is not None
                and response['review']['review_revision'] == body['expected_review_revision']):
            # Either no review committed or the requested refresh never replaced
            # its predecessor. Reuse the saved body and CAS, not a new identity.
            response = self.api('POST', '/connections/remote-setup:review', deepcopy(body))
        return self._accept_review(pending, response)

    def _validate(self, document):
        if (document.get('format') != 1 or document.get('kind') != self.KIND
                or document.get('state') not in self.STATES):
            raise ConnectionError('CHECKPOINT_INVALID', 'The remote setup checkpoint is not recognized.')
        review = validate_review(document['remote_review'])
        if (review['review_revision'] != document['review_revision']
                or review['draft']['server_origin'] != self.origin
                or review['draft'] != document['selection']['remote_draft']
                or review['selection']['server_id'] != document['server_id']
                or review['selection']['identity']['agent_id'] != document['selection']['agent']):
            raise ConnectionError('REVIEW_CHANGED', 'The saved remote setup no longer matches its review.')
        return review

    def _request(self, document):
        review = self._validate(document)
        return dict(setup_run_id=review['draft']['setup_run_id'],
                    review_revision=review['review_revision'])

    def _save_after_effect(self, document):
        try:
            self.save(document)
        except (OSError, ValueError, TypeError):
            raise ConnectionError('CHECKPOINT_UNCONFIRMED',
                'Remote effects may be committed. Recover this same setup; no new identity or key was requested.',
                possible_effect=True) from None

    def _consume(self, document, response, *, allow_material=False):
        review = self._validate(document)
        before = document_revision(document)
        if validate_review(response['review']) != review:
            raise ConnectionError('REVIEW_CHANGED', 'The Server setup review changed. Review the affected choices again.')
        if response.get('state') not in ('reviewed', 'awaiting_host', 'committed'):
            raise ConnectionError('RECEIPT_UNCONFIRMED', 'The Server returned an unknown setup state.', possible_effect=True)
        if (response.get('material_status') not in ('not_issued', 'issued_once', 'unavailable', 'reuse_existing')
                or response.get('current_references') not in (None, 'matching', 'changed', 'unavailable')):
            raise ConnectionError('RECEIPT_UNCONFIRMED', 'The Server returned unknown receipt metadata.', possible_effect=True)
        final = response.get('final_binding')
        if final is not None and (type(final) is not dict
                or set(final) != {'server_id', 'agent_id', 'workspace_id', 'executor_id', 'binding_id', 'proposal_id', 'finish_id'}
                or any(type(value) is not str or not 1 <= len(value) <= 200 for value in final.values())):
            raise ConnectionError('RECEIPT_UNCONFIRMED', 'The final receipt has unsupported fields.', possible_effect=True)
        material = response.get('material')
        if material is not None and (not allow_material or type(material) is not dict
                or set(material) != {'api_key'} or not is_well_formed_api_key(material['api_key'])):
            raise ConnectionError('MATERIAL_UNCONFIRMED', 'Unexpected credential material was refused.', possible_effect=True)
        bootstrap = response.get('bootstrap')
        if bootstrap is not None:
            expected = dict(setup_run_id=review['draft']['setup_run_id'], server_id=document['server_id'],
                agent_id=document['selection']['agent'])
            if (type(bootstrap) is not dict or set(bootstrap) != set(expected) | {'workspace_id', 'credential_epoch', 'review_revision'}
                    or any(bootstrap.get(key) != value for key, value in expected.items())
                    or type(bootstrap['review_revision']) is not str
                    or not re.fullmatch('[0-9a-f]{64}', bootstrap['review_revision'])
                    or type(bootstrap['credential_epoch']) is not int or bootstrap['credential_epoch'] < 1
                    or not isinstance(bootstrap['workspace_id'], str) or not bootstrap['workspace_id']
                    or review['selection']['workspace']['mode'] == 'select'
                    and bootstrap['workspace_id'] != review['selection']['workspace']['workspace_id']):
                raise ConnectionError('RECEIPT_UNCONFIRMED', 'The partial receipt has another setup scope.', possible_effect=True)
            if document.get('bootstrap') is not None and document['bootstrap'] != bootstrap:
                raise ConnectionError('RECEIPT_UNCONFIRMED', 'The original bootstrap receipt changed.', possible_effect=True)
            if (review['selection']['identity']['mode'] == 'select'
                    and bootstrap['credential_epoch'] != review['selection']['credential']['expected_epoch']):
                raise ConnectionError('RECEIPT_UNCONFIRMED', 'The selected identity credential revision changed.', possible_effect=True)
            handoff = response.get('handoff')
            expected_handoff = dict(format='okto.remote-setup-handoff', version=1,
                bootstrap=bootstrap, child_requests=review['child_requests'],
                draft_revision=review['draft_revision'], review_revision=review['review_revision'])
            if type(handoff) is not dict or document_revision(handoff) != document_revision(expected_handoff):
                raise ConnectionError('RECEIPT_UNCONFIRMED', 'The host handoff does not match the reviewed setup.', possible_effect=True)
            document.update(bootstrap=deepcopy(bootstrap), handoff=deepcopy(expected_handoff))
        elif material is not None or response.get('handoff') is not None:
            raise ConnectionError('RECEIPT_UNCONFIRMED', 'Credential delivery has no matching bootstrap receipt.', possible_effect=True)
        for key in ('material_status', 'current_references', 'final_binding'):
            document[key] = deepcopy(response.get(key))
        if bootstrap is not None and document['state'] not in ('decision_submitted', 'awaiting_finish', 'done'):
            document['state'] = 'awaiting_host'
        if document_revision(document) != before:
            self._save_after_effect(document)
        if material is not None:
            if self.material_sink is None:
                raise ConnectionError('MATERIAL_DELIVERY_UNAVAILABLE',
                    'The one-shot key could not be delivered. Recover metadata without rotating the identity.', possible_effect=True)
            try:
                self.material_sink(material['api_key'])
            except OSError:
                raise ConnectionError('MATERIAL_DELIVERY_UNAVAILABLE',
                    'The one-shot key could not be displayed. Recover metadata without rotating the identity.',
                    possible_effect=True) from None
            document['material_delivery'] = 'delivered_once'
            self._save_after_effect(document)
        if self.handoff_sink is not None and document.get('handoff') is not None:
            try:
                self.handoff_sink(deepcopy(document['handoff']))
            except ConnectionError as error:
                raise ConnectionError(error.code, error.message, possible_effect=True) from None
            except (OSError, ValueError, TypeError):
                raise ConnectionError('HANDOFF_EXPORT_UNCONFIRMED',
                    'The metadata handoff could not be exported. Resume this same setup to recover it.',
                    possible_effect=True) from None
        return response['state']

    def _public(self, document, *, state=None, **details):
        value = dict(state=state or document['state'], server_id=document['server_id'],
            setup_run_id=document['remote_review']['draft']['setup_run_id'],
            agent_id=document['selection']['agent'], work_state='not_submitted',
            **{key: deepcopy(document[key]) for key in ('bootstrap', 'handoff', 'material_status',
                'material_delivery', 'current_references', 'final_binding') if key in document})
        return value | details

    def observe(self, document):
        if document.get('state') == 'review_submitted':
            return self.recover_review(document)
        self._validate(document)
        if document['state'] != 'done':
            response = self.api('POST', '/connections/remote-setup:recover', self._request(document))
            self._consume(document, response)
            if response['state'] != 'committed':
                return self._public(document)
            self._complete(document)
        result = RemoteTerminalConnection(self.call, lambda _: None).observe(document)
        return result | dict(setup_run_id=document['remote_review']['draft']['setup_run_id'])

    def _complete(self, document):
        final, bootstrap = document.get('final_binding'), document.get('bootstrap')
        if (not isinstance(final, dict) or not bootstrap
                or any(final.get(key) != bootstrap[key] for key in ('server_id', 'agent_id', 'workspace_id'))
                or not isinstance(final.get('proposal_id'), str)
                or final.get('finish_id') != final['proposal_id'] + '_setup'):
            raise ConnectionError('RECEIPT_UNCONFIRMED', 'The final Finish receipt is not correlated to this setup.', possible_effect=True)
        binding = self.api('GET', '/connections/bindings/' + quote(final['binding_id'], safe=''))
        if (any(binding.get(key) != final[key] for key in ('server_id', 'agent_id', 'workspace_id', 'executor_id', 'binding_id'))
                or binding.get('state') != 'APPROVED'
                or binding.get('adapter_id') != document['remote_review']['draft']['installation']['adapter_id']
                or binding.get('candidate_ref') != document['remote_review']['draft']['installation']['candidate_ref']):
            raise ConnectionError('PROFILE_DRIFT', 'The final binding no longer matches the approved remote project.')
        document.update(state='done', remote_scope={key: binding[key] for key in RemoteTerminalConnection.SCOPE},
            result=dict(saved=True, agent_id=binding['agent_id'], binding=binding))
        self._save_after_effect(document)

    def apply(self, document, *, approval=None, timeout=300):
        if document.get('state') == 'review_submitted':
            return self.recover_review(document)
        review = self._validate(document)
        if self._me()['server_id'] != document['server_id']:
            raise ConnectionError('SERVER_ID_MISMATCH', 'The selected Server installation changed.')
        if document['state'] == 'done':
            return self.observe(document)
        if document['state'] == 'review':
            if approval != review['review_revision']:
                raise ConnectionError('REVIEW_REQUIRED', 'Approve the displayed remote project review before applying it.')
            document.update(state='approved', approved_revision=approval)
            self.save(document)
        elif document.get('approved_revision') != review['review_revision']:
            raise ConnectionError('REVIEW_REQUIRED', 'The current remote review has not been confirmed.')
        response = self.api('POST', '/connections/remote-setup:recover', self._request(document))
        self._consume(document, response)
        if response['bootstrap'] is None:
            if review['selection']['identity']['mode'] == 'create' and self.material_sink is None:
                raise ConnectionError('INTERACTIVE_KEY_DELIVERY_REQUIRED',
                    'Resume this same profile in an interactive terminal to receive the new agent key. No identity was created.')
            document['state'] = 'bootstrap_submitted'
            self.save(document)
            response = self.api('POST', '/connections/remote-setup:bootstrap', self._request(document))
            self._consume(document, response, allow_material=True)
        deadline = self.monotonic() + timeout
        while True:
            if response['state'] == 'committed':
                self._complete(document)
                return self.observe(document)
            if document.get('current_references') in ('changed', 'unavailable'):
                return self._public(document, state='review_required')
            assessment = self.api('POST', '/connections/remote-setup:materialization', self._request(document))
            if (assessment.get('comparison_only') is not True or assessment.get('authority_granted') is not False
                    or assessment.get('requires_authenticated_operator') is not True):
                raise ConnectionError('MATERIALIZATION_UNCONFIRMED', 'Canonical comparison metadata is unavailable.')
            if assessment['state'] == 'requires_review':
                document['state'] = 'review_required'
                self.save(document)
                return self._public(document, changed_fields=assessment['changed_fields'])
            if assessment['state'] == 'review_matches' and document['state'] != 'awaiting_finish':
                approvals = TerminalBindingApproval(self.call)
                current = approvals.review(assessment['approval_id'])
                if (document_revision(current['proposal']) != document_revision(assessment['proposal'])
                        or current['server_id'] != document['server_id']
                        or current['agent_id'] != document['bootstrap']['agent_id']
                        or current['workspace_id'] != document['bootstrap']['workspace_id']):
                    raise ConnectionError('REVIEW_CHANGED', 'The canonical proposal changed before the operator decision.')
                document.update(state='decision_submitted', approval=dict(
                    approval_id=assessment['approval_id'], review_revision=current['review_revision']))
                self.save(document)
                approvals.decide(assessment['approval_id'], 'approve', current['review_revision'])
                document['state'] = 'awaiting_finish'
                self._save_after_effect(document)
            elif assessment['state'] not in ('review_matches', 'needs_canonical_metadata'):
                raise ConnectionError('MATERIALIZATION_UNCONFIRMED', 'Unknown canonical comparison state was refused.')
            if self.monotonic() >= deadline:
                return self._public(document, missing_fields=assessment.get('missing_fields', []))
            self.sleep(min(1, max(0, deadline - self.monotonic())))
            response = self.api('POST', '/connections/remote-setup:recover', self._request(document))
            self._consume(document, response)

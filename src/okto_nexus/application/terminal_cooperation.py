"""Optional, resumable cooperation proof between authenticated identities.

The journal stores references and consent digests only. Productive requests use
TerminalCoordination's existing durable receipts; observation never acts for the
peer and never qualifies a particular model or client installation.
"""
from copy import deepcopy
import re
import time
import uuid

from .terminal_connection import ConnectionError, document_revision
from .terminal_coordination import TerminalCoordination, timestamp, utc_now


def _require(condition):
    if not condition:
        raise ValueError('Invalid cooperation contract')


def _identity(value):
    return type(value) is str and 0 < len(value) <= 160 and not any(ord(c) < 32 for c in value)


class TerminalCooperation:
    def __init__(self, mcp, scope, save, requests, document=None, *, now=utc_now,
                 monotonic=time.monotonic, sleep=time.sleep):
        self.mcp, self.scope, self.save, self.requests = mcp, dict(scope), save, requests
        self.document = deepcopy(document)
        self.now, self.monotonic, self.sleep = now, monotonic, sleep
        if self.document is not None:
            self.validate()

    def _flow(self, operation):
        identity = self.document['request_ids'][operation]
        checkpoint = self.requests.load(operation, identity)
        flow = TerminalCoordination(self.mcp, self.scope, self.requests.save, checkpoint,
            now=self.now, monotonic=self.monotonic, sleep=self.sleep)
        if checkpoint is not None and (checkpoint['operation'], checkpoint['client_request_id']) != (operation, identity):
            raise ConnectionError('CHECKPOINT_INVALID', 'The cooperation request checkpoint belongs to another intent.')
        return flow

    def validate(self):
        try:
            doc = self.document
            _require(type(doc) is dict and set(doc) == {'revision', 'test_revision', 'smoke_id', 'scope',
                'profile_binding', 'peer', 'session_id', 'request_ids', 'reviews', 'consents',
                'receipts', 'evidence', 'created_at', 'updated_at'})
            _require(type(doc['revision']) is int and doc['revision'] == 1)
            _require(type(doc['test_revision']) is int and doc['test_revision'] == 1)
            _require(doc['scope'] == self.scope and set(self.scope) == {'origin', 'server_id', 'agent_id', 'workspace_id'})
            _require(all(_identity(value) for value in self.scope.values()))
            _require(type(doc['smoke_id']) is str and re.fullmatch('smoke_[0-9a-f]{32}', doc['smoke_id']))
            _require(type(doc['profile_binding']) is str and re.fullmatch('[0-9a-f]{64}', doc['profile_binding']))
            _require(_identity(doc['peer']) and doc['peer'] != self.scope['agent_id'])
            _require(doc['session_id'] is None or _identity(doc['session_id']))
            _require(doc['request_ids'] == {op: doc['smoke_id'] + suffix for op, suffix in (
                ('message_create', ':message'), ('handoff_create', ':handoff'))})
            _require(timestamp(doc['created_at']) <= timestamp(doc['updated_at']))
            for field in ('reviews', 'consents', 'receipts', 'evidence'):
                _require(type(doc[field]) is dict and set(doc[field]) == {'exchange', 'handoff'})
            _require(doc['reviews']['exchange'] == self._digest('exchange'))
            for phase, operation in (('exchange', 'message_create'), ('handoff', 'handoff_create')):
                review, consent = doc['reviews'][phase], doc['consents'][phase]
                _require(consent is None or consent == review and review is not None)
                if phase == 'handoff' and review is not None:
                    _require(doc['evidence']['exchange'] is not None and review == self._digest(phase))
                receipt = doc['receipts'][phase]
                if receipt is not None:
                    _require(consent is not None)
                    TerminalCoordination(None, self.scope, None)._reference(receipt, operation, doc['request_ids'][operation])
            exchange = doc['evidence']['exchange']
            if exchange is not None:
                _require(set(exchange) == {'message_id', 'reply_message_id', 'authority_kind', 'runtime_outcome', 'observed_at'})
                _require(_identity(exchange['message_id']) and _identity(exchange['reply_message_id'])
                    and exchange['message_id'] != exchange['reply_message_id'])
                _require(doc['receipts']['exchange'] is not None and
                    exchange['message_id'] == doc['receipts']['exchange']['resource_id']
                    and doc['receipts']['exchange']['state'] in ('created', 'resource_removed', 'expired'))
                _require(self._authority(exchange))
                timestamp(exchange['observed_at'])
            handoff = doc['evidence']['handoff']
            if handoff is not None:
                _require(set(handoff) == {'handoff_id', 'claimed_by', 'claim_epoch', 'observed_at'})
                _require(_identity(handoff['handoff_id']) and doc['receipts']['handoff'] is not None
                    and handoff['handoff_id'] == doc['receipts']['handoff']['resource_id']
                    and doc['receipts']['handoff']['state'] in ('created', 'resource_removed', 'expired'))
                _require(handoff['claimed_by'] == doc['peer'] and type(handoff['claim_epoch']) is int and handoff['claim_epoch'] > 0)
                timestamp(handoff['observed_at'])
        except (KeyError, TypeError, ValueError, ConnectionError):
            raise ConnectionError('CHECKPOINT_INVALID', 'Preserve the invalid cooperation checkpoint for inspection; no work was sent.') from None

    def _store(self, *, possible_effect=False):
        local = self.now()
        if local < timestamp(self.document['updated_at']):
            raise ConnectionError('REQUEST_CLOCK_CHANGED', 'A clock moved backwards. Preserve the cooperation checkpoint.')
        self.document['updated_at'] = local.isoformat()
        self.validate()
        try:
            self.save(deepcopy(self.document))
        except Exception:
            raise ConnectionError('CHECKPOINT_WRITE_UNCONFIRMED' if possible_effect else 'CHECKPOINT_WRITE_FAILED',
                'The cooperation checkpoint could not be saved. Preserve this attempt and recover its original IDs.',
                possible_effect=possible_effect) from None

    def _required(self):
        if self.document is None:
            raise ConnectionError('REVIEW_REQUIRED', 'Review an optional directed exchange before sending work.')

    def _arguments(self, phase, session_secret=None):
        doc = self.document
        target = dict(strategy='direct', agent_id=doc['peer'])
        if phase == 'exchange':
            body = (
                'This is an optional Nexus cooperation test between identities. Responding may consume execution capacity '
                'and incur model/provider cost. Do not change files or start other work. If authorized to participate, '
                'respond with the canonical message_create tool, addressed directly to ' + self.scope['agent_id'] +
                ' in this workspace and channel, using parent_message_id equal to the message_id of this received '
                'message and client_request_id=' + doc['smoke_id'] + ':reply. A short acknowledgement is sufficient. '
                'Text alone is not proof; the canonical correlated reply is observed. Do not create or claim a handoff '
                'for this message. A handoff test requires separate consent.'
            )
            args = dict(target=target, subject='Optional Nexus cooperation exchange', body=body)
            session_field = 'from_session_id'
        else:
            exchange = doc['evidence']['exchange']
            args = dict(target=target, visibility='eligible', payload=dict(
                objective='Optional Nexus cooperation handoff test. Claim this exact handoff using handoff_claim, '
                    'then submit a non-null result using handoff_complete with the claim_epoch returned by that claim. '
                    'Do not change files or start other work. This separately consented test may consume execution '
                    'capacity and incur model/provider cost. Only the canonical claim and result prove completion.',
                smoke_id=doc['smoke_id'], message_id=exchange['message_id'], reply_message_id=exchange['reply_message_id']))
            session_field = 'session_id'
        if doc['session_id'] is not None:
            args[session_field] = doc['session_id']
            if session_secret is not None:
                args['session_secret'] = session_secret
        return args

    def _review(self, phase):
        doc = self.document
        return dict(revision=1, test_revision=doc['test_revision'], phase=phase, smoke_id=doc['smoke_id'],
            scope=deepcopy(self.scope), peer=doc['peer'], profile_binding=doc['profile_binding'],
            operation='message_create' if phase == 'exchange' else 'handoff_create',
            client_request_id=doc['request_ids']['message_create' if phase == 'exchange' else 'handoff_create'],
            arguments=self._arguments(phase),
            effects=['Send one directed message; the peer response may consume execution capacity and incur provider cost.']
                if phase == 'exchange' else ['Create one directed handoff; peer claim and completion may consume execution capacity and incur provider cost.'])

    def _digest(self, phase):
        return document_revision(self._review(phase))

    def review_exchange(self, peer, profile_binding, session_id=None):
        if not _identity(peer) or peer == self.scope.get('agent_id'):
            raise ConnectionError('REQUEST_INVALID', 'Choose a distinct canonical peer identity for the directed exchange.')
        if (type(profile_binding) is not str or not re.fullmatch('[0-9a-f]{64}', profile_binding)
                or session_id is not None and not _identity(session_id)):
            raise ConnectionError('REQUEST_INVALID', 'Use the participant profile revision digest and an optional explicit session ID.')
        if self.document is not None:
            if (peer, profile_binding, session_id) != tuple(self.document[key] for key in ('peer', 'profile_binding', 'session_id')):
                raise ConnectionError('REQUEST_CONFLICT', 'This attempt already names another peer, profile or session. Preserve it and review separate new work.')
        else:
            identity, created = 'smoke_' + uuid.uuid4().hex, self.now().isoformat()
            self.document = dict(revision=1, test_revision=1, smoke_id=identity, scope=self.scope,
                profile_binding=profile_binding, peer=peer, session_id=session_id,
                request_ids=dict(message_create=identity + ':message', handoff_create=identity + ':handoff'),
                reviews=dict(exchange=None, handoff=None), consents=dict(exchange=None, handoff=None),
                receipts=dict(exchange=None, handoff=None), evidence=dict(exchange=None, handoff=None),
                created_at=created, updated_at=created)
            self.document['reviews']['exchange'] = self._digest('exchange')
            self._store()
        return self._review_output('exchange')

    def _review_output(self, phase):
        return dict(self.status(), review_revision=self.document['reviews'][phase], review=self._review(phase))

    def _discover(self):
        self._flow('message_create').discover(observation=True)
        try:
            discovery = self.mcp.discover()
            contract = discovery['info']['coordination_cooperation']
            _require(type(contract['revision']) is int and contract['revision'] == 1)
            _require(contract['reply_tool'] == 'message_status' and contract['direct_replies'] is True
                and contract['authority_provenance'] is True)
            _require({'message_id', 'include_replies'} <= discovery['schemas']['message_status']['properties'].keys())
        except (KeyError, TypeError, ValueError):
            raise ConnectionError('SERVER_UPGRADE_REQUIRED', 'The Server does not advertise canonical cooperation reply evidence. No legacy test fallback is used.') from None

    def _approve(self, phase, approval):
        expected = self.document['reviews'][phase]
        if expected is None or approval != expected or expected != self._digest(phase):
            raise ConnectionError('REVIEW_REQUIRED', 'Approve the exact review revision for this cooperation phase.')

    def _remember(self, phase, result):
        receipt, old = result['request_receipt'], self.document['receipts'][phase]
        if old and (any(receipt[key] != old[key] for key in ('created_at', 'expires_at', 'approval_id'))
                or old['resource_id'] is not None and old['resource_id'] != receipt['resource_id']):
            raise ConnectionError('REQUEST_RESULT_UNCONFIRMED', 'The cooperation receipt changed its original references.', possible_effect=True)
        self.document['receipts'][phase] = deepcopy(receipt)
        self._store(possible_effect=True)

    def _submit(self, phase, approval, session_secret):
        self._approve(phase, approval)
        had_consent = self.document['consents'][phase] is not None
        self.document['consents'][phase] = approval
        self._store()
        operation = 'message_create' if phase == 'exchange' else 'handoff_create'
        flow = self._flow(operation)
        if flow.document is None and (had_consent or self.document['receipts'][phase] is not None):
            # Losing the local request file must not discard its replay window.
            # Prior consent may have preceded a lost response, even when this
            # journal never received the receipt. Only canonical inspection can
            # recover such an attempt; absence cannot authorize fresh deadlines.
            try:
                self._inspect(phase)
            except ConnectionError as error:
                if error.code == 'NOT_FOUND':
                    raise ConnectionError('NOT_FOUND',
                        'The previously consented request has no local checkpoint or retained receipt. '
                        'Preserve this attempt and its IDs for review; do not recreate it.', possible_effect=True) from None
                raise
            return self.status()
        result = flow.submit(operation, self.document['request_ids'][operation],
            self._arguments(phase, session_secret), observation=True)
        self._remember(phase, result)
        return self.status()

    def send_exchange(self, approval, *, session_secret=None):
        self._required()
        self._approve('exchange', approval)
        self._discover()
        return self._submit('exchange', approval, session_secret)

    @staticmethod
    def _authority(reply):
        return ((reply.get('authority_kind') == 'coordination_request' and reply.get('runtime_outcome') is None)
            or (reply.get('authority_kind') == 'runtime_result' and reply.get('runtime_outcome') == 'completed'))

    def _inspect(self, phase):
        operation = 'message_create' if phase == 'exchange' else 'handoff_create'
        try:
            result = self._flow(operation).inspect(operation, self.document['request_ids'][operation])
        except ConnectionError as error:
            if error.code == 'NOT_FOUND' and self.document['receipts'][phase] is not None:
                raise ConnectionError('REQUEST_RECEIPT_MISSING', 'A confirmed cooperation receipt is missing. Do not recreate the request.', possible_effect=True) from None
            raise
        self._remember(phase, result)
        return result

    def _exchange_snapshot(self):
        result = self._inspect('exchange')
        if result['state'] != 'created':
            return False
        message_id = result['message_id']
        value = self.mcp.call('message_status', dict(message_id=message_id, include_replies=True))
        try:
            _require(value['message_id'] == message_id and type(value['replies']) is list
                and type(value['replies_truncated']) is bool)
            _require(type(value['deliveries']) is list and type(value['count']) is int
                and value['count'] == len(value['deliveries']))
            _require(all(type(delivery) is dict for delivery in value['deliveries']))
            delivered = any(delivery.get('recipient') == self.document['peer']
                and delivery.get('status') in ('unread', 'delivered', 'read', 'parked')
                for delivery in value['deliveries'])
            if not delivered:
                return False
            selected = None
            previous = self.document['evidence']['exchange']
            for reply in value['replies']:
                _require(type(reply) is dict)
                if not (reply.get('parent_message_id') == message_id and reply.get('workspace_id') == self.scope['workspace_id']
                        and reply.get('from_agent_id') == self.document['peer']
                        and reply.get('target') == dict(strategy='direct', agent_id=self.scope['agent_id'])
                        and reply.get('delivery_status') in ('unread', 'delivered', 'read', 'parked') and self._authority(reply)):
                    continue
                _require(_identity(reply['message_id']) and reply['message_id'] != message_id)
                _require(timestamp(reply['created_at']) >= timestamp(result['request_receipt']['created_at']))
                _require('read_at' in reply and (reply['read_at'] is None or
                    timestamp(reply['read_at']) >= timestamp(reply['created_at'])))
                _require(reply['delivery_status'] != 'read' or reply['read_at'] is not None)
                evidence = dict(message_id=message_id, reply_message_id=reply['message_id'],
                    authority_kind=reply['authority_kind'], runtime_outcome=reply['runtime_outcome'],
                    observed_at=self.now().isoformat())
                if selected is None or previous and previous['reply_message_id'] == reply['message_id']:
                    selected = evidence
            if selected is not None:
                # A reviewed handoff binds the exact reply. A different reply is
                # valid exchange evidence, but cannot silently change consent.
                if self.document['reviews']['handoff'] is not None and previous != selected:
                    _require(previous['reply_message_id'] == selected['reply_message_id'])
                self.document['evidence']['exchange'] = selected
                self._store(possible_effect=True)
            return selected is not None
        except (KeyError, TypeError, ValueError):
            raise ConnectionError('REQUEST_RESULT_UNCONFIRMED', 'The Server did not return valid correlated reply evidence.', possible_effect=True) from None

    def review_handoff(self):
        self._required()
        if self.document['consents']['exchange'] is None:
            raise ConnectionError('REVIEW_REQUIRED', 'Complete the separately consented exchange before reviewing a handoff.')
        self._discover()
        if not self._exchange_snapshot():
            raise ConnectionError('REVIEW_REQUIRED', 'A current canonical reply from the chosen peer is required before a handoff review.')
        digest = self._digest('handoff')
        previous = self.document['reviews']['handoff']
        if previous is not None and previous != digest:
            raise ConnectionError('REQUEST_CONFLICT', 'The handoff review changed. Preserve the existing attempt.')
        self.document['reviews']['handoff'] = digest
        self._store(possible_effect=True)
        return self._review_output('handoff')

    def send_handoff(self, approval, *, session_secret=None):
        self._required()
        self._approve('handoff', approval)
        self._discover()
        if not self._exchange_snapshot():
            raise ConnectionError('REVIEW_REQUIRED', 'The peer reply must still be confirmed before creating a handoff.')
        return self._submit('handoff', approval, session_secret)

    def _handoff_evidence(self, result):
        if result['state'] != 'completed':
            return
        value, receipt = result['handoff'], self.document['receipts']['handoff']
        try:
            _require(value['handoff_id'] == receipt['resource_id'] and value['workspace_id'] == self.scope['workspace_id'])
            _require(value['from_agent_id'] == self.scope['agent_id'] and value['target'] == dict(strategy='direct', agent_id=self.document['peer']))
            _require(value['status'] == 'COMPLETED' and value['claimed_by'] == self.document['peer'])
            _require(type(value['claim_epoch']) is int and value['claim_epoch'] > 0 and value['result'] is not None)
        except (KeyError, TypeError, ValueError):
            raise ConnectionError('HANDOFF_RESULT_UNCONFIRMED', 'The exact peer claim and canonical result were not confirmed.') from None
        self.document['evidence']['handoff'] = dict(handoff_id=value['handoff_id'], claimed_by=value['claimed_by'],
            claim_epoch=value['claim_epoch'], observed_at=self.now().isoformat())
        self._store(possible_effect=True)

    def _observation_status(self, *, exchange=False, handoff=False):
        # A current observation must not inherit PASS from retained historical
        # evidence. This projection changes only returned copies; offline status
        # and the durable journal keep the original proof and its timestamp.
        output = self.status()
        output['historical'] = False
        for phase, check, confirmed in (('exchange', 'coordination_participation', exchange),
                                       ('handoff', 'handoff_test', handoff)):
            if not confirmed:
                output['checks'][check].update(status='UNKNOWN', evidence=None)
                output['evidence'][phase] = None
        return output

    def observe(self, timeout=300):
        TerminalCoordination._timeout(timeout)
        self._required()
        if self.document['consents']['exchange'] is None:
            return dict(self.status(), exit_code=3)
        deadline = self.monotonic() + timeout
        self._discover()
        args = dict(workspace_id=self.scope['workspace_id'], agent_id=self.scope['agent_id'], stream='workspace', passive=True)
        cursor = self.mcp.call('event_cursor', args).get('cursor')
        if type(cursor) is not int or cursor < 0:
            raise ConnectionError('EVENT_CURSOR_UNCONFIRMED', 'The cooperation observation cursor is invalid.')
        if self.document['consents']['handoff'] is not None:
            exchange_error = None
            try:
                exchange_confirmed = self._exchange_snapshot()
            except ConnectionError as error:
                if error.code.startswith('CHECKPOINT_') or error.code == 'REQUEST_CLOCK_CHANGED':
                    raise
                # Exchange evidence can be pruned or no longer visible while
                # the separately authorized handoff still needs observation.
                exchange_confirmed, exchange_error = False, error.code
            result = self._inspect('handoff')
            result = self._flow('handoff_create').wait_request(result, timeout=max(0, deadline - self.monotonic()))
            if result.get('handoff_id'):
                # wait_request may have crossed pending approval into creation.
                # Recover that reference before validating completion evidence.
                self._inspect('handoff')
            self._handoff_evidence(result)
            output = self._observation_status(exchange=exchange_confirmed, handoff=result['state'] == 'completed')
            if not exchange_confirmed:
                output['checks']['coordination_participation']['reason_code'] = exchange_error or 'REPLY_UNCONFIRMED'
            return dict(output, state='handoff_proven' if result['state'] == 'completed' else result['state'],
                historical=False, exit_code=result['exit_code'])
        while True:
            if self._exchange_snapshot():
                return dict(self._observation_status(exchange=True), exit_code=0)
            receipt = self.document['receipts']['exchange']
            if receipt['state'] not in ('created', 'pending_approval', 'approved_awaiting_execution'):
                return dict(self._observation_status(), state=receipt['state'], exit_code=3)
            remaining = deadline - self.monotonic()
            if remaining <= 0:
                return dict(self._observation_status(), state='timed_out', exit_code=4)
            page = self.mcp.call('event_wait', dict(args, cursor=cursor, filters={'type': 'message.created'},
                timeout_seconds=min(30, remaining)), timeout=min(35, remaining + 2))
            following = page.get('next_cursor')
            if type(following) is not int or following < cursor:
                raise ConnectionError('EVENT_CURSOR_UNCONFIRMED', 'The cooperation cursor did not advance safely.')
            cursor = following

    def status(self):
        if self.document is None:
            return dict(format=1, state='not_reviewed', historical=True, qualification='identities_only',
                checks={key: dict(status='UNKNOWN') for key in ('coordination_participation', 'handoff_test')}, possible_effect=False)
        doc = self.document
        phase = 'handoff' if doc['reviews']['handoff'] is not None else 'exchange'
        state = ('handoff_proven' if doc['evidence']['handoff'] else 'handoff_pending' if doc['consents']['handoff']
            else 'handoff_review' if doc['reviews']['handoff'] else 'exchange_proven' if doc['evidence']['exchange']
            else 'message_confirmed' if doc['receipts']['exchange'] and doc['receipts']['exchange']['state'] == 'created'
            else 'message_pending' if doc['consents']['exchange'] else 'message_review')
        output = dict(format=1, state=state, smoke_id=doc['smoke_id'], scope=deepcopy(self.scope), peer=doc['peer'],
            profile_binding=doc['profile_binding'], request_ids=deepcopy(doc['request_ids']),
            review_revision=doc['reviews'][phase], review=self._review(phase), reviews=deepcopy(doc['reviews']),
            consents=deepcopy(doc['consents']), receipts=deepcopy(doc['receipts']), evidence=deepcopy(doc['evidence']),
            historical=True, qualification='identities_only',
            possible_effect=any(doc['consents'][key] is not None and doc['receipts'][key] is None for key in ('exchange', 'handoff')),
            checks={name: dict(status='PASS' if doc['evidence'][kind] else 'UNKNOWN',
                evidence=deepcopy(doc['evidence'][kind])) for name, kind in (
                    ('coordination_participation', 'exchange'), ('handoff_test', 'handoff'))})
        for phase, key in (('exchange', 'message_id'), ('handoff', 'handoff_id')):
            receipt = doc['receipts'][phase]
            if receipt is not None and receipt['resource_id'] is not None:
                output[key] = receipt['resource_id']
        return output

"""Native domain operations with one canonical transaction and durable replay."""

import hashlib
import json

from nexus_connector_core.protocol import canonical_json

from ..domain.execution_principal import current_execution_principal, current_execution_tool
from ..errors import ErrorCode, OktoNexusError
from .execution_tools import NATIVE_ACTIONS, BoundExecutionConnectionFactory, denied

MAX_NATIVE_BYTES = 16 * 1024


def invalid(message='The native action request does not match the contract.'):
    return OktoNexusError(ErrorCode.VALIDATION_ERROR, message, {})


def identifier(value, maximum=160):
    return type(value) is str and 1 <= len(value) <= maximum and value.isprintable()


def validate_request(body):
    if (type(body) is not dict or set(body) != {'action_id', 'scope', 'action', 'payload'}
            or not identifier(body['action_id']) or type(body['action']) is not str
            or body['action'] not in NATIVE_ACTIONS or type(body['scope']) is not dict
            or type(body['payload']) is not dict):
        raise invalid()
    action, payload = body['action'], body['payload']
    required = ({'message'} if action == 'message_create' else set() if action == 'input_list'
                else {'request'} if action == 'input_respond' else {'handoff_id'})
    optional = set()
    if action == 'claim':
        required.add('idempotency_key')
        optional.add('claim_epoch')
    elif action == 'complete':
        required |= {'claim_epoch', 'result'}
    if not required <= payload.keys() or not payload.keys() <= required | optional:
        raise invalid()
    if action == 'message_create':
        message = payload['message']
        if (type(message) is not dict or not {'subject','body','target'} <= message.keys()
                or message.keys() - {'subject','body','target','channel_id','parent_message_id','artifacts'}):
            raise invalid('A native message supplies content and target; sender and workspace come from the session.')
    if 'handoff_id' in payload and not identifier(payload['handoff_id']):
        raise invalid()
    if action == 'input_respond' and (not isinstance(payload['request'], dict) or 'client_intent_id' in payload['request']):
        raise invalid()
    if action == 'claim' and not identifier(payload['idempotency_key'], 128):
        raise invalid()
    if 'claim_epoch' in payload and (type(payload['claim_epoch']) is not int or payload['claim_epoch'] < 1):
        raise invalid()
    try:
        encoded = canonical_json(body)
    except (ValueError, TypeError, RecursionError):
        raise invalid() from None
    if len(encoded) > MAX_NATIVE_BYTES:
        raise OktoNexusError("CAPACITY_EXCEEDED", 'The native action body is too large.', {})
    return encoded


class NativeActionService:
    def __init__(self, *, factory, capabilities, repository, build_handoff, clock, native_decisions=None, build_messages=None):
        self.factory, self.capabilities = factory, capabilities
        self.repository, self.build_handoff, self.clock = repository, build_handoff, clock
        self.native_decisions = native_decisions
        self.build_messages = build_messages

    def invoke(self, *, principal, body):
        encoded = validate_request(body)
        if (principal.audience != 'nexus-native-session'
                or canonical_json(body['scope']) != canonical_json(dict(principal.scope))):
            raise denied('The native action is outside this session scope.')
        action, payload, scope = body['action'], body['payload'], dict(principal.scope)
        digest = hashlib.sha256(encoded).hexdigest()
        principal_token = current_execution_principal.set(principal)
        action_token = current_execution_tool.set(NATIVE_ACTIONS[action])
        try:
            if action in {'input_list', 'input_respond'}:
                return self._input(principal, body)
            with self.factory.unit_of_work() as uow:
                self.capabilities.authorize_principal(uow, principal=principal,
                                                      actions=(NATIVE_ACTIONS[action],))
                factory = BoundExecutionConnectionFactory(self.factory, self.capabilities, uow)
                if action == 'message_create':
                    return self._message(uow, factory, principal, body, digest)
                handoffs = self.build_handoff(factory)
                prior = self.repository.get(uow, scope, body['action_id'])
                if prior:
                    if prior['request_digest'] != digest or prior['scope_json'] != canonical_json(scope).decode():
                        raise OktoNexusError(ErrorCode.CONFLICT,
                                             'The native action ID has different content.', {})
                    response = json.loads(prior['response_json'])
                    handoffs.authorize_native_replay(uow, workspace_id=scope['workspace_id'],
                        handoff_id=payload['handoff_id'], agent_id=scope['agent_id'],
                        action=action, claim_epoch=prior['claim_epoch'],
                        includes_payload='payload' in response['result'])
                    return response
                claim_key = payload.get('idempotency_key') if action == 'claim' else None
                if claim_key is not None and self.repository.claim_key_owner(uow, scope, claim_key):
                    raise OktoNexusError(ErrorCode.CONFLICT,
                        'This claim key already belongs to another action. Replay the original action ID.', {})
                args = dict(project_root=scope['workspace_id'], agent_id=scope['agent_id'],
                            handoff_id=payload['handoff_id'])
                if action == 'context':
                    result = handoffs.handoff_get(**args)
                elif action == 'claim':
                    result = handoffs.handoff_claim(**args, session_id=scope['session_id'],
                                                   claim_epoch=payload.get('claim_epoch'))
                else:
                    result = handoffs.handoff_complete(**args, session_id=scope['session_id'],
                        claim_epoch=payload['claim_epoch'], result=payload['result'])
                response = dict(action_id=body['action_id'], action=action,
                                state=result.get('status', 'SUCCEEDED'), result=result)
                response_json = canonical_json(response)
                if len(response_json) > MAX_NATIVE_BYTES:
                    # Roll back the domain mutation too: never claim work that the
                    # bridge cannot receive and never store an oversized receipt.
                    raise OktoNexusError("CAPACITY_EXCEEDED",
                                         'The native action result is too large. Use an artifact reference.', {})
                self.repository.record(uow, scope=scope, action_id=body['action_id'], action=action,
                    scope_json=canonical_json(scope).decode(), digest=digest, claim_key=claim_key,
                    handoff_id=payload['handoff_id'], response_json=response_json.decode(),
                    now=self.clock.now_iso())
            return response
        finally:
            current_execution_tool.reset(action_token)
            current_execution_principal.reset(principal_token)

    def _message(self, uow, factory, principal, body, digest):
        if self.build_messages is None:
            raise denied('Native messaging is unavailable.')
        scope = dict(principal.scope)
        prior = self.repository.get(uow, scope, body['action_id'])
        if prior:
            if prior['request_digest'] != digest or prior['scope_json'] != canonical_json(scope).decode():
                raise OktoNexusError(ErrorCode.CONFLICT, 'The native action ID has different content.', {})
            return json.loads(prior['response_json'])
        result = self.build_messages(factory).create_message(
            workspace_id=scope['workspace_id'], from_agent_id=scope['agent_id'], **body['payload']['message'])
        response = dict(action_id=body['action_id'], action='message_create',
                        state=result.get('status', 'SUCCEEDED'), result=result)
        encoded = canonical_json(response)
        if len(encoded) > MAX_NATIVE_BYTES:
            raise OktoNexusError('CAPACITY_EXCEEDED', 'The native message result is too large.', {})
        self.repository.record_message(uow, scope=scope, action_id=body['action_id'], digest=digest,
            response_json=encoded.decode(), now=self.clock.now_iso())
        return response

    def _input(self, principal, body):
        """Native decisions own their transaction, replay and response retention."""
        if self.native_decisions is None:
            raise denied('Native question responses are unavailable.')
        from ..domain.runtime_context import RuntimeRequestContext
        context = RuntimeRequestContext(principal.scope['agent_id'], 'session_capability')
        if body['action'] == 'input_list':
            items = self.native_decisions.pending_inputs(context=context, workspace_id=principal.scope['workspace_id'])
            result = {'items': [item['request_payload']['kwargs'] for item in items]}
        else:
            identity = canonical_json({'scope': dict(principal.scope), 'action_id': body['action_id']})
            request = dict(body['payload']['request'], client_intent_id='native-input-'+hashlib.sha256(identity).hexdigest())
            value, reused = self.native_decisions.confirm(context=context, request=request)
            result = {'decision': value, 'reused': reused}
        response = dict(action_id=body['action_id'], action=body['action'], state='SUCCEEDED', result=result)
        if len(canonical_json(response)) > MAX_NATIVE_BYTES:
            raise OktoNexusError('CAPACITY_EXCEEDED', 'The native question result is too large.', {})
        return response

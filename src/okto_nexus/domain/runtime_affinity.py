"""Logical session isolation shared by capacity selection and dispatch.

The caller supplies VERIFIED creator provenance, or the existing empty-origin
fallback. This module neither authenticates a user-supplied session ID nor owns
runtime state. The host receives only the opaque digest, never sender identity.
"""
from dataclasses import dataclass
from hashlib import sha256
import json


@dataclass(frozen=True)
class RuntimeAffinity:
    server_id: str
    executor_id: str
    binding_id: str
    workspace_id: str
    workspace_binding_id: str
    configuration_key: str
    policy: str
    sender_agent_id: str
    source_session_key: str

    @classmethod
    def for_binding(cls, binding, *, sender_agent_id=None, source_session_key=''):
        policy = binding['session_policy']
        if policy not in ('shared', 'per_sender', 'per_sender_session', 'one_shot'):
            raise ValueError('Unknown session isolation policy.')
        isolated = policy in ('per_sender', 'per_sender_session')
        if isolated and (type(sender_agent_id) is not str or not sender_agent_id):
            raise ValueError('Sender identity is required for an isolated session.')
        if type(source_session_key) is not str:
            raise ValueError('Invalid verified session origin.')
        # A realization and its revision describe the approved configuration.
        # Changing it never aliases a reservation for an older configuration.
        configuration = json.dumps([binding['realization_ref'], binding['realization_revision'],
                                    binding['binding_revision']], separators=(',', ':'))
        return cls(*(binding[k] for k in ('server_id', 'executor_id', 'binding_id',
                   'workspace_id', 'workspace_binding_id')), configuration, policy,
                   sender_agent_id if isolated else '',
                   source_session_key if policy == 'per_sender_session' else '')

    @property
    def per_sender(self):
        return self.policy in ('per_sender', 'per_sender_session')

    @property
    def uses_origin_fallback(self):
        return self.policy == 'per_sender_session' and not self.source_session_key

    @property
    def opaque_key(self):
        values = [1, self.server_id, self.executor_id, self.binding_id, self.workspace_id,
                  self.workspace_binding_id, self.configuration_key, self.policy,
                  self.sender_agent_id, self.source_session_key]
        return 'sha256:' + sha256(json.dumps(values, ensure_ascii=True, separators=(',', ':')).encode()).hexdigest()

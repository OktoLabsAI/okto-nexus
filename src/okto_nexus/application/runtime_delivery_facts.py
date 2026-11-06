"""Pure authority check shared by deferred transport and attention reads."""
import json

from ..domain.tag_selector import reachable
from ..errors import ErrorCode, OktoNexusError
from .runtime_requirements import validate_native_requirements, validate_native_requirements_descriptor


def require_delivery_facts(*, operation, config, actor, recipient, endpoint, profile,
                           actor_binding_valid, method_enabled, session_profile_revision,
                           original=None, original_profile=None, descriptor=None, legacy_descriptor=None):
    if operation.get('reconciliation_id'):
        raise OktoNexusError(ErrorCode.PERMISSION_DENIED, 'Transport attempt was administratively reconciled.', {})
    admission = json.loads(operation['admission_binding']) if operation.get('admission_binding') else None
    if admission:
        if (not original or original['revision'] != admission['revision'] or not original['enabled']
                or original['activation_state'] != 'approved' or original['selection_group'] != admission['selection_group']):
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED, 'Original fallback approval changed.', {})
        if admission['profile_id'] and (not original_profile or not original_profile['enabled']
                or original_profile['revision'] != admission['profile_revision']):
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED, 'Original fallback profile approval changed.', {})
    if admission and endpoint and endpoint['selection_group'] != admission['selection_group']:
        raise OktoNexusError(ErrorCode.PERMISSION_DENIED, 'Fallback equivalence approval changed.', {})
    if (not config.feature_harness_integrations or not actor or not actor.is_active or not actor_binding_valid
            or not recipient or not recipient.is_active or not reachable(actor, recipient)
            or not endpoint or not endpoint['enabled'] or endpoint['activation_state'] != 'approved'
            or endpoint['revision'] != operation['endpoint_revision'] or endpoint['health'] == 'quarantined'
            or endpoint['agent_id'] != recipient.agent_id or endpoint['workspace_id'] != operation['workspace_id']
            or endpoint['response_policy'] != 'conversation' or endpoint['consumption'] != 'exclusive'):
        raise OktoNexusError(ErrorCode.PERMISSION_DENIED, 'Transport authorization changed before dispatch.', {})
    if not method_enabled:
        raise OktoNexusError(ErrorCode.PERMISSION_DENIED, 'Connection method is disabled for this agent.', {})
    if endpoint['profile_id'] and (not profile or not profile['enabled'] or profile['revision'] != operation['profile_revision']):
        raise OktoNexusError(ErrorCode.PERMISSION_DENIED, 'Runtime profile changed before dispatch.', {})
    if profile and operation['runtime_session_id'] and session_profile_revision != profile['revision']:
        raise OktoNexusError(ErrorCode.PERMISSION_DENIED, 'Runtime must be reopened with the current approved profile.', {})
    if endpoint['protocol'] == 'nxl-r4':
        if (descriptor is None or descriptor.connection_mode != 'managed' or not profile
                or 'conversation' in profile['config'].get('disabled_capabilities', ())):
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED, 'Canonical conversation delivery is unavailable.', {})
        validate_native_requirements_descriptor(profile['config'], descriptor, hitl_enabled=config.feature_hitl)
        return endpoint, profile
    if callable(legacy_descriptor):
        legacy_descriptor = legacy_descriptor()
    if profile:
        validate_native_requirements(profile['config'], legacy_descriptor, hitl_enabled=config.feature_hitl)
        if 'conversation' in profile['config'].get('disabled_capabilities', ()):
            raise OktoNexusError(ErrorCode.CONFIG_ERROR, 'Profile disables conversation transport.', {})
    if not legacy_descriptor.capabilities.conversation:
        raise OktoNexusError(ErrorCode.CONFIG_ERROR, 'adapter_capability_unsupported: conversation is unavailable.',
            {'reason': 'adapter_capability_unsupported', 'capability': 'conversation'})
    return endpoint, profile

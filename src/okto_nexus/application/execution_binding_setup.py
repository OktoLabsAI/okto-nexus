"""Apply only the connection configuration covered by a binding approval."""
import json

from nexus_connector_core import CoreError
from nexus_connector_core.connection_configuration import (
    parse_portable_connection_configuration, materialize_connection_configuration,
)

from ..errors import ErrorCode, OktoNexusError


def validate_requested_configuration(request):
    value = request['connection_configuration']
    try:
        # The remote machine's paths and credentials never enter this contract.
        if not isinstance(value, dict) or value.get('version') != 2:
            raise ValueError()
        from .connection_authorization import normalize_authorization
        portable = parse_portable_connection_configuration(normalize_authorization(value))
        if portable['adapter_id'] != request['adapter_id'] or portable['alias'] != request['alias']:
            raise ValueError()
        if portable['runtime_enabled'] is not True:
            raise ValueError()
        return normalize_authorization(materialize_connection_configuration(portable, execution_location='remote'))
    except (CoreError, ValueError, TypeError):
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR,
                             'Invalid remote connection configuration.', {}) from None


def finish_approved_configuration(deps, uow, *, row, expected, proposal, context, operator):
    from ..bootstrap.execution_authority import ExecutionToolDependencies
    from ..domain.runtime_context import RuntimeRequestContext
    from .connection_setup import SetupTransaction, baseline, finish_setup

    if deps is None:
        raise OktoNexusError(ErrorCode.CONFLICT, 'Connection setup is unavailable.', {})
    if not operator:
        # Caller has already verified the committed approval, immutable diff,
        # current operator guard and subject guard in this same transaction.
        # Replay the recorded decision context only for this exact configuration.
        proof = json.loads(row['operator_proof_json'] or '{}')
        authority = proof.get('decision_context')
        if not authority or not expected.get('operator_approval_id'):
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED,
                                 'The connection requires an operator decision.', {})
        context = RuntimeRequestContext(**authority)
    scoped = ExecutionToolDependencies(deps, SetupTransaction(deps.connection_factory, uow))
    finish_setup(scoped, context, None, {}, dict(
        client_intent_id=proposal['proposal_id'] + '_setup',
        agent_id=proposal['agent_id'], executor_id=proposal['executor_id'],
        binding_id=proposal['binding_id'], workspace_id=proposal['workspace_id'],
        configuration=expected['connection_configuration'],
        baseline=baseline(uow, proposal['agent_id'], proposal['binding_id'])), verified=None)

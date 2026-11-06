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


def prepare_project_review(uow, request, configuration, settings):
    """A participant may request the preset; only its operator diff authorizes it."""
    preset = request.get('project_preset')
    if preset is None:
        return {}
    from .project_preset import ORIGIN
    if (not isinstance(preset, dict) or preset != ORIGIN or type(preset.get('revision')) is not int or
            configuration is None or configuration['runtime_enabled'] is not True or settings is None):
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR, 'Invalid remote project preset review.', {})
    policy = settings.native_decision_review(uow)
    review = dict(expected_revision=policy['revision'], initialize=policy['can_initialize'])
    settings.validate_native_decisions(uow, review)
    return dict(project_preset=dict(ORIGIN), native_decision_policy=review)


def validate_project_review(uow, expected, settings):
    if expected.get('project_preset') is None:
        return
    from .connection_setup import validate_native_policy
    if expected.get('native_decision_policy') is None:
        raise OktoNexusError(ErrorCode.CONFLICT, 'The project policy review is unavailable.', {})
    validate_native_policy(uow, dict(project_preset=expected['project_preset'],
        native_decision_policy=expected['native_decision_policy'],
        configuration=expected['connection_configuration']), settings)


def refresh_applied_project(factory, *, actor_agent_id, request, settings):
    """Publish only committed policy; replay refreshes the current stored choice."""
    if settings is None:
        return
    try:
        with factory.unit_of_work(write=False) as uow:
            row = uow.connection.execute('SELECT expected_revisions_json FROM execution_proposals '
                "WHERE actor_agent_id=? AND apply_client_intent_id=? AND status='APPLIED'",
                (actor_agent_id, request['client_intent_id'])).fetchone()
            expected = json.loads(row['expected_revisions_json']) if row else {}
        if expected.get('native_decision_policy', {}).get('initialize'):
            settings.refresh_native_decisions(factory)
    except Exception as error:
        # Apply already committed. Any failure in this post-commit cache
        # refresh must report that fact, including adapter and decode errors.
        # Preserve the cause; recovery reuses the intent instead of regranting.
        raise OktoNexusError(ErrorCode.CONFLICT,
            'Binding setup is committed; Server policy refresh is pending. Resume this same apply intent.',
            {'reason': 'SETUP_ACTIVATION_PENDING'}) from error


def finish_approved_configuration(deps, uow, *, row, expected, proposal, context, operator, settings=None):
    from ..bootstrap.execution_authority import ExecutionToolDependencies
    from ..domain.runtime_context import RuntimeRequestContext
    from .connection_setup import SetupTransaction, baseline, _finish_setup

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
    # Binding apply owns the real transaction. Defer the shared config refresh
    # to its outer wrapper, after this transaction actually commits.
    _finish_setup(scoped, context, None, {}, dict(
        client_intent_id=proposal['proposal_id'] + '_setup',
        agent_id=proposal['agent_id'], executor_id=proposal['executor_id'],
        binding_id=proposal['binding_id'], workspace_id=proposal['workspace_id'],
        configuration=expected['connection_configuration'],
        **{key: expected[key] for key in ('project_preset', 'native_decision_policy') if key in expected},
        baseline=baseline(uow, proposal['agent_id'], proposal['binding_id'])), verified=None, settings=settings)

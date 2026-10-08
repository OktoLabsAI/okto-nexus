"""Workspace-scoped preparation, binding and opening eligibility projections."""

import json

from .execution_binding_proposals import _require_binding_method
from .execution_binding_views import read_execution_binding
from .executor_inventory import load_current_executor_inventory
from .executor_inventory_views import read_executor_inventory
from ..errors import ErrorCode, OktoNexusError
from ..domain.runtime_context import RuntimeRequestContext


def read_runtime_options(factory, *, server_id, executor_id, agent_id, workspace_id,
                         fresh_publications, context, access, remote_ready):
    for value in (agent_id, executor_id):
        if not isinstance(value, str) or not 1 <= len(value) <= 160:
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, 'Invalid runtime-options scope.', {})
    if workspace_id is not None and (not isinstance(workspace_id, str) or not 1 <= len(workspace_id) <= 160):
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR, 'Invalid workspace ID.', {})
    # Bindings may materialize the current agent revision counters. All facts
    # and authorization checks use one transaction; no grant is consumed.
    with factory.unit_of_work() as uow:
        view = read_executor_inventory(factory, server_id=server_id, executor_id=executor_id,
            agent_id=agent_id, fresh_publications=fresh_publications, context=context, access=access, uow=uow)
        operator = access.authenticate(context, uow=uow, require_feature=False)
        snapshot = view['snapshot']
        common = []
        if view['freshness'] != 'FRESH':
            common.append('EXECUTOR_OFFLINE' if view['freshness'] == 'OFFLINE' else 'INVENTORY_STALE')
        try:
            load_current_executor_inventory(json.dumps(snapshot))
        except OktoNexusError:
            common.append('INVENTORY_INCOMPATIBLE')
        if not access.config.feature_harness_integrations:
            common.append('FEATURE_DISABLED')
        subject = access.agents.get(uow, agent_id)
        if subject is None or not subject.is_active:
            common.append('AGENT_DISABLED')
        try:
            access.require_admission('open')
        except OktoNexusError:
            common.append('RUNTIME_DRAINING')
        conn = uow.connection
        executor = conn.execute('SELECT kind,control_state FROM execution_executors WHERE server_id=? AND executor_id=?',
                                (server_id, executor_id)).fetchone()
        kind = executor['kind']
        from .execution_agent_recovery import agent_recovering
        recovering = agent_recovering(conn, server_id, executor_id, agent_id)
        descriptors = {item['adapter_id']: item for item in snapshot['catalog']['runtimes']}
        evidence = {(item['adapter_id'], item['candidate_ref']) for item in snapshot['evidence']}
        options = []
        for technical in snapshot['availability']['availability']:
            adapter, candidate = technical['adapter_id'], technical['candidate_ref']
            reasons = list(common)
            descriptor = descriptors.get(adapter)
            if descriptor is None or descriptor['support_status'] != 'managed_supported':
                reasons.append('ADAPTER_UNSUPPORTED')
            if not candidate or (adapter, candidate) not in evidence:
                reasons.append('INSTALLATION_REQUIRED')
            try:
                _require_binding_method(conn, subject_agent_id=agent_id, adapter_id=adapter)
            except OktoNexusError:
                reasons.append('METHOD_DISABLED')
            selectable = not reasons
            # Reviewing configuration does not grant execution authority.
            can_configure = bool(selectable and kind == 'embedded' and operator)
            from .agent_execution_policy import require_execution_location
            try:
                require_execution_location(uow, agent_id=agent_id, executor_id=executor_id, adapter_id=adapter)
            except OktoNexusError as error:
                reasons.append(error.details.get('reason', 'EXECUTION_LOCATION_RESTRICTED'))
                selectable = False
            can_prepare = selectable and (kind != 'embedded' or operator)
            if selectable and kind == 'embedded' and not operator:
                reasons.append('LOCAL_OPERATOR_REQUIRED')
            can_bind = can_start = False
            preparation = binding_view = None
            if workspace_id is None:
                reasons.append('WORKSPACE_REQUIRED')
            else:
                # Historical binding reads remain available when inventory or
                # execution readiness is lost. Eligibility still gates writes.
                # Never choose one realization/binding by list order.
                pending = conn.execute(
                    'SELECT r.realization_ref,r.revision AS realization_revision,r.workspace_binding_id '
                    'FROM execution_realizations r JOIN execution_workspace_bindings w '
                    'ON w.server_id=r.server_id AND w.executor_id=r.executor_id '
                    'AND w.workspace_binding_id=r.workspace_binding_id '
                    "WHERE r.server_id=? AND r.executor_id=? AND r.subject_agent_id=? AND w.workspace_id=? "
                    "AND r.candidate_ref=? AND r.inventory_revision=? AND r.status='PENDING_APPROVAL' "
                    "AND w.status='PENDING_APPROVAL' LIMIT 2",
                    (server_id, executor_id, agent_id, workspace_id, candidate, snapshot['inventory_revision'])).fetchall()
                bindings = conn.execute(
                    'SELECT b.binding_id FROM execution_bindings b JOIN agent_endpoints ep ON ep.endpoint_id=b.endpoint_id '
                    'WHERE b.server_id=? AND b.executor_id=? AND ep.agent_id=? AND ep.workspace_id=? '
                    'AND ep.adapter_id=? AND b.candidate_ref=? LIMIT 2',
                    (server_id, executor_id, agent_id, workspace_id, adapter, candidate)).fetchall()
                if len(pending) > 1:
                    reasons.append('REALIZATION_SELECTION_REQUIRED')
                elif pending:
                    can_bind = operator and selectable
                    preparation = dict(pending[0]) if operator and selectable else None
                    if not operator:
                        reasons.append('OPERATOR_APPROVAL_REQUIRED')
                elif not bindings:
                    reasons.append('PREPARATION_REQUIRED')
                if len(bindings) > 1:
                    reasons.append('BINDING_SELECTION_REQUIRED')
                elif not bindings:
                    reasons.append('BINDING_REQUIRED')
                else:
                    binding = read_execution_binding(factory, server_id=server_id,
                        binding_id=bindings[0]['binding_id'], context=context, access=access, uow=uow)
                    binding_view = binding
                    if binding['state'] != 'APPROVED':
                        reasons.append('BINDING_' + binding['state'])
                    elif not selectable:
                        pass
                    elif not remote_ready:
                        reasons.append('EXECUTION_UNAVAILABLE')
                    elif context.actor_agent_id != agent_id and not operator:
                        reasons.append('OPERATOR_REQUIRED')
                    else:
                        try:
                            # Project the exact grant that the dispatcher will
                            # consume. Operator status alone does not create it.
                            execution_context = RuntimeRequestContext(agent_id, 'agent_key',
                                credential_binding=subject.api_key_hash) if operator else context
                            grant = access.authorize(execution_context, action='open', endpoint_id=binding['endpoint_id'],
                                represented_agent_id=agent_id, workspace_id=workspace_id,
                                consume=False, audit=False, uow=uow)
                            if grant is None:
                                raise OktoNexusError(ErrorCode.PERMISSION_DENIED, 'A canonical execution grant is required.', {})
                        except OktoNexusError:
                            reasons.append('AUTHORIZATION_REQUIRED')
                        else:
                            can_start = (not recovering and executor['control_state'] == 'CONTROL_READY' and
                                         technical['state'] == 'READY_FOR_RUNTIME')
            if recovering:
                reasons.append('AGENT_RECOVERING')
            if executor['control_state'] != 'CONTROL_READY':
                reasons.append('EXECUTOR_RECOVERING' if executor['control_state'] == 'RECOVERING' else 'EXECUTOR_OFFLINE')
            if technical['state'] != 'READY_FOR_RUNTIME':
                reasons.append('TECHNICAL_NOT_READY')
            options.append(dict(adapter_id=adapter, candidate_ref=candidate, label=technical['label'],
                technical_state=technical['state'], technical_reasons=list(technical['reasons']),
                can_configure=can_configure,
                can_prepare=can_prepare, can_bind=can_bind, can_start=can_start,
                preparation=preparation, binding=binding_view,
                policy_reasons=list(dict.fromkeys(reasons))))
            if descriptor and descriptor['support_status'] == 'managed_supported':
                from nexus_connector_core import discover_harness_configuration
                options[-1]['harness_configuration'] = discover_harness_configuration(
                    adapter, version=technical.get('version'), candidate_ref=candidate or None)
                if binding_view:
                    from .execution_harness_configuration import read_harness_configuration
                    options[-1]['harness_configuration'] = read_harness_configuration(conn,
                        endpoint_id=binding_view['endpoint_id'], adapter_id=adapter,
                        version=technical.get('version'), candidate_ref=candidate or None)
            if kind == 'embedded' and operator and candidate:
                from nexus_connector_core import discover_provider_home
                options[-1]['provider_home_suggestion'] = discover_provider_home(adapter)
        return dict(agent_id=agent_id, executor_id=executor_id, inventory_revision=snapshot['inventory_revision'],
                    catalog=snapshot['catalog'], availability=snapshot['availability'],
                    freshness=view['freshness'], options=options)

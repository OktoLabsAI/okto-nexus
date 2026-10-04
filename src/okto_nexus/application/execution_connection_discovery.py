"""Read-only connection projections from the public Core catalog and R4 state."""
import time
from nexus_connector_core import get_runtime_catalog

from .connection_policy import method_enabled
from .executor_inventory import load_current_executor_inventory
from ..errors import ErrorCode, OktoNexusError


def canonical_methods(uow, agent_id):
    return [dict(method=item.adapter_id, protocol="nxl-r4",
        enabled=method_enabled(uow, agent_id, item.adapter_id), requires_endpoint=True,
        substrate=item.connection_mode, platform_compatible=None,
        platform_authority="executor", display_name=item.display_name)
        for item in get_runtime_catalog().runtimes]


def canonical_available(uow, *, access, context, endpoints, fresh, remote_ready):
    methods = []
    for descriptor in get_runtime_catalog().runtimes:
        enabled = method_enabled(uow, context.actor_agent_id, descriptor.adapter_id)
        blockers = []
        if not access.config.feature_harness_integrations:
            blockers.append("integrations_disabled")
        if not enabled:
            blockers.append("agent_method_disabled")
        if not remote_ready:
            blockers.append("execution_unavailable")
        if descriptor.connection_mode != "managed":
            blockers.append("managed_binding_required")
        rows = []
        for endpoint in endpoints:
            if endpoint["protocol"] != "nxl-r4" or endpoint["adapter_id"] != descriptor.adapter_id:
                continue
            reasons = list(blockers)
            try:
                access.authorize(context, action="open", endpoint_id=endpoint["endpoint_id"],
                    represented_agent_id=context.actor_agent_id, uow=uow, audit=False)
            except OktoNexusError as exc:
                if exc.code != ErrorCode.PERMISSION_DENIED:
                    raise
                reasons.append("open_authorization_or_configuration_required")
            bindings = uow.connection.execute(
                "SELECT b.*,e.control_state,e.revoked_at,w.status AS workspace_status,"
                "r.status AS realization_status,r.revision AS current_realization_revision,"
                "c.inventory_revision AS current_inventory_revision,c.publication_sequence,"
                "s.observation_age_ms,s.canonical_projection FROM execution_bindings b "
                "JOIN execution_installation i ON i.server_id=b.server_id "
                "JOIN execution_executors e ON e.server_id=b.server_id AND e.executor_id=b.executor_id "
                "JOIN execution_workspace_bindings w ON w.server_id=b.server_id AND w.executor_id=b.executor_id "
                "AND w.workspace_binding_id=b.workspace_binding_id "
                "JOIN execution_realizations r ON r.server_id=b.server_id AND r.executor_id=b.executor_id "
                "AND r.realization_ref=b.realization_ref "
                "LEFT JOIN execution_inventory_current c ON c.server_id=b.server_id AND c.executor_id=b.executor_id "
                "LEFT JOIN execution_inventory_snapshots s ON s.server_id=c.server_id AND s.executor_id=c.executor_id "
                "AND s.publication_sequence=c.publication_sequence WHERE b.endpoint_id=? LIMIT 2",
                (endpoint["endpoint_id"],)).fetchall()
            if len(bindings) != 1:
                reasons.append("canonical_binding_required")
            else:
                binding = bindings[0]
                if binding["control_state"] != "CONTROL_READY" or binding["revoked_at"] is not None:
                    reasons.append("executor_not_ready")
                if (binding["workspace_status"] != "READY" or binding["realization_status"] != "READY" or
                        binding["realization_revision"] != binding["current_realization_revision"]):
                    reasons.append("realization_not_ready")
                receipt = fresh.get((binding["server_id"], binding["executor_id"]))
                if (receipt is None or receipt[0] != binding["publication_sequence"] or
                        binding["observation_age_ms"] is None or binding["observation_age_ms"] +
                        max(0, int((time.monotonic() - receipt[1]) * 1000)) >= 120000):
                    reasons.append("inventory_not_fresh")
                else:
                    from .execution_inventory_revalidation import accepts_binding
                    if not accepts_binding(uow.connection, binding, binding['current_inventory_revision'],
                                           binding['server_id'], binding['executor_id']):
                        reasons.append("inventory_binding_review_required")
                    try:
                        snapshot = load_current_executor_inventory(binding["canonical_projection"])
                        if not any(item["adapter_id"] == descriptor.adapter_id and
                                   item["candidate_ref"] == binding["candidate_ref"] for item in snapshot["evidence"]):
                            reasons.append("candidate_not_current")
                    except OktoNexusError:
                        reasons.append("inventory_incompatible")
            row = dict(endpoint_id=endpoint["endpoint_id"], available=not reasons,
                       unavailable_reasons=reasons)
            if not reasons:
                row["connect"] = dict(tool="harness_list", arguments=dict(view="connections",
                    maintenance=dict(action="connect", endpoint_id=endpoint["endpoint_id"],
                                     idempotency_key="<unique-key-for-this-opening>")))
            rows.append(row)
        methods.append(dict(method=descriptor.adapter_id, protocol="nxl-r4", enabled=enabled,
            available=any(row["available"] for row in rows),
            unavailable_reasons=blockers + ([] if rows else ["endpoint_required"]),
            connection_mode="managed_runtime" if descriptor.connection_mode == "managed" else "approved_external_target",
            capability_verification="published_inventory", endpoints=rows))
    return methods

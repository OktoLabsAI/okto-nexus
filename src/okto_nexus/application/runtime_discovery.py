"""Bounded, authorized projection of canonical agent runtime bindings.

All facts come from one SQLite read snapshot. No peer calls, secret resolution,
or process-liveness inference; descriptor capabilities are declarations only.
"""
from dataclasses import asdict

from ..errors import ErrorCode, OktoNexusError


class RuntimeDiscoveryService:
    def __init__(self, *, access):
        self.access = access

    def list(self, context, *, agent_id=None, after_endpoint_id=None, limit=50):
        with self.access.cf.unit_of_work(write=False) as uow:
            operator = self.access.authenticate(context, uow=uow)
            if (type(limit) is not int or not 1 <= limit <= 100 or any(
                    value is not None and (not isinstance(value, str) or not value or len(value) > 256)
                    for value in (agent_id, after_endpoint_id))):
                raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Use limit 1..100 and bounded, nonempty identifiers.", {})
            now = self.access.clock.now_iso()
            query = "SELECT e.endpoint_id FROM agent_endpoints e WHERE e.endpoint_id>?"
            values = [after_endpoint_id or ""]
            if agent_id is not None:
                query += " AND e.agent_id=?"
                values.append(agent_id)
            if not operator:
                query += (" AND EXISTS (SELECT 1 FROM runtime_execution_grants g WHERE g.endpoint_id=e.endpoint_id"
                          " AND g.actor_agent_id=? AND g.credential_binding=? AND g.revoked_at IS NULL AND g.expires_at>?)")
                values.extend((context.actor_agent_id, context.credential_binding, now))
            # Scan bounds apply before authorization; never return a hidden ID as
            # a cursor. Filtering by agent allows callers to narrow large stores.
            candidates = uow.connection.execute(query + " ORDER BY e.endpoint_id LIMIT 1001", values).fetchall()
            visible = []
            for candidate in candidates[:1000]:
                endpoint_id = candidate[0]
                try:
                    self.access.authorize(context, action="discover", endpoint_id=endpoint_id, uow=uow, audit=False)
                except OktoNexusError as exc:
                    if exc.code != ErrorCode.PERMISSION_DENIED:
                        raise
                    continue
                visible.append(self.access.endpoints.get(uow, endpoint_id))
                if len(visible) > limit:
                    break
            if len(candidates) > 1000 and len(visible) <= limit:
                raise OktoNexusError(ErrorCode.QUOTA_EXCEEDED, "Discovery scan limit reached; narrow agent_id.", {})
            owner = uow.connection.execute("SELECT epoch,lease_expires_at FROM runtime_dispatcher_owner WHERE owner_key='dispatcher'").fetchone()
            groups = {}
            for endpoint in visible[:limit]:
                item = self._endpoint(uow, endpoint, owner, now)
                agent_id = endpoint["agent_id"]
                if agent_id not in groups:
                    agent = self.access.agents.get(uow, agent_id)
                    groups[agent_id] = {"agent_id": agent_id,
                        "skill_names": sorted(key for key, value in agent.capabilities.items() if value) if agent else [],
                        "endpoints": []}
                groups[agent_id]["endpoints"].append(item)
            more = len(visible) > limit
            return {"agents": list(groups.values()), "has_more": more,
                    "next_endpoint_id": visible[limit - 1]["endpoint_id"] if more else None}

    def _endpoint(self, uow, endpoint, owner, now):
        descriptor = self.access.registry.get(endpoint["adapter_id"])
        profile = self.access.endpoints.profile(uow, endpoint["profile_id"]) if endpoint["profile_id"] else None
        item = {key: endpoint[key] for key in ("endpoint_id", "adapter_id", "protocol", "workspace_id",
                "profile_id", "revision", "health", "response_policy", "consumption")}
        item.update(enabled=bool(endpoint["enabled"]), profile_revision=profile["revision"] if profile else None,
                    declared_capabilities=asdict(descriptor.capabilities), capability_verification="not_probed")
        rows = uow.connection.execute("SELECT session_id,status,lifecycle_state,owner_epoch,runtime_profile_revision,started_at,ended_at "
            "FROM harness_sessions WHERE endpoint_id=? ORDER BY started_at DESC,session_id DESC LIMIT 11", (endpoint["endpoint_id"],)).fetchall()
        sessions = []
        for row in rows[:10]:
            session = dict(row)
            session["current_owner_ready_record"] = bool(
                row["lifecycle_state"] == "protocol_ready" and owner and owner["epoch"] == row["owner_epoch"]
                and owner["lease_expires_at"] > now and endpoint["enabled"] and endpoint["activation_state"] == "approved"
                and endpoint["health"] != "quarantined" and (not endpoint["profile_id"] or (
                    profile and profile["enabled"] and profile["revision"] == row["runtime_profile_revision"])))
            session["process_liveness"] = "not_probed"
            sessions.append(session)
        item.update(sessions=sessions, sessions_has_more=len(rows) > 10)
        return item

"""Transactional causal admission; no session-local state, transport or telemetry."""
from ..domain.base import iso_plus, new_id
from ..errors import ErrorCode, OktoNexusError


class RuntimeCausalityService:
    def __init__(self, *, config, agents):
        self.config, self.agents = config, agents

    @staticmethod
    def node(uow, message_id):
        row = uow.connection.execute("SELECT n.*,r.deadline,r.max_depth,r.max_messages,r.max_executions "
            "FROM runtime_message_causality n JOIN runtime_causal_roots r USING(root_operation_id) WHERE n.message_id=?",
            (message_id,)).fetchone()
        return dict(row) if row else None

    def record(self, uow, *, message, context, now, source_result_id=None, authorized_work=False):
        existing = self.node(uow, message.message_id)
        if existing:
            return existing
        parent = self.node(uow, message.parent_message_id) if message.parent_message_id else None
        if source_result_id:
            # A late result remains an observation even beyond the admission
            # deadline. Recording evidence does not authorize a new execution.
            if not parent:
                return None  # Legacy result, never silently minted as a new root.
            purpose, depth, root = "observation", parent["hop_count"] + 1, parent["root_operation_id"]
        else:
            if not context or context.authentication_source != "agent_key" or not context.credential_binding:
                return None
            actor = self.agents.get(uow, context.actor_agent_id)
            if (not actor or not actor.is_active or actor.api_key_hash != context.credential_binding or
                    (not authorized_work and actor.agent_id not in {message.from_agent_id, "operator"})):
                raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "Causal entry requires an authenticated sender.", {})
            if message.parent_message_id:
                if not parent:
                    raise OktoNexusError(ErrorCode.CONFLICT, "Parent has no verified causal lineage; explicitly start a new conversation.", {})
                allowed = uow.connection.execute("SELECT 1 FROM messages WHERE message_id=? AND from_agent_id=? "
                    "UNION ALL SELECT 1 FROM message_deliveries WHERE message_id=? AND recipient_agent_id=?",
                    (message.parent_message_id, message.from_agent_id) * 2).fetchone()
                if not allowed and actor.agent_id != "operator":
                    raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "Causal parent is outside the sender's delivery audience.", {})
                root, depth, purpose = parent["root_operation_id"], parent["hop_count"] + 1, "continuation"
                if depth > parent["max_depth"] or parent["deadline"] <= now:
                    raise OktoNexusError(ErrorCode.QUOTA_EXCEEDED, "Causal depth or root deadline exhausted.", {})
                changed = uow.connection.execute("UPDATE runtime_causal_roots SET generated_messages=generated_messages+1 "
                    "WHERE root_operation_id=? AND generated_messages<max_messages AND deadline>?", (root, now)).rowcount
                if not changed:
                    raise OktoNexusError(ErrorCode.QUOTA_EXCEEDED, "Causal message budget exhausted.", {})
            else:
                since = iso_plus(now, -60)
                actor_count = uow.connection.execute("SELECT count(*) FROM runtime_causal_roots WHERE actor_agent_id=? AND created_at>=?",
                    (actor.agent_id, since)).fetchone()[0]
                workspace_count = uow.connection.execute("SELECT count(*) FROM runtime_causal_roots WHERE workspace_id=? AND created_at>=?",
                    (message.workspace_id, since)).fetchone()[0]
                if actor_count >= self.config.max_new_roots_per_agent_per_minute or workspace_count >= self.config.max_new_roots_per_workspace_per_minute:
                    raise OktoNexusError(ErrorCode.QUOTA_EXCEEDED, "New causal root quota exhausted.", {})
                root, depth, purpose = new_id("rootop"), 0, "entry"
                uow.connection.execute("INSERT INTO runtime_causal_roots(root_operation_id,workspace_id,actor_agent_id,created_at,deadline,"
                    "max_depth,max_messages,max_executions) VALUES(?,?,?,?,?,?,?,?)", (root, message.workspace_id, actor.agent_id, now,
                    iso_plus(now, self.config.root_deadline_seconds), self.config.max_relay_depth,
                    self.config.max_generated_messages_per_root, self.config.max_executions_per_root))
        uow.connection.execute("INSERT INTO runtime_message_causality VALUES(?,?,?,?,?,?)",
            (message.message_id, root, message.parent_message_id, depth, purpose, source_result_id))
        return self.node(uow, message.message_id)

    def reserve_execution(self, uow, *, message_id, now):
        node = self.node(uow, message_id)
        if not node or node["purpose"] == "observation" or node["hop_count"] > node["max_depth"]:
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "No executable causal admission.", {})
        changed = uow.connection.execute("UPDATE runtime_causal_roots SET admitted_executions=admitted_executions+1 "
            "WHERE root_operation_id=? AND admitted_executions<max_executions AND deadline>?",
            (node["root_operation_id"], now)).rowcount
        if not changed:
            raise OktoNexusError(ErrorCode.QUOTA_EXCEEDED, "Causal execution budget or deadline exhausted.", {})
        return node

    def admit_result_relay(self, uow, *, message_id, source_result_id, now):
        node = self.node(uow, message_id)
        if not node or node["source_result_id"] != source_result_id or node["purpose"] != "observation":
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "Result has no correlated causal observation.", {})
        if node["hop_count"] > node["max_depth"]:
            raise OktoNexusError(ErrorCode.QUOTA_EXCEEDED, "Causal depth exhausted.", {})
        changed = uow.connection.execute("UPDATE runtime_causal_roots SET generated_messages=generated_messages+1 "
            "WHERE root_operation_id=? AND generated_messages<max_messages AND deadline>?",
            (node["root_operation_id"], now)).rowcount
        if not changed:
            raise OktoNexusError(ErrorCode.QUOTA_EXCEEDED, "Causal message budget or deadline exhausted.", {})
        uow.connection.execute("UPDATE runtime_message_causality SET purpose='continuation' WHERE message_id=?", (message_id,))

    def validate_dispatch(self, uow, *, operation, now):
        node = self.node(uow, operation["message_id"])
        if (not node or node["purpose"] == "observation" or node["root_operation_id"] != operation["root_operation_id"]
                or node["deadline"] <= now or node["hop_count"] > node["max_depth"]):
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "Causal dispatch admission expired or unavailable.", {})

    @staticmethod
    def context(node):
        return {key: node[key] for key in ("root_operation_id", "parent_message_id", "hop_count", "deadline",
                                           "max_depth", "max_messages", "max_executions")}

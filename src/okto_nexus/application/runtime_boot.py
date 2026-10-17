"""Bounded startup of explicitly approved stable endpoint bindings."""
import time
import hashlib
import json
from datetime import datetime

from ..domain.runtime_context import RuntimeRequestContext
from ..errors import OktoNexusError


def next_boot_intent_key(conn, *, server_id, agent_id, binding_id, key, now):
    """Replace only a resolution that can provably never be submitted.

    Accepted operations retain their original intent even after a failed/lost
    response. Immutable blocked/expired resolutions with no admitted operation
    get a new attempt; concurrent callers choose the same next key.
    """
    prior = conn.execute(
        'SELECT i.client_intent_id,i.resolved_json,EXISTS(SELECT 1 FROM execution_operations o '
        'WHERE o.server_id=i.server_id AND o.operation_id=i.operation_id) admitted '
        'FROM execution_client_intents i WHERE i.server_id=? AND i.actor_agent_id=? '
        'AND (i.client_intent_id=? OR i.client_intent_id GLOB ?) '
        'ORDER BY length(i.client_intent_id) DESC,i.client_intent_id DESC LIMIT 1',
        (server_id, agent_id, key, key + ':retry:[0-9]*')).fetchone()
    if prior is None:
        return key
    previous_key = prior['client_intent_id']
    resolution = json.loads(prior['resolved_json'])
    if (prior['admitted'] or resolution['scope']['binding_id'] != binding_id or
            resolution['semantic_intent']['action'] != 'runtime.open'):
        return previous_key
    expired = datetime.fromisoformat(resolution['expires_at']) <= datetime.fromisoformat(now.replace('Z', '+00:00'))
    if resolution['can_submit'] and not resolution['blockers'] and not expired:
        return previous_key
    suffix = previous_key.removeprefix(key + ':retry:')
    if previous_key != key and not suffix.isdecimal():
        return previous_key  # Unexpected content never grants a fresh attempt.
    return key + ':retry:' + str(1 if previous_key == key else int(suffix) + 1)


class RuntimeBootService:
    def __init__(self, *, connection_factory, endpoints, registry, open_service, owner_id, owner_epoch, canonical_open=None):
        self.cf, self.endpoints, self.registry, self.open_service = connection_factory, endpoints, registry, open_service
        self.owner_id, self.owner_epoch = owner_id, owner_epoch
        self.canonical_open = canonical_open

    def run(self, *, budget_seconds=30, exclude_endpoint_ids=()):
        deadline = time.monotonic() + min(max(budget_seconds, 0), 30)
        with self.cf.unit_of_work(write=False) as uow:
            bindings = [binding for binding in self.endpoints.boot_candidates(uow)
                        if binding['endpoint_id'] not in exclude_endpoint_ids]
        results = []
        for index, binding in enumerate(bindings):
            endpoint_id = binding["endpoint_id"]
            remaining = deadline - time.monotonic()
            if index >= 16 or remaining <= 0:
                results.append({"endpoint_id": endpoint_id, "state": "deferred", "reason": "startup_budget"})
                continue
            context = RuntimeRequestContext(actor_agent_id=None, authentication_source="runtime_boot",
                represented_agent_id=binding["agent_id"], endpoint_id=endpoint_id, workspace_id=binding["workspace_id"],
                runtime_owner_id=self.owner_id, runtime_owner_epoch=self.owner_epoch)
            try:
                key = f"boot:{self.owner_epoch}:" + hashlib.sha256(endpoint_id.encode()).hexdigest()
                if binding.get("protocol") == "nxl-r4" and self.canonical_open is not None:
                    operation = self.canonical_open(context, endpoint_id, key)
                    results.append(dict(endpoint_id=endpoint_id, state=operation["admission_state"],
                        session_id=operation["scope"]["session_id"], operation_id=operation["operation_id"],
                        reused=operation["reused"]))
                    continue
                descriptor = self.registry.get(binding["adapter_id"])
                session, _, reused, request_id = self.open_service.open(context,
                    agent_id=binding["agent_id"], kind=descriptor.kind, substrate=descriptor.substrate,
                    project_root=binding["root_realpath"], endpoint_id=endpoint_id,
                    idempotency_key=key, startup_timeout_s=remaining)
                results.append({"endpoint_id": endpoint_id, "state": session.lifecycle_state,
                    "session_id": session.session_id, "request_id": request_id, "reused": reused})
            except OktoNexusError as exc:
                results.append({"endpoint_id": endpoint_id, "state": "blocked", "reason": str(exc.code),
                    "retryable": exc.retryable or exc.code == 'CONFLICT'})
        return results

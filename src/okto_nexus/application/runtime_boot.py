"""Bounded startup of explicitly approved stable endpoint bindings."""
import time
import hashlib

from ..domain.runtime_context import RuntimeRequestContext
from ..errors import OktoNexusError


class RuntimeBootService:
    def __init__(self, *, connection_factory, endpoints, registry, open_service, owner_id, owner_epoch):
        self.cf, self.endpoints, self.registry, self.open_service = connection_factory, endpoints, registry, open_service
        self.owner_id, self.owner_epoch = owner_id, owner_epoch

    def run(self, *, budget_seconds=30):
        deadline = time.monotonic() + min(max(budget_seconds, 0), 30)
        with self.cf.unit_of_work(write=False) as uow:
            bindings = self.endpoints.boot_candidates(uow)
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
                descriptor = self.registry.get(binding["adapter_id"])
                session, _, reused, request_id = self.open_service.open(context,
                    agent_id=binding["agent_id"], kind=descriptor.kind, substrate=descriptor.substrate,
                    project_root=binding["root_realpath"], endpoint_id=endpoint_id,
                    idempotency_key=f"boot:{self.owner_epoch}:" + hashlib.sha256(endpoint_id.encode()).hexdigest(), startup_timeout_s=remaining)
                results.append({"endpoint_id": endpoint_id, "state": session.lifecycle_state,
                    "session_id": session.session_id, "request_id": request_id, "reused": reused})
            except OktoNexusError as exc:
                results.append({"endpoint_id": endpoint_id, "state": "blocked", "reason": str(exc.code)})
        return results

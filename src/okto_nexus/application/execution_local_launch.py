"""Resolve approved embedded selections at the Core launch boundary."""
import asyncio
from dataclasses import asdict, replace
import json
import os
import re
import time

from nexus_connector_core import CoreError
from nexus_connector_core.environment import child_environment

from ..adapters.outbound.sqlite.execution_agent_revisions import current_agent_revisions
from .execution_binding_proposals import _agent_guard
from .execution_local_realizations import _digest, directory_identity
from ..adapters.outbound.execution.core_inventory import resolve_local_installation_selection
from nexus_connector_core.discovery import selected_fingerprint


def _refuse():
    return CoreError("PROFILE_DRIFT", "local_configuration",
                     message="The approved local execution configuration changed.")


class ProviderSecretResolver:
    """Resolve explicitly consented provider references from this host only."""
    def __init__(self, vault=None):
        self.vault = vault

    async def resolve(self, reference):
        from ..adapters.outbound.provider_vault import ProviderVaultError, validate_provider_secret
        prefix, _, name = reference.partition(":")
        if prefix=="vault" and self.vault is not None:
            try:
                return await asyncio.to_thread(self.vault.resolve,reference)
            except ProviderVaultError:
                raise CoreError("PROVIDER_AUTH_REQUIRED", "environment", retry_safe=True) from None
        if prefix != "provider" or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", name):
            raise CoreError("PROVIDER_AUTH_REQUIRED", "environment", retry_safe=True)
        value = os.environ.get(name)
        try:
            return validate_provider_secret(value)
        except ProviderVaultError:
            raise CoreError("PROVIDER_AUTH_REQUIRED", "environment", retry_safe=True)


class ApprovedLocalLaunch:
    def __init__(self, owner, scope, *, resolver=None):
        self.owner = owner
        self.scope = dict(scope)
        from ..adapters.outbound.provider_vault import ProviderVault
        self.resolver = resolver or ProviderSecretResolver(ProviderVault(owner.deps.config.home_dir,scope["agent_id"]))
        self._snapshot, self.candidate, self.record = self._read()
        self.workspace_root = self.record["root"]["path"]
        self.auth_refs = tuple(sorted(set(self.record["configuration"]["secret_bindings"].values())))
        self.tools = None

    def _database(self):
        owner, scope = self.owner, self.scope
        deps = owner.deps
        if (scope["server_id"], scope["executor_id"]) != (owner.key.server_id, owner.key.executor_id):
            raise _refuse()
        _, revisions, _ = current_agent_revisions(deps.connection_factory, agent_id=scope["agent_id"])
        if (revisions.authorization, revisions.configuration, revisions.credential_epoch) != tuple(
                scope[k] for k in ("authorization_revision", "configuration_revision", "credential_epoch")):
            raise _refuse()
        with deps.connection_factory.unit_of_work(write=False) as uow:
            if not owner.dispatcher.repo.owns(uow, owner_id=owner.dispatcher.owner_id,
                    epoch=owner.dispatcher.epoch, now=deps.clock.now_iso()):
                raise _refuse()
            row = uow.connection.execute(
                "SELECT l.local_record_json,r.configuration_digest,r.local_root_proof_digest,r.body_hash,"
                "r.local_consent_id,r.subject_agent_id,r.candidate_ref,r.inventory_revision,"
                "p.revision AS profile_revision,ep.adapter_id,a.is_active "
                "FROM execution_bindings b "
                "JOIN execution_executors e ON e.server_id=b.server_id AND e.executor_id=b.executor_id "
                "JOIN execution_realizations r ON r.server_id=b.server_id AND r.executor_id=b.executor_id AND r.realization_ref=b.realization_ref "
                "JOIN execution_local_realizations l ON l.server_id=r.server_id AND l.executor_id=r.executor_id AND l.realization_ref=r.realization_ref "
                "JOIN execution_workspace_bindings w ON w.server_id=b.server_id AND w.executor_id=b.executor_id AND w.workspace_binding_id=b.workspace_binding_id "
                "JOIN agent_endpoints ep ON ep.endpoint_id=b.endpoint_id "
                "JOIN runtime_profiles p ON p.profile_id=ep.profile_id "
                "JOIN agents a ON a.agent_id=ep.agent_id "
                "JOIN execution_sessions s ON s.server_id=b.server_id AND s.executor_id=b.executor_id AND s.binding_id=b.binding_id "
                "WHERE b.server_id=? AND b.executor_id=? AND b.binding_id=? AND b.binding_revision=? "
                "AND b.workspace_binding_id=? AND w.workspace_id=? AND ep.agent_id=? "
                "AND s.session_id=? AND s.owner_generation=? AND s.workspace_id=w.workspace_id "
                "AND s.workspace_binding_id=w.workspace_binding_id AND s.lifecycle_state IN ('OPEN_PENDING','READY') "
                "AND e.kind='embedded' AND e.owner_instance_id=? AND e.generation=? AND e.revoked_at IS NULL "
                "AND e.control_state='CONTROL_READY' AND r.status='READY' AND w.status='READY' "
                "AND b.realization_revision=r.revision AND r.candidate_ref=b.candidate_ref AND r.inventory_revision=b.inventory_revision "
                "AND p.enabled=1 AND ep.enabled=1 AND ep.activation_state='approved' AND ep.protocol='nxl-r4' "
                "AND ep.health<>'quarantined'",
                (scope["server_id"], scope["executor_id"], scope["binding_id"], scope["binding_revision"],
                 scope["workspace_binding_id"], scope["workspace_id"], scope["agent_id"], scope["session_id"],
                 scope["session_owner_generation"], owner.dispatcher.owner_id, owner.generation)).fetchone()
            if row is None or not row["is_active"] or row["subject_agent_id"] != scope["agent_id"]:
                raise _refuse()
            guard = _agent_guard(uow.connection, scope["agent_id"])
            return dict(row), guard

    def _read(self):
        owner, scope = self.owner, self.scope
        row, guard = self._database()
        try:
            record = json.loads(row["local_record_json"])
            configuration = record["configuration"]
            if (_digest(configuration) != row["configuration_digest"]
                    or _digest(record["publication"]) != row["body_hash"]
                    or configuration["local_consent_id"] != row["local_consent_id"]
                    or configuration["profile_revision"] != row["profile_revision"]
                    or configuration["adapter_id"] != row["adapter_id"]
                    or any(configuration[k] != scope[k] for k in ("server_id", "executor_id", "agent_id"))
                    or configuration["provider_home"] != record["provider_home"]):
                raise _refuse()
            proof = dict(root=record["root"], nonce=record["root_proof_nonce"],
                         agent_id=scope["agent_id"], server_id=scope["server_id"], executor_id=scope["executor_id"])
            if _digest(proof) != row["local_root_proof_digest"]:
                raise _refuse()
            candidate = resolve_local_installation_selection(owner.candidates,
                adapter_id=row["adapter_id"], candidate_ref=row["candidate_ref"],
                expected_inventory_revision=row["inventory_revision"])
            if asdict(candidate) != record["candidate"] or selected_fingerprint(candidate) != candidate.fingerprint:
                raise _refuse()
            if directory_identity(record["root"]["path"]) != record["root"]:
                raise _refuse()
            if record["provider_home"] is not None and directory_identity(record["provider_home"]["path"]) != record["provider_home"]:
                raise _refuse()
            if self._database() != (row, guard):
                raise _refuse()
            # Discovery is intentionally untrusted. The exact installation has
            # now passed current binding, operator consent, identity and drift
            # checks, so grant selection only to this scoped launch copy.
            return _digest(dict(row=row, agent_guard=guard)), replace(candidate, trust='selected'), record
        except (KeyError, TypeError, ValueError, OSError):
            raise _refuse() from None

    def check(self):
        snapshot, _, _ = self._read()
        if snapshot != self._snapshot:
            raise _refuse()

    async def environment(self, prepared):
        await asyncio.to_thread(self.check)
        if (prepared.intent.adapter_id != self.candidate.adapter_id
                or prepared.intent.agent_id != self.scope["agent_id"]
                or prepared.intent.workspace_id != self.scope["workspace_id"]
                or set(prepared.secret_refs) != set(self.auth_refs)):
            raise _refuse()
        home = self.record["provider_home"]
        resolver,templates=self.resolver,()
        provider_home=home["path"] if home else None
        def tools_current():
            if self.tools is not None:
                if time.monotonic()>=self.tools["deadline"]:
                    raise CoreError("AUTH_EXPIRED","local_tool_configuration")
                if self.tools["home"] is not None:
                    self.tools["home"].require_current()
        if self.tools is not None:
            config=self.tools
            base=self.resolver
            class ToolResolver:
                async def resolve(self,reference):
                    if reference==config["cap"]["capability_ref"]:
                        return config["cap"]["capability"]
                    return await base.resolve(reference)
            resolver=ToolResolver()
            if config["template"] is not None:
                templates=(config["template"],)
                if config["home"] is not None:
                    provider_home=str(config["home"].home)
        await asyncio.to_thread(tools_current)
        value = await child_environment(prepared, resolver,
            secret_bindings=self.record["configuration"]["secret_bindings"],
            provider_home=provider_home, trusted_home=provider_home is not None,http_templates=templates,
            process_http=bool(self.tools and self.tools.get("process_http")))
        await asyncio.to_thread(tools_current)
        await asyncio.to_thread(self.check)
        return value

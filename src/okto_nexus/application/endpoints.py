"""Canonical endpoint/profile use cases. No subprocess or secret I/O in UoWs."""
from pathlib import Path

from ..domain.endpoints import AgentEndpoint
from ..domain.ids import resolve_realpath, resolve_workspace_id
from ..errors import ErrorCode, OktoNexusError
from .runtime_authorization import authorize_runtime, require_runtime_agent


class EndpointService:
    def __init__(self, *, connection_factory, agents, workspaces, repo, registry, config, clock):
        self.cf, self.agents, self.workspaces, self.repo = connection_factory, agents, workspaces, repo
        self.registry, self.config, self.clock = registry, config, clock

    def authorize(self, context):
        authorize_runtime(context, config=self.config, agents=self.agents, connection_factory=self.cf)

    def create_profile(self, context, *, profile_id, adapter_id, config=None, secret_refs=None,
                       inherit_ambient=False, enabled=False):
        self.authorize(context)
        descriptor = self.registry.get(adapter_id)
        config, secret_refs = dict(config or {}), dict(secret_refs or {})
        if descriptor.substrate == "attach":
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Attach uses an approved external target, not a process profile.", {})
        if not isinstance(inherit_ambient, bool) or not isinstance(enabled, bool):
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Profile switches must be booleans.", {})
        allowed = {"command", "provider", "model", "sandbox", "approval_policy", "env", "extra_args"}
        if set(config) - allowed:
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Unsupported runtime profile configuration.", {})
        if descriptor.kind != "pi" and set(config) & {"provider", "model", "extra_args"}:
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "This adapter selects its backend through its approved environment/configuration.", {})
        command = config.get("command")
        if command is not None and (not isinstance(command, list) or not command or
                                   any(not isinstance(x, str) or not x for x in command) or
                                   not Path(command[0]).is_absolute()):
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Profile command requires an absolute executable and string arguments.", {})
        # Native launch arguments are controlled by the adapter. An executable
        # selector must not become a second channel for bypassing its policy.
        expected_args = {"codex": ["app-server"], "pi": ["--mode", "rpc"], "claude_code": []}
        if command is not None and command[1:] != expected_args.get(descriptor.kind, []):
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Profile command arguments must match the adapter launch contract.", {})
        extra_args = config.get("extra_args", [])
        if (not isinstance(extra_args, list) or len(extra_args) % 2 or
                any(not isinstance(extra_args[i], str) or extra_args[i] not in {"--provider", "--model"} or
                    not isinstance(extra_args[i + 1], str) or not extra_args[i + 1] or
                    extra_args[i + 1].startswith("-") for i in range(0, len(extra_args), 2))):
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Pi profile extra_args supports provider/model pairs only.", {})
        if config.get("sandbox", "read-only") not in {"read-only", "workspace-write"}:
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "This managed profile requires a sandbox.", {})
        if config.get("approval_policy", "on-request") not in {"on-request", "untrusted"}:
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "This managed profile requires approvals.", {})
        safe_env = {"CODEX_HOME", "CLAUDE_CONFIG_DIR", "PI_CODING_AGENT_DIR"}
        env = config.get("env", {})
        if (not isinstance(env, dict) or set(env) - safe_env or
                any(not isinstance(v, str) or not Path(v).is_absolute() for v in env.values())):
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Use secret references for backend credentials.", {})
        if any(not isinstance(key, str) or not key.isidentifier() or not isinstance(ref, str)
               or not ref.startswith("env:") or not ref[4:].isidentifier() or "NEXUS" in ref.upper()
               or "NEXUS" in key.upper() for key, ref in secret_refs.items()):
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Unsupported or privileged secret reference.", {})
        descriptor.config_validator(config)
        with self.cf.unit_of_work() as uow:
            self.repo.put_profile(uow, profile_id=profile_id, adapter_id=adapter_id, config=config,
                secret_refs=secret_refs, inherit_ambient=inherit_ambient, enabled=enabled, now=self.clock.now_iso())
        return {"profile_id": profile_id, "adapter_id": adapter_id, "enabled": bool(enabled),
                "inherit_ambient": bool(inherit_ambient), "revision": 1}

    def create_endpoint(self, context, *, endpoint_id, agent_id, adapter_id, project_root,
                        profile_id=None, enabled=False, priority=0, selection_group=None,
                        response_policy="explicit", consumption="exclusive", public_config=None):
        self.authorize(context)
        require_runtime_agent(agents=self.agents, connection_factory=self.cf, agent_id=agent_id)
        descriptor = self.registry.get(adapter_id)
        public_config = dict(public_config or {})
        allowed_public = {"target_pid"} if descriptor.substrate == "attach" else set()
        if set(public_config) - allowed_public:
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Unsupported public endpoint configuration.", {})
        if descriptor.substrate == "attach" and (
            type(public_config.get("target_pid")) is not int or public_config["target_pid"] <= 0
        ):
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Attach endpoint requires an explicitly selected process ID.", {})
        if not Path(project_root).is_absolute():
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Workspace root must be absolute.", {})
        root = resolve_realpath(project_root)
        if not Path(root).is_dir():
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Workspace root must be a directory.", {})
        workspace_id = resolve_workspace_id(root)
        if consumption == "mirror_only" and not descriptor.capabilities.context_without_execution:
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Adapter cannot mirror without starting execution.", {})
        endpoint = AgentEndpoint(endpoint_id, agent_id, adapter_id, workspace_id, descriptor.protocol,
            runtime_profile_id=profile_id, enabled=enabled, activation_state="approved" if enabled else "pending_review",
            priority=priority, selection_group=selection_group, response_policy=response_policy,
            delivery_consumption=consumption, public_config=dict(public_config or {}))
        with self.cf.unit_of_work() as uow:
            if profile_id:
                profile = self.repo.profile(uow, profile_id)
                if profile is None or profile["adapter_id"] != adapter_id or not profile["enabled"]:
                    raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Endpoint requires an enabled compatible runtime profile.", {})
            elif descriptor.substrate != "attach":
                raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Process endpoints require an approved profile.", {})
            self.workspaces.upsert(uow, workspace_id=workspace_id, root_realpath=root)
            self.repo.create(uow, endpoint=endpoint, now=self.clock.now_iso())
        return {"endpoint_id": endpoint_id, "agent_id": agent_id, "workspace_id": workspace_id, "revision": 1}

    def list(self, context, *, agent_id=None):
        self.authorize(context)
        with self.cf.unit_of_work(write=False) as uow:
            return self.repo.list(uow, agent_id=agent_id)

    def diagnostics(self, context):
        self.authorize(context)
        with self.cf.unit_of_work(write=False) as uow:
            historical = self.repo.legacy_diagnostics(uow)
        return {"legacy_sessions": historical, "live": False,
                "recovery": "Review legacy bindings and restore damaged agent profiles only from a trusted backup; historical sessions do not prove liveness."}

    def resolve(self, context, *, endpoint_id, agent_id, kind, substrate, project_root):
        self.authorize(context)
        workspace_id = resolve_workspace_id(project_root)
        with self.cf.unit_of_work(write=False) as uow:
            candidates = [self.repo.get(uow, endpoint_id)] if endpoint_id else self.repo.list(
                uow, agent_id=agent_id, workspace_id=workspace_id)
            candidates = [e for e in candidates if e and e["enabled"] and e["agent_id"] == agent_id
                          and e["workspace_id"] == workspace_id and
                          (self.registry.get(e["adapter_id"]).kind, self.registry.get(e["adapter_id"]).substrate) == (kind, substrate)]
            if len(candidates) != 1:
                raise OktoNexusError(ErrorCode.CONFLICT if candidates else ErrorCode.NOT_FOUND,
                    "AMBIGUOUS_BINDING" if candidates else "Configure an enabled endpoint and approved runtime profile first.", {})
            endpoint = candidates[0]
            profile = self.repo.profile(uow, endpoint["profile_id"]) if endpoint["profile_id"] else None
            if profile is not None and not profile["enabled"]:
                raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "Runtime profile is disabled.", {})
        return endpoint, profile

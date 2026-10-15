"""Pure validation of operator-declared native request requirements, v1."""
from dataclasses import fields
from ..domain.endpoints import EndpointCapabilities
from ..errors import ErrorCode, OktoNexusError


def native_requirement_schema(kind, substrate=None):
    """Declared request contracts, shared by current and historical profiles."""
    if kind == 'codex':
        return dict(native_approval_contract=1, requires_feature_hitl=True,
            methods=['item/commandExecution/requestApproval', 'item/fileChange/requestApproval',
                     'item/tool/requestUserInput', 'mcpServer/elicitation/request'],
            decisions=['accept', 'decline'], input_contract=1,
            input_limits='blocking non-secret questions; correlated form elicitation with flat primitive fields only; no URL or remote schema resolution')
    if kind == 'claude_code' and substrate == 'stream':
        return dict(native_approval_contract=1, requires_feature_hitl=True,
            methods=['control_request:can_use_tool'], tools=['Write', 'Edit', 'Bash', 'AskUserQuestion'],
            decisions=['accept', 'decline'], correlation='operation_and_local_generation')
    return {}


def validate_canonical_native_requirements(config, adapter_id, *, hitl_enabled=None):
    """Profile restrictions do not discover, launch, or grant native authority."""
    from types import SimpleNamespace
    from nexus_connector_core import get_runtime_catalog
    descriptor = next((item for item in get_runtime_catalog().runtimes if item.adapter_id == adapter_id), None)
    if descriptor is None or descriptor.connection_mode != 'managed':
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR, 'Unsupported runtime profile adapter.', {})
    schema = native_requirement_schema(descriptor.native_kind,
        'stream' if descriptor.native_kind == 'claude_code' else None)
    validate_native_requirements(config, SimpleNamespace(input_schema=schema), hitl_enabled=hitl_enabled)


def profile_action_allowed(config, action):
    disabled = config.get('disabled_capabilities', ())
    return not (action in {'send', 'steer'} and 'conversation' in disabled
                or action == 'steer' and 'steer_timing' in disabled
                or action == 'execute_work' and 'managed_work' in disabled)


def validate_effective_capability(report, capability):
    capabilities = report.get("effective_capabilities")
    value = capabilities.get(capability) if isinstance(capabilities, dict) else None
    supported = isinstance(value, str) and value in {"IMMEDIATE", "NEXT_TURN_BOUNDARY"} if capability == "steer_timing" else value is True
    if type(report.get("effective_capability_contract")) is not int or report["effective_capability_contract"] != 1 or not supported:
        raise OktoNexusError(ErrorCode.CONFIG_ERROR,
            "runtime_capability_unverified: the session lacks a qualified capability allowed by its profile.",
            {"reason": "runtime_capability_unverified", "capability": capability})


def validate_declared_command(capabilities, verb):
    required = {"send_turn": "conversation", "steer": "steer_timing", "interrupt": "interrupt"}.get(verb)
    if required and not getattr(capabilities, required):
        raise OktoNexusError(ErrorCode.CONFIG_ERROR,
            "adapter_capability_unsupported: the registered adapter does not support this operation.",
            {"reason": "adapter_capability_unsupported", "capability": required})


def validate_effective_control(report, verb):
    """Pure server-owned evidence check, additional to permission/turn fences."""
    if verb in {"steer", "interrupt"} and (
        report.get("control_contract_basis") not in {"tested_version_contract", "tested_protocol_contract"}
        or verb not in report.get("compatible_controls", [])
    ):
        raise OktoNexusError(ErrorCode.CONFIG_ERROR,
            "native_control_unverified: the session has no verified contract for this control.",
            {"reason": "native_control_unverified", "verb": verb})


def validate_effective_native_requirements(required, report):
    """Server-owned adapter evidence is additional to profile/descriptor checks."""
    if required and (report.get("native_request_basis") != "tested_version_contract" or
                     not set(required) <= set(report.get("compatible_native_requests", []))):
        raise OktoNexusError(ErrorCode.CONFIG_ERROR,
            "native_requirements_unverified: the runtime has no verified contract for this profile's required requests.",
            {"reason": "native_requirements_unverified"})


def validate_native_requirements(config, descriptor, *, hitl_enabled=None):
    disabled = config.get("disabled_capabilities", [])
    names = {field.name for field in fields(EndpointCapabilities)} - {"interrupt_requires_settle"}
    if (not isinstance(disabled, list) or len(disabled) > len(names) or
            any(not isinstance(name, str) or name not in names for name in disabled) or
            len(disabled) != len(set(disabled))):
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "disabled_capabilities must list unique restrictable capability names.", {})
    requested = config.get("required_native_requests", [])
    if (not isinstance(requested, list) or len(requested) > 32 or
            any(not isinstance(item, str) or not 1 <= len(item) <= 128 for item in requested) or
            len(set(requested)) != len(requested)):
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "required_native_requests must be a unique list of at most 32 request names.", {})
    schema = descriptor.input_schema
    methods, tools = schema.get("methods", []), schema.get("tools", [])
    supported = {f"{method}/{tool}" for method in methods for tool in tools} if tools else set(methods)
    if set(requested) - supported:
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Runtime profile requires an unsupported native request contract.", {})
    if requested and hitl_enabled is False and schema.get("requires_feature_hitl"):
        raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "Runtime profile requires enabled native HITL.", {})
    if requested and "approvals" in disabled:
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Required native requests conflict with disabled approvals.", {})

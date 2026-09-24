"""Pure validation of operator-declared native request requirements, v1."""
from ..errors import ErrorCode, OktoNexusError


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

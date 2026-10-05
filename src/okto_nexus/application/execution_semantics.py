"""Project HTTP targeting onto the Core wire without changing its hash rules."""

from typing import Any, Mapping

from nexus_connector_core import CoreError, r4_submit_intent_hash, validate_control_target

from ..errors import ErrorCode, OktoNexusError


def validate_execution_target(adapter_id: str, action: str,
                              target: Mapping[str, Any]) -> None:
    if (not isinstance(target, Mapping) or
            set(target) != {"kind", "expected_turn_id"} or
            type(target["kind"]) is not str or
            target["kind"] not in {"none", "native_turn_id", "current_run"} or
            (target["expected_turn_id"] is not None and
             (type(target["expected_turn_id"]) is not str or
              not 1 <= len(target["expected_turn_id"]) <= 160)) or
            (target["kind"] == "native_turn_id") !=
            (target["expected_turn_id"] is not None)):
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR,
                             "Invalid native turn target.", {})
    if action not in {"turn.steer", "turn.interrupt"}:
        if target["kind"] != "none":
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR,
                                 "This intent cannot target an existing turn.", {})
        return
    try:
        contract = validate_control_target(adapter_id, action, target["expected_turn_id"])
    except CoreError as exc:
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR,
                             "The selected adapter does not support this control target.", {}) from exc
    expected_kind = ("native_turn_id" if target["expected_turn_id"] is not None else
                     "current_run" if contract.requires_active_run else "none")
    if target["kind"] != expected_kind:
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR,
                             "An explicit active run target is required.", {})


def execution_wire_intent(semantic: Mapping[str, Any]) -> dict[str, Any]:
    """Keep the HTTP target out of NXL and bind its native ID into the hash.

    Target kinds are validated against Core before admission. A current-run
    control has no native ID; it is never converted to a made-up identifier.
    """
    wire = {key: value for key, value in semantic.items() if key != "target"}
    target_id = semantic["target"]["expected_turn_id"]
    if target_id is not None:
        wire["expected_turn_id"] = target_id
    return wire


def execution_intent_hash(semantic: Mapping[str, Any]) -> str:
    return r4_submit_intent_hash(execution_wire_intent(semantic))

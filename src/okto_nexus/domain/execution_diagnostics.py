"""Safe corrective guidance derived from scoped executor receipt codes."""

_GUIDANCE = {
    "PROVIDER_AUTH_REQUIRED": (
        "Provider authentication is unavailable.",
        "Complete provider sign-in locally using the approved provider home or restore its protected credential reference."),
    "AGENT_AUTH_REQUIRED": (
        "Required authentication material is unavailable.",
        "Check the selected identity and protected authentication references locally; restore the missing material."),
    "BINARY_NOT_FOUND": (
        "The selected provider executable is unavailable.",
        "Restore the approved installation or discover a replacement and approve its binding diff."),
    "NATIVE_VERSION_UNQUALIFIED": (
        "The selected provider build is not qualified for execution.",
        "Select a qualified build, rediscover the installation and approve the binding diff."),
    "NEEDS_REDISCOVERY": (
        "The selected installation requires new discovery evidence.",
        "Rediscover the installation and review and approve the replacement binding diff."),
    "PROFILE_DRIFT": (
        "The approved installation, workspace or launch configuration changed.",
        "Verify the installation, workspace and provider home locally; review and approve a replacement binding if the selection changed."),
}


def executor_receipt_error(receipt, *, operation_id, executor_id, binding_id):
    code = receipt["error_code"]
    message, guidance = _GUIDANCE.get(code, (
        "The executor reported an operation failure.",
        "Inspect the operation and reconcile its outcome before requesting new work."))
    target = f"On executor '{executor_id}' for binding '{binding_id}': "
    if receipt["possible_effect"]:
        action = ("Query this operation and reconcile any existing session before requesting new work. "
                  + target + guidance)
    else:
        action = target + guidance + " Query this operation before requesting new work."
    return dict(code=code, stage="executor", message=message,
        possible_effect=receipt["possible_effect"], retry_safe=receipt["retry_safe"],
        operation_id=operation_id, action=action)

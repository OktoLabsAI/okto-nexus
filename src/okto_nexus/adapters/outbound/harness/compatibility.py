"""Bounded compatibility observations; a version string is not a capability grant."""
import re
import subprocess

from .owned_process import observe_owned_process, spawn_owned_process
from ....errors import ErrorCode, OktoNexusError

# Exact installed schema inspected in P09_NATIVE_PROTOCOL_SURVEY.md, with the
# Nexus handlers exercised by protocol fixtures; actual command denial is
# evidenced in P07_EFFECTIVE_NATIVE_REQUIREMENTS.md. Input elicitation is not
# claimed as an actual model-generated request by this allowlist.
# This is a protocol-contract allowlist, never a semver range or permission.
CODEX_NATIVE_REQUEST_CONTRACTS = {
    "0.156.1": (
        "item/commandExecution/requestApproval", "item/fileChange/requestApproval",
        "item/tool/requestUserInput", "mcpServer/elicitation/request",
    ),
}

# One-shot permissions and explicit questions exercised in the isolated native
# campaigns recorded in P09. This does not assert sandbox or general capability
# verification, nor support for any other can_use_tool shape.
CLAUDE_NATIVE_REQUEST_CONTRACTS = {
    "2.1.280": tuple("control_request:can_use_tool/" + tool
                     for tool in ("Write", "Edit", "Bash", "AskUserQuestion")),
    # Only the two flows actually qualified after the local binary updated.
    "2.1.281": ("control_request:can_use_tool/Write", "control_request:can_use_tool/AskUserQuestion"),
}


def claude_version_observation(command, *, cwd, env, timeout=3.0):
    """Bounded read-only probe under the same birth ownership as the runtime.

    Wait before reading: the OS pipe bounds output, including a flooding peer.
    Read only after the owned tree has stopped, so descendants cannot hold EOF.
    This helper issues no model request and resolves no secrets; env is sealed.
    """
    proc = spawn_owned_process(command, stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, cwd=cwd, env=env)
    try:
        try:
            code = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            raise OktoNexusError(ErrorCode.CONFIG_ERROR,
                "Claude version probe exceeded its deadline.",
                {"reason": "version_probe_timeout"}) from exc
        if not observe_owned_process(proc)["stop_observed"]:
            raise OktoNexusError(ErrorCode.CONFIG_ERROR,
                "Claude version probe tree stop is unconfirmed.",
                {"reason": "version_probe_stop_unknown"})
        output = proc.stdout.read(1025) if code == 0 else b""
        match = re.fullmatch(rb"(\d{1,4}\.\d{1,4}\.\d{1,4}) \(Claude Code\)\r?\n?", output) if len(output) <= 1024 else None
        version = match.group(1).decode("ascii") if match else None
        return {"schema_version": 1, "native_version": version,
            "observation": "executable_version" if version else "version_not_observed",
            "capabilities_verified": False,
            "compatible_native_requests": list(CLAUDE_NATIVE_REQUEST_CONTRACTS.get(version, ())),
            "native_request_basis": "tested_version_contract" if version in CLAUDE_NATIVE_REQUEST_CONTRACTS else "unverified"}
    finally:
        try:
            if not observe_owned_process(proc)["stop_observed"]:
                proc.kill()
                proc.wait(timeout=3)
        finally:
            proc.stdout.close()


def codex_initialize_observation(result):
    """Retain only the native version, never codexHome or the full user-agent."""
    user_agent = result.get("userAgent") if isinstance(result, dict) else None
    match = re.match(r"^okto-nexus/(\d{1,4}\.\d{1,4}\.\d{1,4})(?: |$)", user_agent) if isinstance(user_agent, str) and len(user_agent) <= 1024 else None
    version = match.group(1) if match else None
    return {"schema_version": 1, "native_version": version,
            "observation": "initialize_version" if match else "version_not_observed",
            "capabilities_verified": False,
            "compatible_native_requests": list(CODEX_NATIVE_REQUEST_CONTRACTS.get(version, ())),
            "native_request_basis": "tested_version_contract" if version in CODEX_NATIVE_REQUEST_CONTRACTS else "unverified"}

"""Bounded compatibility observations; a version string is not a capability grant."""
import re

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

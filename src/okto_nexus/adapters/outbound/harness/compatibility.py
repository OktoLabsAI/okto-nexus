"""Bounded compatibility observations; a version string is not a capability grant."""
import re


def codex_initialize_observation(result):
    """Retain only the native version, never codexHome or the full user-agent."""
    user_agent = result.get("userAgent") if isinstance(result, dict) else None
    match = re.match(r"^okto-nexus/(\d{1,4}\.\d{1,4}\.\d{1,4})(?: |$)", user_agent) if isinstance(user_agent, str) and len(user_agent) <= 1024 else None
    return {"schema_version": 1, "native_version": match.group(1) if match else None,
            "observation": "initialize_version" if match else "version_not_observed",
            "capabilities_verified": False}

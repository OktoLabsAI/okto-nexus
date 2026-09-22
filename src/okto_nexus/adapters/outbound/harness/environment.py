"""Approved child environments. Never propagate Nexus operator credentials."""
import hashlib
import os
from pathlib import Path

from ....errors import ErrorCode, OktoNexusError

_SEALED = "_NEXUS_PROFILE_ENV_SEALED"
_OS_VARIABLES = {"SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "PATH", "TEMP", "TMP",
                 "LANG", "LC_ALL", "TERM"}


def child_environment(overrides=None):
    values = dict(overrides or {})
    sealed = values.pop(_SEALED, None) == "1"
    merged = values if sealed else {**os.environ, **values}
    return {k: v for k, v in merged.items() if "NEXUS" not in k.upper()
            and not any(prefix in str(v) for prefix in ("nxs_", "nxsept_"))}


def profile_environment(profile, home_dir):
    """Resolve secrets/files outside all database transactions."""
    inherit = bool(profile["inherit_ambient"])
    values = dict(os.environ) if inherit else {k: v for k, v in os.environ.items() if k.upper() in _OS_VARIABLES}
    private_home = Path(home_dir) / "runtime-homes" / hashlib.sha256(profile["profile_id"].encode()).hexdigest()
    if not inherit:
        private_home.mkdir(parents=True, exist_ok=True)
        values.update(HOME=str(private_home), USERPROFILE=str(private_home),
                      CODEX_HOME=str(private_home / "codex"),
                      CLAUDE_CONFIG_DIR=str(private_home / "claude"),
                      PI_CODING_AGENT_DIR=str(private_home / "pi"))
    values.update(profile["config"].get("env", {}))
    for name, reference in profile["secret_refs"].items():
        value = os.environ.get(reference[4:])
        if not value or any(prefix in value for prefix in ("nxs_", "nxsept_")):
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "Runtime credential reference is unavailable or privileged.", {})
        values[name] = value
    values = child_environment({**values, _SEALED: "1"})
    values[_SEALED] = "1"
    return values

"""Bounded observation of Codex 0.157 thread start/resume response metadata.

This is a Core projection, not a native notification or a configuration
command. Only the response's allowlisted fields are inspected. In particular,
the thread transcript and instruction contents never enter this projection.
Missing optional properties remain missing; schema defaults are not evidence.
Paths are native references, validated lexically without filesystem access.
"""
from __future__ import annotations

from pathlib import PurePosixPath, PureWindowsPath
from collections.abc import Callable

from ..protocol import canonical_json


EVENT_TYPE = "core/codex_thread_configuration"
METADATA_KEY = "codex_thread_configuration"
FIELDS = (
    "approvalPolicy", "approvalsReviewer", "cwd", "instructionSources",
    "model", "modelProvider", "sandbox", "reasoningEffort",
)
MAX_FIELD_BYTES = 16_384
MAX_OBSERVATION_BYTES = 48_000
MAX_PATH_BYTES = 4096
MAX_REFERENCES = 32


class _InvalidField(ValueError):
    pass


def _invalid(reason: str) -> dict:
    return {"status": "invalid", "reason": reason}


def _text(value, limit: int) -> str:
    if type(value) is not str or not value:
        raise _InvalidField("invalid_value")
    # Check character length before encoding any potentially oversized input.
    if len(value) > limit:
        raise _InvalidField("limit_exceeded")
    if not value.strip():
        raise _InvalidField("invalid_value")
    if any(ord(char) < 32 or 127 <= ord(char) <= 159 for char in value):
        raise _InvalidField("invalid_value")
    try:
        size = len(value.encode("utf-8"))
    except UnicodeEncodeError:
        raise _InvalidField("invalid_value") from None
    if size > limit:
        raise _InvalidField("limit_exceeded")
    return value


def _path(value, *, absolute: bool) -> str:
    value = _text(value, MAX_PATH_BYTES)
    if absolute and not (PurePosixPath(value).is_absolute()
                         or PureWindowsPath(value).is_absolute()):
        raise _InvalidField("invalid_value")
    # Do not resolve, case-fold or rewrite environment-native paths. These
    # references neither prove file existence nor authorize access to a file.
    return value


def _paths(value, *, absolute: bool) -> list[str]:
    if type(value) is not list:
        raise _InvalidField("invalid_value")
    if len(value) > MAX_REFERENCES:
        raise _InvalidField("limit_exceeded")
    return [_path(item, absolute=absolute) for item in value]


def _enum(value, allowed) -> str:
    if type(value) is not str or value not in allowed:
        raise _InvalidField("invalid_value")
    return value


def _boolean(value) -> bool:
    if type(value) is not bool:
        raise _InvalidField("invalid_value")
    return value


def _approval(value):
    if type(value) is str:
        return _enum(value, ("untrusted", "on-request", "never"))
    if type(value) is not dict or type(value.get("granular")) is not dict:
        raise _InvalidField("invalid_value")
    if len(value) != 1:
        raise _InvalidField("unknown_policy_field")
    granular = value["granular"]
    required = ("mcp_elicitations", "rules", "sandbox_approval")
    allowed = (*required, "request_permissions", "skill_approval")
    if len(granular) > len(allowed) or any(key not in allowed for key in granular):
        raise _InvalidField("unknown_policy_field")
    if any(key not in granular for key in required):
        raise _InvalidField("invalid_value")
    return {"granular": {key: _boolean(granular[key]) for key in allowed if key in granular}}


def _sandbox(value) -> dict:
    if type(value) is not dict:
        raise _InvalidField("invalid_value")
    kind = _enum(value.get("type"), (
        "dangerFullAccess", "readOnly", "externalSandbox", "workspaceWrite"))
    allowed = {"type"}
    if kind != "dangerFullAccess":
        allowed.add("networkAccess")
    if kind == "workspaceWrite":
        allowed.update(("excludeSlashTmp", "excludeTmpdirEnvVar", "writableRoots"))
    if len(value) > len(allowed) or any(key not in allowed for key in value):
        raise _InvalidField("unknown_policy_field")
    result = {"type": kind}
    if kind == "externalSandbox" and "networkAccess" in value:
        result["networkAccess"] = _enum(value["networkAccess"], ("restricted", "enabled"))
    if kind in {"readOnly", "workspaceWrite"} and "networkAccess" in value:
        result["networkAccess"] = _boolean(value["networkAccess"])
    if kind == "workspaceWrite":
        for key in ("excludeSlashTmp", "excludeTmpdirEnvVar"):
            if key in value:
                result[key] = _boolean(value[key])
        if "writableRoots" in value:
            result["writableRoots"] = _paths(value["writableRoots"], absolute=True)
    return result


def _value(field: str, value):
    if field == "approvalPolicy":
        return _approval(value)
    if field == "approvalsReviewer":
        return _enum(value, ("user", "auto_review", "guardian_subagent"))
    if field == "cwd":
        return _path(value, absolute=True)
    if field == "instructionSources":
        # LegacyAppPathString, unlike AbsolutePathBuf, can be relative.
        return _paths(value, absolute=False)
    if field == "sandbox":
        return _sandbox(value)
    if field == "reasoningEffort":
        return None if value is None else _text(value, 64)
    return _text(value, 256)  # model / modelProvider


def bound_observation(observation: dict) -> dict:
    """Bound our closed projection again after redaction can expand strings."""
    fields = observation["fields"]
    for key in FIELDS:
        field = fields[key]
        if field["status"] == "reported" and len(canonical_json(field)) > MAX_FIELD_BYTES:
            fields[key] = _invalid("limit_exceeded")
    if len(canonical_json(observation)) > MAX_OBSERVATION_BYTES:
        # Never truncate references or turn a partial observation into empty
        # effective policy. This is a defensive final bound on the full event.
        observation["fields"] = {key: _invalid("limit_exceeded") for key in FIELDS}
    return observation


def redact_observation(observation: dict, clean: Callable) -> dict:
    """Keep closed keys/statuses intact; never present a masked policy as fact."""
    fields = {}
    for key in FIELDS:
        field = observation["fields"][key]
        if field["status"] != "reported":
            fields[key] = dict(field)
            continue
        value = clean(field["value"])
        fields[key] = (_invalid("redacted") if value != field["value"] else
                       {"status": "reported", "value": value})
    return bound_observation({**observation, "thread_id": clean(observation["thread_id"]),
                              "fields": fields})


def observe_thread_response(response: dict, *, method: str, thread_id: str) -> dict:
    """Detach allowlisted, bounded metadata from one validated thread reply."""
    if method not in {"thread/start", "thread/resume"}:
        raise ValueError("unsupported thread observation source")
    fields = {}
    for key in FIELDS:
        if key not in response:
            fields[key] = {"status": "missing"}
            continue
        try:
            fields[key] = {"status": "reported", "value": _value(key, response[key])}
        except _InvalidField as error:
            fields[key] = _invalid(str(error))
    return bound_observation({
        "schema_version": 1,
        "adapter_id": "codex_app_server",
        "source": method + "/response",
        "thread_id": thread_id,
        "fields": fields,
    })

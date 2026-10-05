"""Forward stdio controls to the existing serve owner; never spawn a manager."""
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from ...errors import ErrorCode, OktoNexusError


def call_runtime_owner(home_dir, path, body):
    key = os.environ.get("OKTO_NEXUS_API_KEY")
    if not key:
        raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "Runtime controls require the configured authenticated serve owner.", {})
    try:
        descriptor = Path(home_dir) / "runtime-wake.json"
        if descriptor.stat().st_size > 2048:
            raise ValueError("invalid owner descriptor")
        record = json.loads(descriptor.read_text(encoding="utf-8"))
        address = record.get("api_url", "")
        parsed = urlsplit(address)
        if (parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "::1"} or
                not parsed.port or parsed.path or parsed.query or parsed.fragment or parsed.username):
            raise ValueError("invalid owner address")
    except (OSError, ValueError, TypeError):
        raise OktoNexusError(ErrorCode.CONFIG_ERROR, "Start an enabled serve owner for this Nexus home before controlling runtimes.", {}) from None
    try:
        with httpx.Client(trust_env=False, timeout=45, follow_redirects=False) as client:
            response = client.post(address + path, headers={"x-api-key": key}, json=body)
        result = response.json()
    except (httpx.HTTPError, ValueError):
        raise OktoNexusError(ErrorCode.CONFLICT, "Owner response is unknown; do not automatically repeat the operation.",
                            {"outcome": "OUTCOME_UNKNOWN", "idempotency_key": body.get("idempotency_key")}) from None
    if not result.get("ok"):
        error = result.get("error", {})
        raise OktoNexusError(error.get("code", ErrorCode.INTERNAL_ERROR), error.get("message", "Runtime owner rejected the operation."), error.get("details", {}))
    return result["data"]

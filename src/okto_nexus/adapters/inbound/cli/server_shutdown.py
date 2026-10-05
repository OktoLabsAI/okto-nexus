"""Control the running Server without creating a second runtime owner."""
import json
import math
import sys
from urllib.parse import urlsplit

import httpx


def run_shutdown(options, environ, sink):
    key = environ.get("OKTO_NEXUS_API_KEY", "")
    budget = getattr(options, "timeout_seconds", 0.0)
    try:
        address = urlsplit(options.url)
        valid_url = (address.scheme in {"http", "https"} and address.hostname
                     and not address.username and not address.password
                     and address.path in {"", "/"} and not address.query
                     and not address.fragment)
        # Validate malformed ports before HTTPX sees the URL.
        address.port
        if not valid_url or not math.isfinite(budget) or not 0 <= budget <= 300:
            raise ValueError
    except ValueError:
        print("[okto-nexus admin] CONFIG_ERROR: Supply a Server base URL and a timeout between 0 and 300 seconds.", file=sys.stderr)
        return 1
    if not key:
        print("[okto-nexus admin] PERMISSION_DENIED: Set OKTO_NEXUS_API_KEY to an operator credential.", file=sys.stderr)
        return 1
    try:
        with httpx.Client(trust_env=False, follow_redirects=False, timeout=budget + 5) as client:
            url = options.url.rstrip("/") + "/v1/runtime/shutdown"
            headers = {"Authorization": "Bearer " + key}
            response = (client.post(url, headers=headers, json={"timeout_seconds": budget})
                        if options.command == "shutdown" else client.get(url, headers=headers))
        if response.status_code not in {200, 202}:
            print(f"[okto-nexus admin] REQUEST_REJECTED: Server returned HTTP {response.status_code}.", file=sys.stderr)
            return 1
        report = response.json()
        if not isinstance(report, dict) or report.get("state") not in {
                "RUNNING", "DRAINING_PENDING", "DRAINED"}:
            raise ValueError
    except (httpx.HTTPError, ValueError):
        print("[okto-nexus admin] OUTCOME_UNKNOWN: Server response is unavailable. Inspect shutdown-status before taking further action.", file=sys.stderr)
        return 1
    sink.write(json.dumps(report, ensure_ascii=True) + "\n")
    sink.flush()
    # Pending is an accepted request. The Server retains its recovery task;
    # only this administrative client exits.
    return 0

"""Explicitly authorized passive discovery: binary/layout bytes only, never probes."""

from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
import argparse
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from safety import publish, sha


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    from nexus_connector_core.discovery import discover_installations
    from nexus_connector_core.installation import effective_installation_ref

    inventory = discover_installations(
        adapter_ids=("codex_app_server", "claude_stream")
    )
    values = []
    for item in inventory.candidates:
        value = asdict(item)
        value["candidate_ref"] = effective_installation_ref(item)
        value["executable_sha256"] = sha(item.executable)
        values.append(value)
    report = {
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "candidates": values,
        "native_invoked": False,
        "auth_or_provider_home_opened": False,
        "method": "Core0.0.14 discover_installations restricted to Codex/Claude; PATH/layout/executable byte reads only",
    }
    publish(args.output, report)
    print(
        json.dumps(
            {
                "count": len(values),
                "output": str(args.output),
                "native_invoked": False,
                "auth_opened": False,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

"""Bind passive, fresh executable observations; declare homes without opening them."""

from pathlib import Path
import argparse
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from safety import publish, read, require


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--discovery", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    observed = read(args.discovery)
    require(
        observed["native_invoked"] is False
        and observed["auth_or_provider_home_opened"] is False,
        "PASSIVE_FRESH_OBSERVATION_REQUIRED",
    )
    values = {}
    for name, adapter, model in (
        ("codex", "codex_app_server", "gpt-5.3-codex"),
        ("claude", "claude_stream", "claude-sonnet-4-6"),
    ):
        matches = [
            item for item in observed["candidates"] if item["adapter_id"] == adapter
        ]
        require(len(matches) == 1, "EXACT_INSTALLATION_SELECTION_REQUIRED")
        selected = matches[0]
        require(
            selected["launch_script"] is None,
            "THIS_DRIVER_REQUIRES_DIRECT_NATIVE_EXECUTABLE",
        )
        values[name] = {
            key: selected[key]
            for key in (
                "adapter_id",
                "candidate_ref",
                "executable",
                "executable_sha256",
                "fingerprint",
                "build_identity",
            )
        }
        values[name].update(
            account="currently_authenticated_cli",
            model_id=model,
            model_family="Sonnet" if name == "claude" else "Codex",
            installation_root=str(Path(selected["executable"]).parent),
            provider_home=str(Path.home()),
            provider_home_declaration="Current user home path literal only; no auth/config/home content opened; authentication remains unverified.",
            version_verified=False,
            model_access_verified=False,
        )
    publish(args.output, values)


if __name__ == "__main__":
    main()

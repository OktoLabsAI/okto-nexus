"""Offline preparation only: no product handlers, native launch or auth reads."""

from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
import argparse
import json
import sys
import tempfile
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parent))
from safety import ORDER, POLICY, publish, read, require, sha

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]


def identity():
    path = HERE / "identity.json"
    if not path.exists():
        campaign = uuid.uuid4().hex
        publish(
            path,
            {
                "campaign_id": campaign,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "temporary_parent": str(Path(tempfile.gettempdir()).resolve()),
                "campaign_root": str(
                    Path(tempfile.gettempdir()).resolve() / ("nexus-ui042-" + campaign)
                ),
                "port": 50000 + int(campaign[:8], 16) % 10000,
                "agent_ids": {
                    name: "ui042-" + name + "-" + campaign[:16]
                    for name in ("codex", "claude")
                },
                "intent_ids": {
                    kind: "ui042_" + campaign + "_" + kind.replace(".", "_")
                    for kind in ORDER
                },
            },
        )
    return read(path)


def package_snapshot(report_path):
    report = read(report_path)
    executable = Path(report["installed_environment"]["executable"]).resolve()
    require(
        executable == Path(sys.executable).resolve(),
        "QUALIFIED_INSTALLED_PYTHON_REQUIRED",
    )
    root = executable.parents[2]
    artifacts = report["candidate"]["artifacts"]
    requested = [
        ("okto_nexus", report["candidate"]["wheel_sha256"]),
        (
            "okto_nexus_connector",
            "4095484f14110b845b3481941330810f3de1d8fadf9051de0b724cb824177b90",
        ),
    ]
    wheels = []
    for module, expected in requested:
        paths = [
            root / key
            for key, value in artifacts.items()
            if key.endswith(".whl") and value == expected
        ]
        require(
            len(paths) == 1 and sha(paths[0]) == expected, "QUALIFIED_WHEEL_REQUIRED"
        )
        wheels.append({"path": str(paths[0]), "sha256": expected, "module": module})
    core = REPO / "vendor/wheels/okto_nexus_connector_core-0.0.14-py3-none-any.whl"
    require(
        sha(core) == "ea1797805279667a5b39fdb6e9e6185ed8dcb958a1c7f98e91651e841754dca5",
        "CORE_PIN_CHANGED",
    )
    wheels.append(
        {"path": str(core), "sha256": sha(core), "module": "nexus_connector_core"}
    )
    payloads = []
    for package, version in (
        ("okto-nexus", "0.3.5"),
        ("okto-nexus-connector", "0.0.13"),
        ("okto-nexus-connector-core", "0.0.14"),
    ):
        distribution = metadata.distribution(package)
        require(distribution.version == version, "PACKAGE_VERSION_CHANGED")
        for entry in distribution.files or []:
            if entry.suffix == ".pyc" or entry.hash is None:
                continue
            target = Path(distribution.locate_file(entry)).resolve()
            require(
                target.is_relative_to(Path(sys.prefix).resolve()),
                "PACKAGE_OUTSIDE_OWN_PREFIX",
            )
            payloads.append({"path": str(target), "sha256": sha(target)})
    images = {
        str(Path(path).resolve()): sha(path)
        for path in {sys.executable, sys._base_executable}
    }
    return {
        "package_bound": True,
        "python": {"path": str(executable), "sha256": sha(executable)},
        "python_images": images,
        "package_pins": [
            {"path": str(report_path.resolve()), "sha256": sha(report_path)},
            *[{key: item[key] for key in ("path", "sha256")} for item in wheels],
        ],
        "wheels": wheels,
        "installed_payloads": payloads,
    }


def prepare(package_report=None, native_bindings=None):
    plan = identity() | {
        "schema": "ui042-campaign-v1",
        "policy": POLICY,
        "admission_order": list(ORDER),
        "home_observer_window": {
            "seconds": 180,
            "marker": "public/observer.done",
            "requires_campaign_id": True,
            "absence": "NOT_RUN",
            "productive_calls": 0,
        },
        "package_bound": False,
        "native_bindings_bound": False,
        "native": {
            name: {
                "account": "currently_authenticated_cli",
                "adapter_id": adapter,
                "model_family": "Sonnet"
                if name == "claude"
                else "operator-selected Codex model",
                "candidate_ref": None,
                "executable": None,
                "executable_sha256": None,
                "installation_root": None,
                "provider_home": None,
                "model_id": None,
            }
            for name, adapter in (
                ("codex", "codex_app_server"),
                ("claude", "claude_stream"),
            )
        },
        "prompts": {
            "work": "Analyze this expense CSV without tools, network, subagents, or any additional request.\n\n"
            "date,category,amount\n2026-11-01,hosting,12.50\n2026-11-02,software,8.25\n"
            "2026-11-03,hosting,2.25\n2026-11-04,refund,-3.00\n\nReturn only JSON containing exactly "
            "row_count (integer), total (decimal string with two fractional digits), and totals_by_category "
            "(category to decimal string with two fractional digits). This is the entire task.",
            "continue": "Continue in this same session. Independently verify your preceding expense total and "
            "calculate a hypothetical 10 percent surcharge. Return only JSON with verified_total, surcharge "
            "and total_with_surcharge as exact decimal strings. Do not use tools, network or subagents.",
        },
    }
    if package_report is not None:
        plan.update(package_snapshot(package_report))
    if native_bindings is not None:
        binding = read(native_bindings)
        require(set(binding) == {"codex", "claude"}, "TWO_NATIVE_BINDINGS_REQUIRED")
        for name in ("codex", "claude"):
            require(
                binding[name]["adapter_id"] == plan["native"][name]["adapter_id"]
                and binding[name]["account"] == "currently_authenticated_cli",
                "NATIVE_ACCOUNT_SCOPE_CHANGED",
            )
            require(
                all(
                    isinstance(binding[name].get(key), str) and binding[name][key]
                    for key in (
                        "candidate_ref",
                        "executable",
                        "executable_sha256",
                        "installation_root",
                        "provider_home",
                        "model_id",
                    )
                ),
                "EXPLICIT_NATIVE_SELECTION_REQUIRED",
            )
            # Literal metadata binding only. Do not stat/open binaries, homes,
            # config, credential files or keychains while preparing a proposal.
        require(binding["claude"]["model_family"] == "Sonnet", "SONNET_REQUIRED")
        plan["native"], plan["native_bindings_bound"] = binding, True
    plan["driver_pins"] = [
        {"path": str(HERE / name), "sha256": sha(HERE / name)}
        for name in (
            "driver.py",
            "safety.py",
            "usage.py",
            "own_process.py",
            "README.md",
            "qualification.json",
            "passive-discovery.json",
            "native-bindings.json",
        )
    ]
    return plan


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package-report", type=Path)
    parser.add_argument("--native-bindings", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    plan = prepare(args.package_report, args.native_bindings)
    publish(args.output, plan)
    print(
        json.dumps(
            {
                "candidate": str(args.output),
                "sha256": sha(args.output),
                "package_bound": plan["package_bound"],
                "native_bindings_bound": plan["native_bindings_bound"],
                "effects_started": False,
                "native_or_provider_called": False,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

"""Verify automatic runtime lease renewal against installed artifacts."""
import argparse
import hashlib
import importlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "plans/r4_execution/evidence/lease-renewal-artifacts.json"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("suite", choices=["core", "connector", "nexus"])
    parser.add_argument("--bootstrap-pin", action="store_true")
    args = parser.parse_args()
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    roots = {"nexus": ROOT, "connector": ROOT.parent / "okto-nexus-connector",
             "core": ROOT.parent / "okto-nexus-connector-core"}
    modules = {"nexus": "okto_nexus", "connector": "okto_nexus_connector",
               "core": "nexus_connector_core"}
    verified = {}
    for name, module in modules.items():
        package = importlib.import_module(module)
        location = Path(package.__file__).resolve().parent
        assert "site-packages" in str(location), location
        wheel = Path(data[name]["wheel"])
        assert hashlib.sha256(wheel.read_bytes()).hexdigest() == data[name]["sha256"]
        count = 0
        with zipfile.ZipFile(wheel) as archive:
            for member in archive.namelist():
                if not member.startswith(module + "/") or member.endswith("/"):
                    continue
                relative = member[len(module) + 1:]
                expected = archive.read(member)
                assert (location / relative).read_bytes() == expected, member
                assert (roots[name] / "src" / member).read_bytes() == expected, member
                count += 1
        verified[name] = {"path": str(location), "files": count}
    assert importlib.import_module("nexus_connector_core").__version__ == "0.2.38.dev0"
    tests = {
        "core": ['test_r4_terminal_close.py', 'test_r4_runtime_leases.py', 'test_close_policy.py', 'test_kernel.py', 'test_kernel_crash.py', 'test_journal_conformance.py', 'test_receipt_reducer.py', 'test_r4_receipt_reducer.py', 'test_r4_receipt_bridge.py', 'test_r4_receipt_binding.py', 'test_r4_decision_bridge.py'],
        "connector": ["test_r4_native_actions.py", "unit", "contract"],
        "nexus": ["execution_r4/test_daemon_startup.py", "execution_r4/test_approved_mcp_host.py", "execution_r4/test_pi_native_hosts.py", "execution_r4/test_capability_recovery.py", "execution_r4/test_capability_reservation.py", "execution_r4/test_session_capabilities.py", "execution_r4/test_ns07.py",
                  "execution_r4/test_ns09.py", "execution_r4/test_ns01.py",
                  "execution_r4/test_core_native_actions.py", "execution_r4/test_remote_connection.py", "execution_r4/test_reconciliation.py"],
    }
    tests["nexus"] = ["execution_r4/" + name + ".py" for name in ("test_event_ingress", "test_public_open_bootstrap", "test_remote_connection", "test_reconciliation", "test_ns09")]
    tests["core"] += ["test_r4_pending_containment.py", "test_owned_slot_state.py", "test_r4_resource_release.py", "test_owned_slot_reservations.py", "test_installation_slot_ledger.py"]
    tests["nexus"] += ["execution_r4/test_ns01.py", "execution_r4/test_session_capabilities.py", "execution_r4/test_capability_recovery.py"]
    suite = args.suite
    suffix = "-bootstrap-pin" if args.bootstrap_pin else ""
    if args.bootstrap_pin:
        assert suite == "nexus"
        tests[suite] = ["execution_r4/test_ns01.py::test_ns01_03"]
    test_root = roots[suite] / "tests"
    out = ROOT / "plans/r4_execution/evidence"
    config = Path.cwd() / "pytest.ini"
    assert config.read_text().strip() == "[pytest]"
    launcher = [sys.executable, "-I", "-m", "pytest"]
    if suite == "core":
        # A legacy Core test imports tests.regression by package name.
        # Add the repository root only; never add src or editable packages.
        probe = ("import sys; sys.path.insert(0, " + repr(str(roots[suite])) + "); "
                 "import nexus_connector_core, pytest; "
                 "assert 'site-packages' in nexus_connector_core.__file__; "
                 "raise SystemExit(pytest.main(sys.argv[1:]))")
        launcher = [sys.executable, "-I", "-c", probe]
    command = [*launcher, "-c", str(config),
               "--rootdir=" + str(test_root), "--confcutdir=" + str(test_root),
               "-o", "asyncio_mode=auto", "-o", "asyncio_default_fixture_loop_scope=function",
               *[str(test_root / t) for t in tests[suite]],
               "-q", "--junitxml=" + str(out / ("lease-renewal-installed-" + suite + suffix + ".xml"))]
    with (out / ("lease-renewal-installed-" + suite + suffix + ".log")).open("w", encoding="utf-8") as log:
        result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
    (out / ("lease-renewal-installed-" + suite + suffix + ".json")).write_text(json.dumps({
        "command": command, "cwd": str(Path.cwd()), "verified_packages": verified,
        "exit_code": result.returncode, "python": sys.version,
        "limitations": "Automatic renewal uses Server grants, current local authority and Core deadlines; compatible renewal retains applied Server authority until ACK. Actual process-kill recovery, live-session adoption, embedded publishing, projections and provider/platform/independent-host final acceptance remain pending. Technical native peer and fixture readiness."
    }, indent=2) + "\n", encoding="utf-8")
    print((out / ("lease-renewal-installed-" + suite + suffix + ".log")).read_text(encoding="utf-8")[-7000:])
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()

"""Repeat native domain integration against installed, byte-verified artifacts."""
import argparse
import hashlib
import importlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "plans/r4_execution/evidence/native-domain-artifacts.json"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("suite", choices=["core", "connector", "nexus"])
    parser.add_argument("--final", action="store_true")
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
    assert importlib.import_module("nexus_connector_core").__version__ == "0.2.29.dev0"
    tests = {
        "core": ["test_r4_native_actions.py", "test_native_action_bridge.py",
                 "test_r4_runtime_leases.py", "test_r4_pending_containment.py", "test_runtime.py"],
        "connector": ["test_r4_native_actions.py", "unit/test_r4_session_capability.py",
                      "unit/test_r4_execution.py", "unit/test_r4_daemon_control.py",
                      "contract/test_r4_connection.py", "contract/test_wss_r4.py"],
        "nexus": ["execution_r4"],
    }
    suite = args.suite
    if args.final:
        if suite == "connector":
            tests[suite] = ["test_r4_native_actions.py", "unit", "contract"]
        elif suite == "nexus":
            tests[suite] = ["execution_r4/test_core_native_actions.py",
                           "execution_r4/test_daemon_startup.py",
                           "execution_r4/test_remote_connection.py",
                           "execution_r4/test_executor_registration_cli.py"]
    suffix = "-final" if args.final else ""
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
               "-q", "--junitxml=" + str(out / ("native-domain-installed-" + suite + suffix + ".xml"))]
    with (out / ("native-domain-installed-" + suite + suffix + ".log")).open("w", encoding="utf-8") as log:
        result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
    (out / ("native-domain-installed-" + suite + suffix + ".json")).write_text(json.dumps({
        "command": command, "cwd": str(Path.cwd()), "verified_packages": verified,
        "exit_code": result.returncode, "python": sys.version,
        "limitations": "Technical harness peer; no real provider qualification or automatic host lifecycle."
    }, indent=2) + "\n", encoding="utf-8")
    print((out / ("native-domain-installed-" + suite + suffix + ".log")).read_text(encoding="utf-8")[-7000:])
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()

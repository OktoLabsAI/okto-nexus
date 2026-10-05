"""Verify installed Connector session observation and actual HTTP/WSS CLI integration."""
import hashlib
import importlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "plans/r4_execution/evidence"
artifacts = json.loads((OUT / "session-cli-artifacts.json").read_text())
verified = {}
for name, module, source in (
    ("nexus", "okto_nexus", ROOT),
    ("connector", "okto_nexus_connector", ROOT.parent / "okto-nexus-connector"),
    ("core", "nexus_connector_core", ROOT.parent / "okto-nexus-connector-core"),
):
    location = Path(importlib.import_module(module).__file__).resolve().parent
    assert "site-packages" in str(location)
    artifact = artifacts[name]
    wheel = Path(artifact["wheel"])
    assert hashlib.sha256(wheel.read_bytes()).hexdigest() == artifact["sha256"]
    with zipfile.ZipFile(wheel) as archive:
        for member in archive.namelist():
            if member.startswith(module + "/") and not member.endswith("/"):
                assert (location / member.split("/", 1)[1]).read_bytes() == archive.read(member)
                assert (source / "src" / member).read_bytes() == archive.read(member)
    verified[name] = dict(path=str(location), artifact=artifact)
connector = ROOT.parent / "okto-nexus-connector"
assert (Path.cwd() / "pytest.ini").read_text().strip() == "[pytest]"
suites = {
    "connector": (connector / "tests", [
        connector / "tests/unit/test_runtime_session_reads.py",
        connector / "tests/unit/test_runtime_admission.py",
        connector / "tests/contract/test_https_client.py"]),
    "nexus": (ROOT / "tests/execution_r4", [
        str(ROOT / "tests/execution_r4/test_remote_connection.py") +
        "::test_public_runtime_cli_dispatches_five_actions_through_automatic_daemon"]),
}
for name, (root, tests) in suites.items():
    arguments = ["-c", str(Path.cwd() / "pytest.ini"), "--rootdir=" + str(root),
        "--confcutdir=" + str(root), "-o", "asyncio_mode=auto",
        "-o", "asyncio_default_fixture_loop_scope=function",
        *map(str, tests), "-q", "--tb=short",
        "--junitxml=" + str(OUT / ("session-cli-" + name + "-installed.xml"))]
    code = "import sys,pytest; sys.path.insert(0," + repr(str(connector)) + "); raise SystemExit(pytest.main(" + repr(arguments) + "))"
    command = [sys.executable, "-I", "-c", code]
    with (OUT / ("session-cli-" + name + "-installed.log")).open("w", encoding="utf-8") as log:
        result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
    (OUT / ("session-cli-" + name + "-installed.json")).write_text(json.dumps(dict(
        command=command, cwd=str(Path.cwd()), verified_packages=verified, exit_code=result.returncode,
        test_hashes={str(path): hashlib.sha256(Path(str(path).split("::")[0]).read_bytes()).hexdigest()
            for path in tests}), indent=2) + "\n", encoding="utf-8")
    print((OUT / ("session-cli-" + name + "-installed.log")).read_text(encoding="utf-8")[-5000:])
    if result.returncode:
        raise SystemExit(result.returncode)

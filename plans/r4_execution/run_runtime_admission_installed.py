"""Installed launch consent, realization, daemon and public HTTP verification."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

import okto_nexus_connector
import nexus_connector_core

ROOT = Path(__file__).resolve().parents[2]
CONNECTOR = ROOT.parent / "okto-nexus-connector"
OUT = ROOT / "plans/r4_execution/evidence"
artifact = json.loads((OUT / "runtime-admission-artifact.json").read_text())
wheel = Path(artifact["wheel"])
assert hashlib.sha256(wheel.read_bytes()).hexdigest() == artifact["sha256"]
location = Path(okto_nexus_connector.__file__).resolve().parent
assert "site-packages" in str(location)
count = 0
with zipfile.ZipFile(wheel) as archive:
    for member in archive.namelist():
        if member.startswith("okto_nexus_connector/") and not member.endswith("/"):
            relative = member.split("/", 1)[1]
            assert (location / relative).read_bytes() == archive.read(member)
            assert (CONNECTOR / "src" / member).read_bytes() == archive.read(member)
            count += 1
assert nexus_connector_core.__version__ == "0.2.43.dev0"
assert "site-packages" in str(Path(nexus_connector_core.__file__).resolve())
core_artifact = json.loads((OUT / "native-lease-core-artifact.json").read_text())
core_wheel = Path(core_artifact["wheel"])
assert hashlib.sha256(core_wheel.read_bytes()).hexdigest() == core_artifact["sha256"]
core_location = Path(nexus_connector_core.__file__).resolve().parent
with zipfile.ZipFile(core_wheel) as archive:
    for member in archive.namelist():
        if member.startswith("nexus_connector_core/") and not member.endswith("/"):
            relative = member.split("/", 1)[1]
            assert (core_location / relative).read_bytes() == archive.read(member)
            assert (ROOT.parent / "okto-nexus-connector-core/src" / member).read_bytes() == archive.read(member)
tests = ["test_runtime_admission.py", "test_binding_onboarding.py", "test_discovery_configuration.py", "test_r4_daemon_control.py",
         "test_state_store.py", "test_executor_registration.py",
         "test_launch_configuration.py", "test_execution_selection.py",
         "test_session_capability_owner.py", "test_r4_daemon_execution.py",
         "test_r4_execution.py", "test_r4_lease_renewal.py",
         "test_r4_publications.py", "test_approved_native_launch.py",
         "test_approved_mcp_launch.py", "test_executor_onboarding.py",
         "test_executor_inventory_r4.py", "test_realization_service_r4.py"]
arguments = ["-c", str(Path.cwd() / "pytest.ini"), "--rootdir=" + str(CONNECTOR / "tests"),
    "--confcutdir=" + str(CONNECTOR / "tests"), "-o", "asyncio_mode=auto",
    "-o", "asyncio_default_fixture_loop_scope=function",
    *[str(CONNECTOR / "tests/unit" / name) for name in tests], "-q", "--maxfail=3", "--tb=short",
    "--junitxml=" + str(OUT / "runtime-admission-installed.xml")]
code = "import sys,pytest; sys.path.insert(0," + repr(str(CONNECTOR)) + "); raise SystemExit(pytest.main(" + repr(arguments) + "))"
command = [sys.executable, "-I", "-c", code]
with (OUT / "runtime-admission-installed.log").open("w", encoding="utf-8") as log:
    result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
record = dict(command=command, cwd=str(Path.cwd()), package_path=str(location),
    verified_files=count, exit_code=result.returncode, core_version=nexus_connector_core.__version__)
(OUT / "runtime-admission-installed.json").write_text(json.dumps(record, indent=2) + "\n")
print((OUT / "runtime-admission-installed.log").read_text()[-6000:])
if result.returncode:
    raise SystemExit(result.returncode)

from okto_nexus_connector.platform import paths
from okto_nexus_connector.storage.state_store import ConnectorState, ExecutionExecutorRecord, StateStore, IdentityRecord, ServerProfileRecord
state_root = Path(tempfile.mkdtemp(prefix="okto-r4-discovery-cli-"))
store = StateStore(paths.state_file(state_root))
state = ConnectorState(connector_id="connector")
state.execution_executors.append(ExecutionExecutorRecord("server", "connector", "agent", "registration",
    "Host", executor_id="executor", state="REGISTERED"))
state.servers["server"] = ServerProfileRecord("server", "https://nexus.test", "https://nexus.test", "now")
state.identities.append(IdentityRecord("subject", "server", "agent", "vault:identity", 1, "now"))
store.save(state)
base = [sys.executable, "-I", "-m", "okto_nexus_connector.cli.main", "--json",
        "--non-interactive", "--state-dir", str(state_root)]
records = []
def cli(args, expected=0):
    run = subprocess.run(base + args, capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert run.returncode == expected, (run.returncode, run.stdout, run.stderr)
    payload = json.loads(run.stdout)
    records.append(dict(command=base + args, exit_code=run.returncode, response=payload))
    return payload
cli(["executor", "configure-discovery", "--server-id", "server", "--harness-root", str(state_root)])
assert cli(["executor", "show", "server"])["discovery_configuration"]["roots"][0]["path"] == str(state_root)
preview = cli(["discover", "--server-id", "server"])
assert preview["candidates"] == []
before = store.path.read_bytes()
invalid = subprocess.run(base + ["executor", "configure-discovery", "--server-id", "server",
    "--harness-root", "relative"], capture_output=True, text=True, encoding="utf-8", timeout=60)
assert invalid.returncode != 0 and json.loads(invalid.stdout)["error"]["code"] == "VALIDATION_ERROR"
assert store.path.read_bytes() == before
records.append(dict(command="configure-discovery with relative path", exit_code=invalid.returncode,
                    response=json.loads(invalid.stdout)))
cli(["executor", "configure-discovery", "--server-id", "server"])
assert store.load().execution_executors[0].discovery_configuration["roots"] == []
assert not store.load().execution_bindings
launch_args = ["executor", "configure-launch", "--identity", "subject",
    "--harness", "codex_app_server", "--local-consent-id", "explicit-consent", "--profile-revision", "1"]
launch = cli(launch_args)
assert cli(launch_args) == launch
assert launch["configuration_digest"].startswith("sha256:")
assert len(store.load().launch_configurations) == 1
bad_secret = subprocess.run(base + launch_args + ["--secret-ref", "API_KEY=plaintext"],
    capture_output=True, text=True, encoding="utf-8", timeout=60)
assert bad_secret.returncode != 0 and json.loads(bad_secret.stdout)["error"]["code"] == "VALIDATION_ERROR"
records.append(dict(command="configure-launch with a plaintext value",
    exit_code=bad_secret.returncode, response=json.loads(bad_secret.stdout)))
assert len(store.load().launch_configurations) == 1 and not store.load().realizations
(OUT / "runtime-admission-cli.json").write_text(json.dumps(dict(
    commands=records, network_registration_fixture=True, runtime_started=False,
    scope="Installed CLI discovery and launch-consent staging; network realization is verified separately."), indent=2) + "\n")
print("Installed CLI persistence, preview, refusal and clear passed.")


import okto_nexus
nexus_location = Path(okto_nexus.__file__).resolve().parent
assert "site-packages" in str(nexus_location)
nexus_artifact = json.loads((OUT / "runtime-admission-artifacts.json").read_text())["nexus"]
nexus_wheel = Path(nexus_artifact["wheel"])
assert hashlib.sha256(nexus_wheel.read_bytes()).hexdigest() == nexus_artifact["sha256"]
with zipfile.ZipFile(nexus_wheel) as archive:
    for member in archive.namelist():
        if member.startswith("okto_nexus/") and not member.endswith("/"):
            relative = member.split("/", 1)[1]
            assert (nexus_location / relative).read_bytes() == archive.read(member)
            assert (ROOT / "src" / member).read_bytes() == archive.read(member)
tests_root = ROOT / "tests/execution_r4"
tcp_command = [sys.executable, "-I", "-m", "pytest", "-c", str(Path.cwd() / "pytest.ini"),
    "--rootdir=" + str(tests_root), "--confcutdir=" + str(tests_root),
    str(tests_root / "test_executor_onboarding_cli.py"),
    str(tests_root / "test_binding_operator.py"), str(tests_root / "test_local_realization.py"), "-q", "--tb=short",
    "--junitxml=" + str(OUT / "runtime-admission-tcp-installed.xml")]
with (OUT / "runtime-admission-tcp-installed.log").open("w", encoding="utf-8") as log:
    result = subprocess.run(tcp_command, stdout=log, stderr=subprocess.STDOUT)
(OUT / "runtime-admission-tcp-installed.json").write_text(json.dumps(dict(
    command=tcp_command, exit_code=result.returncode, nexus_path=str(nexus_location),
    scope="Actual authenticated local IPC, loopback HTTP and automatic daemon inventory; seeded identity/vault, harmless copied executable, no provider launch. Includes binding/local-realization regressions."), indent=2) + "\n")
print((OUT / "runtime-admission-tcp-installed.log").read_text()[-5000:])
raise SystemExit(result.returncode)

"""Verify process-only MCP launch with installed wheels and no Connector."""
import argparse
import hashlib
import importlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import zipfile

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "plans/r4_execution/evidence"
parser = argparse.ArgumentParser()
parser.add_argument("suite", choices=["codex_app_server", "claude_stream", "pi_rpc"])
parser.add_argument("--observe-native-requests", action="store_true")
args = parser.parse_args()
prefix = "real-native-elicitation" + ("-diagnostic" if args.observe_native_requests else "")
artifacts = json.loads((OUT / "native-elicitation-artifacts.json").read_text())
roots = {"nexus": ROOT, "core": ROOT.parent / "okto-nexus-connector-core",
         "connector": ROOT.parent / "okto-nexus-connector"}
modules = {"nexus": "okto_nexus", "core": "nexus_connector_core",
           "connector": "okto_nexus_connector"}
names = ("nexus", "core")
verified = {}
for name in names:
    package = importlib.import_module(modules[name])
    location = Path(package.__file__).resolve().parent
    assert "site-packages" in str(location)
    wheel = Path(artifacts[name]["wheel"])
    assert hashlib.sha256(wheel.read_bytes()).hexdigest() == artifacts[name]["sha256"]
    count = 0
    with zipfile.ZipFile(wheel) as archive:
        for member in archive.namelist():
            if not member.startswith(modules[name] + "/") or member.endswith("/"):
                continue
            relative = member[len(modules[name]) + 1:]
            assert (location / relative).read_bytes() == archive.read(member)
            assert (roots[name] / "src" / member).read_bytes() == archive.read(member)
            count += 1
    verified[name] = {"path": str(location), "files": count}
assert importlib.util.find_spec("okto_nexus_connector") is None
try:
    importlib.metadata.distribution("okto-nexus-connector")
except importlib.metadata.PackageNotFoundError:
    pass
else:
    raise AssertionError("The Connector application must not be installed.")
root = ROOT / "tests/execution_r4"
tests = ["test_real_embedded_mcp.py"]
os.environ["OKTO_NEXUS_REAL_MCP"] = "1"
os.environ["OKTO_NEXUS_REAL_MCP_REPORT"] = str(OUT / prefix)
if args.suite == "pi_rpc":
    tests = ["test_real_embedded_pi.py"]
    os.environ["OKTO_NEXUS_REAL_PI"] = "1"
    os.environ["OKTO_NEXUS_REAL_PI_REPORT"] = str(OUT / (prefix + "-pi_rpc.json"))
if args.observe_native_requests:
    os.environ["OKTO_NEXUS_OBSERVE_CODEX_REQUESTS"] = str(OUT / (prefix + "-codex-requests.json"))
config = Path.cwd() / "pytest.ini"
assert config.read_text().strip() == "[pytest]"
command = [sys.executable, "-I", "-m", "pytest", "-c", str(config),
    "--rootdir=" + str(root), "--confcutdir=" + str(root),
    "-o", "asyncio_mode=auto", "-o", "asyncio_default_fixture_loop_scope=function",
    *[str(root / test) for test in tests], "-q",
    *([] if args.suite == "pi_rpc" else ["-k", args.suite]),
    "--junitxml=" + str(OUT / (prefix + "-installed-" + args.suite + ".xml"))]
# A failed attempt must not leave a previous successful journey as its report.
journey_report = OUT / (prefix + "-" + args.suite + ".json")
if journey_report.exists():
    journey_report.rename(journey_report.with_name(journey_report.stem + "-previous-" + str(time.time_ns()) + ".json"))
started_at = time.time()
with (OUT / (prefix + "-installed-" + args.suite + ".log")).open("w", encoding="utf-8") as log:
    result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
record = dict(command=command, cwd=str(Path.cwd()), verified_packages=verified,
    started_at=started_at, finished_at=time.time(), journey_report_written=journey_report.exists(),
    native_request_observer=args.observe_native_requests,
    connector_absent=True, exit_code=result.returncode,
    scope="Real installed provider through automatic embedded owner and protected vault: TCP HTTP MCP for Codex/Claude, native action bridge for Pi. Server release gate overridden; native qualification unchanged.")
(OUT / (prefix + "-installed-" + args.suite + ".json")).write_text(
    json.dumps(record, indent=2) + "\n", encoding="utf-8")
print((OUT / (prefix + "-installed-" + args.suite + ".log")).read_text(encoding="utf-8")[-6000:])
raise SystemExit(result.returncode)

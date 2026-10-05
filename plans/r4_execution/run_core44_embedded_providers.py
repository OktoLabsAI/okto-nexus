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
import zipfile

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "plans/r4_execution/evidence"
parser = argparse.ArgumentParser()
parser.add_argument("suite", choices=["pi_rpc", "codex_app_server", "claude_stream"])
args = parser.parse_args()
artifacts = json.loads((OUT / "running-launch-artifacts.json").read_text())
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
    verified[name] = {"path": str(location), "files": count, "artifact": artifacts[name]}
assert importlib.util.find_spec("okto_nexus_connector") is None
try:
    importlib.metadata.distribution("okto-nexus-connector")
except importlib.metadata.PackageNotFoundError:
    pass
else:
    raise AssertionError("The Connector application must not be installed.")
root = ROOT / "tests/execution_r4"
tests = ["test_real_embedded_pi.py" if args.suite == "pi_rpc" else "test_real_embedded_mcp.py"]
os.environ["OKTO_NEXUS_REAL_MCP"] = "1"
os.environ["OKTO_NEXUS_REAL_PI"] = "1"
os.environ["OKTO_NEXUS_REAL_PI_REPORT"] = str(OUT / "core44-embedded-pi_rpc.json")
os.environ["OKTO_NEXUS_REAL_MCP_REPORT"] = str(OUT / "core44-embedded")
config = Path.cwd() / "pytest.ini"
assert config.read_text().strip() == "[pytest]"
command = [sys.executable, "-I", "-m", "pytest", "-c", str(config),
    "--rootdir=" + str(root), "--confcutdir=" + str(root),
    "-o", "asyncio_mode=auto", "-o", "asyncio_default_fixture_loop_scope=function",
    *[str(root / test) for test in tests], "-q",
    "-k", "real_pi" if args.suite == "pi_rpc" else args.suite,
    "--junitxml=" + str(OUT / ("core44-embedded-installed-" + args.suite + ".xml"))]
import time
for suffix in (".json", "-installed.json", "-installed.xml", "-installed.log"):
    name = ("core44-embedded-" + args.suite + suffix if suffix == ".json"
            else "core44-embedded-installed-" + args.suite + suffix.removeprefix("-installed"))
    previous = OUT / name
    if previous.exists():
        previous.rename(previous.with_name(previous.stem + "-previous-" + str(time.time_ns()) + previous.suffix))
with (OUT / ("core44-embedded-installed-" + args.suite + ".log")).open("w", encoding="utf-8") as log:
    result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
record = dict(test_sha256=hashlib.sha256((root / tests[0]).read_bytes()).hexdigest(), command=command, cwd=str(Path.cwd()), verified_packages=verified,
    connector_absent=True, exit_code=result.returncode,
    scope="Real installed provider with automatic embedded owner and protected vault; MCP uses TCP HTTP; Pi uses the application TestClient and real native socket. Server release gate overridden; native qualification unchanged.")
(OUT / ("core44-embedded-installed-" + args.suite + ".json")).write_text(
    json.dumps(record, indent=2) + "\n", encoding="utf-8")
print((OUT / ("core44-embedded-installed-" + args.suite + ".log")).read_text(encoding="utf-8")[-6000:])
raise SystemExit(result.returncode)

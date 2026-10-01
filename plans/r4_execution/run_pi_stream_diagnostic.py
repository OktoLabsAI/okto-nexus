"""Run one real provider through installed Nexus, Connector and Core wheels."""
import argparse
import hashlib
import importlib
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
parser.add_argument("adapter", choices=["pi_rpc", "codex_app_server", "claude_stream"])
args = parser.parse_args()
artifacts = json.loads((OUT / "pi-opening-artifacts.json").read_text())
artifacts["core"] = json.loads((OUT / "pi-opening-core-artifact.json").read_text())
roots = {"nexus": ROOT, "connector": ROOT.parent / "okto-nexus-connector",
         "core": ROOT.parent / "okto-nexus-connector-core"}
modules = {"nexus": "okto_nexus", "connector": "okto_nexus_connector", "core": "nexus_connector_core"}
verified = {}
for name, module in modules.items():
    package = importlib.import_module(module)
    location = Path(package.__file__).resolve().parent
    assert "site-packages" in str(location)
    wheel = Path(artifacts[name]["wheel"])
    assert hashlib.sha256(wheel.read_bytes()).hexdigest() == artifacts[name]["sha256"]
    count = 0
    with zipfile.ZipFile(wheel) as archive:
        for member in archive.namelist():
            if member.startswith(module + "/") and not member.endswith("/"):
                relative = member.split("/", 1)[1]
                assert (location / relative).read_bytes() == archive.read(member)
                assert (roots[name] / "src" / member).read_bytes() == archive.read(member)
                count += 1
    verified[name] = dict(path=str(location), files=count, artifact=artifacts[name])
assert (Path.cwd() / "pytest.ini").read_text().strip() == "[pytest]"
prefix = "pi-stream-diagnostic"
for suffix in (".json", "-progress.json", "-installed.json", "-installed.xml", "-installed.log"):
    previous = OUT / (prefix + "-" + args.adapter + suffix)
    if previous.exists():
        previous.rename(previous.with_name(previous.stem + "-previous-" + str(time.time_ns()) + previous.suffix))
os.environ["OKTO_NEXUS_REAL_CONNECTOR"] = "1"
os.environ["OKTO_NEXUS_PI_STREAM_DIAGNOSTIC"] = "1"
os.environ["OKTO_NEXUS_REAL_CONNECTOR_REPORT"] = str(OUT / prefix)
test_root = ROOT / "tests/execution_r4"
test_sha256 = hashlib.sha256((test_root / "test_real_connector_providers.py").read_bytes()).hexdigest()
command = [sys.executable, "-I", "-m", "pytest", "-c", str(Path.cwd() / "pytest.ini"),
    "--rootdir=" + str(test_root), "--confcutdir=" + str(test_root),
    str(test_root / "test_real_connector_providers.py"), "-k", args.adapter, "-q", "--tb=short",
    "--junitxml=" + str(OUT / (prefix + "-" + args.adapter + "-installed.xml"))]
started = time.time()
log = OUT / (prefix + "-" + args.adapter + "-installed.log")
with log.open("w", encoding="utf-8") as stream:
    result = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT)
(OUT / (prefix + "-" + args.adapter + "-installed.json")).write_text(json.dumps(dict(
    command=command, cwd=str(Path.cwd()), started_at=started, finished_at=time.time(),
    verified_packages=verified, test_sha256=test_sha256, exit_code=result.returncode,
    scope="Actual public Connector onboarding, daemon and real provider over loopback HTTP/WSS. Server release gates test-only; native qualification unchanged."),
    indent=2) + "\n", encoding="utf-8")
print(log.read_text(encoding="utf-8")[-7000:])
raise SystemExit(result.returncode)

"""Run an isolated missing-login case against the installed three-product set."""
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
parser.add_argument("adapter", choices=["claude", "codex", "pi"])
args = parser.parse_args()
artifacts = json.loads((OUT / "native-auth-artifacts.json").read_text())
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
prefix = "native-auth-" + args.adapter
for suffix in ("json", "xml", "log"):
    path = OUT / (prefix + "-installed." + suffix)
    if path.exists():
        path.rename(path.with_name(path.stem + "-previous-" + str(time.time_ns()) + path.suffix))
test_root = ROOT.parent / "okto-nexus-connector-core/tests"
test = test_root / "test_real_native_auth_failure.py"
assert (Path.cwd() / "pytest.ini").read_text().strip() == "[pytest]"
command = [sys.executable, "-I", "-m", "pytest", "-c", str(Path.cwd() / "pytest.ini"),
    "--rootdir=" + str(test_root), "--confcutdir=" + str(test_root),
    str(test) + "::test_real_" + args.adapter + "_missing_login_has_durable_authentication_error",
    "-q", "--tb=short", "--junitxml=" + str(OUT / (prefix + "-installed.xml"))]
env = {**os.environ, "OKTO_NEXUS_REAL_AUTH_FAILURES": "1"}
started = time.time()
with (OUT / (prefix + "-installed.log")).open("w") as log:
    result = subprocess.run(command, env=env, stdout=log, stderr=subprocess.STDOUT)
(OUT / (prefix + "-installed.json")).write_text(json.dumps(dict(
    command=command, cwd=str(Path.cwd()), started_at=started, finished_at=time.time(),
    exit_code=result.returncode, verified_packages=verified,
    test_sha256=hashlib.sha256(test.read_bytes()).hexdigest()), indent=2) + "\n")
print((OUT / (prefix + "-installed.log")).read_text()[-5000:])
raise SystemExit(result.returncode)

"""Verify local preparation with installed wheels, including no Connector."""
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
parser.add_argument("suite", choices=["nexus", "isolated", "real_pi"])
args = parser.parse_args()
artifacts = json.loads((OUT / "local-discovery-artifacts.json").read_text())
roots = {"nexus": ROOT, "core": ROOT.parent / "okto-nexus-connector-core",
         "connector": ROOT.parent / "okto-nexus-connector"}
modules = {"nexus": "okto_nexus", "core": "nexus_connector_core",
           "connector": "okto_nexus_connector"}
names = ("nexus", "core") if args.suite in ("isolated", "real_pi") else tuple(modules)
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
if args.suite in ("isolated", "real_pi"):
    assert importlib.util.find_spec("okto_nexus_connector") is None
    try:
        importlib.metadata.distribution("okto-nexus-connector")
    except importlib.metadata.PackageNotFoundError:
        pass
    else:
        raise AssertionError("The Connector application must not be installed.")
root = ROOT / "tests/execution_r4"
if args.suite == "real_pi":
    os.environ["OKTO_NEXUS_REAL_PI"] = "1"
    os.environ["OKTO_NEXUS_REAL_PI_REPORT"] = str(OUT / "real-embedded-pi-installed.json")
    tests = ["test_real_embedded_pi.py"]
else:
    tests = ["test_local_discovery.py", "test_core_inventory.py",
             "test_embedded_inventory.py", "test_local_realization.py", "../test_serve_args.py"]
config = Path.cwd() / "pytest.ini"
assert config.read_text().strip() == "[pytest]"
command = [sys.executable, "-I", "-m", "pytest", "-c", str(config),
    "--rootdir=" + str(root), "--confcutdir=" + str(root),
    "-o", "asyncio_mode=auto", "-o", "asyncio_default_fixture_loop_scope=function",
    *[str(root / test) for test in tests], "-q",
    *(["-k", "not connector"] if args.suite in ("isolated", "real_pi") else []),
    "--junitxml=" + str(OUT / ("local-discovery-installed-" + args.suite + ".xml"))]
with (OUT / ("local-discovery-installed-" + args.suite + ".log")).open("w", encoding="utf-8") as log:
    result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
record = dict(command=command, cwd=str(Path.cwd()), verified_packages=verified,
    connector_absent=args.suite in ("isolated", "real_pi"), exit_code=result.returncode,
    scope="Local discovery configuration and installed regression. real_pi uses the real production Pi factory and OS vault; Server release gate is overridden in the test, native qualification is not.")
(OUT / ("local-discovery-installed-" + args.suite + ".json")).write_text(
    json.dumps(record, indent=2) + "\n", encoding="utf-8")
print((OUT / ("local-discovery-installed-" + args.suite + ".log")).read_text(encoding="utf-8")[-6000:])
raise SystemExit(result.returncode)

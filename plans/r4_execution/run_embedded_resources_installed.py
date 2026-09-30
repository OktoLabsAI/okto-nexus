"""Verify local preparation with installed wheels, including no Connector."""
import argparse
import hashlib
import importlib
import importlib.metadata
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "plans/r4_execution/evidence"
parser = argparse.ArgumentParser()
parser.add_argument("suite", choices=["nexus", "isolated"])
args = parser.parse_args()
artifacts = json.loads((OUT / "embedded-resources-artifacts.json").read_text())
roots = {"nexus": ROOT, "core": ROOT.parent / "okto-nexus-connector-core",
         "connector": ROOT.parent / "okto-nexus-connector"}
modules = {"nexus": "okto_nexus", "core": "nexus_connector_core",
           "connector": "okto_nexus_connector"}
names = ("nexus", "core") if args.suite == "isolated" else tuple(modules)
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
if args.suite == "isolated":
    assert importlib.util.find_spec("okto_nexus_connector") is None
    try:
        importlib.metadata.distribution("okto-nexus-connector")
    except importlib.metadata.PackageNotFoundError:
        pass
    else:
        raise AssertionError("The Connector application must not be installed.")
tests = ["test_embedded_dispatch", "test_local_launch", "test_local_realization", "test_embedded_inventory", "test_ns07", "test_core_inventory"]
if args.suite == "nexus":
    tests += ["test_event_ingress", "test_ns02_receipts", "test_reconciliation"]
root = ROOT / "tests/execution_r4"
config = Path.cwd() / "pytest.ini"
assert config.read_text().strip() == "[pytest]"
command = [sys.executable, "-I", "-m", "pytest", "-c", str(config),
    "--rootdir=" + str(root), "--confcutdir=" + str(root),
    "-o", "asyncio_mode=auto", "-o", "asyncio_default_fixture_loop_scope=function",
    *[str(root / (test + ".py")) for test in tests], "-q",
    "--junitxml=" + str(OUT / ("embedded-resources-installed-" + args.suite + ".xml"))]
with (OUT / ("embedded-resources-installed-" + args.suite + ".log")).open("w", encoding="utf-8") as log:
    result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
record = dict(command=command, cwd=str(Path.cwd()), verified_packages=verified,
    connector_absent=args.suite == "isolated", exit_code=result.returncode,
    scope="Embedded released-resource reconciliation, cold readiness and public new-session admission. Uncertain native resources and full M05 remain open.")
(OUT / ("embedded-resources-installed-" + args.suite + ".json")).write_text(
    json.dumps(record, indent=2) + "\n", encoding="utf-8")
print((OUT / ("embedded-resources-installed-" + args.suite + ".log")).read_text(encoding="utf-8")[-6000:])
raise SystemExit(result.returncode)

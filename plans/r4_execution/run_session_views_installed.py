"""Verify the installed session query and neighboring runtime routes."""
import hashlib
import importlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "plans/r4_execution/evidence"
artifacts = json.loads((OUT / "running-launch-artifacts.json").read_text())
artifacts["nexus"] = json.loads((OUT / "session-views-artifact.json").read_text())
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
root = ROOT / "tests/execution_r4"
tests = ["test_session_views.py", "test_ns02_receipts.py",
         "test_embedded_dispatch.py", "test_session_capabilities.py"]
assert (Path.cwd() / "pytest.ini").read_text().strip() == "[pytest]"
command = [sys.executable, "-I", "-m", "pytest", "-c", str(Path.cwd() / "pytest.ini"),
    "--rootdir=" + str(root), "--confcutdir=" + str(root),
    *[str(root / name) for name in tests], "-q", "--tb=short",
    "--junitxml=" + str(OUT / "session-views-installed.xml")]
with (OUT / "session-views-installed.log").open("w", encoding="utf-8") as log:
    result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
(OUT / "session-views-installed.json").write_text(json.dumps(dict(
    command=command, cwd=str(Path.cwd()), verified_packages=verified,
    exit_code=result.returncode, test_hashes={name: hashlib.sha256((root / name).read_bytes()).hexdigest()
        for name in tests}), indent=2) + "\n", encoding="utf-8")
print((OUT / "session-views-installed.log").read_text(encoding="utf-8")[-5000:])
raise SystemExit(result.returncode)

"""Recheck normative M0–M3 acceptance on the cutover-fence wheel."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile
import okto_nexus

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "plans/r4_execution/evidence"
artifact = json.loads((OUT / "migration-cutover-artifacts.json").read_text())["nexus"]
location = Path(okto_nexus.__file__).resolve().parent
assert "site-packages" in str(location)
wheel = Path(artifact["wheel"])
assert hashlib.sha256(wheel.read_bytes()).hexdigest() == artifact["sha256"]
with zipfile.ZipFile(wheel) as archive:
    for name in archive.namelist():
        if name.startswith("okto_nexus/") and not name.endswith("/"):
            assert (location / name.split("/", 1)[1]).read_bytes() == archive.read(name)
test = ROOT / "tests/execution_r4/test_ns15.py"
args = ["-c", str(Path.cwd() / "pytest.ini"), "--rootdir=" + str(test.parent),
        "--confcutdir=" + str(test.parent), "-o", "asyncio_mode=auto",
        "-o", "asyncio_default_fixture_loop_scope=function", str(test) + "::test_ns15_01",
        "-q", "--tb=short", "--junitxml=" + str(OUT / "ns15-01-cutover-installed.xml")]
command = [sys.executable, "-I", "-c", "import pytest; raise SystemExit(pytest.main(" + repr(args) + "))"]
with (OUT / "ns15-01-cutover-installed.log").open("w", encoding="utf-8") as log:
    result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
(OUT / "ns15-01-cutover-installed.json").write_text(json.dumps({"command": command,
    "artifact": artifact, "installed": str(location), "exit_code": result.returncode,
    "test_sha256": hashlib.sha256(test.read_bytes()).hexdigest()}, indent=2) + "\n")
print((OUT / "ns15-01-cutover-installed.log").read_text(encoding="utf-8"))
raise SystemExit(result.returncode)

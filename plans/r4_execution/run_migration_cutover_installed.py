"""Verify the legacy cutover fence and affected installed binding regressions."""
import hashlib
import importlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "plans/r4_execution/evidence"
artifacts = json.loads((OUT / "migration-cutover-artifacts.json").read_text())
verified = {}
for name, module in (("nexus", "okto_nexus"), ("core", "nexus_connector_core"),
                     ("connector", "okto_nexus_connector")):
    location = Path(importlib.import_module(module).__file__).resolve().parent
    assert "site-packages" in str(location)
    wheel = Path(artifacts[name]["wheel"])
    assert hashlib.sha256(wheel.read_bytes()).hexdigest() == artifacts[name]["sha256"]
    with zipfile.ZipFile(wheel) as archive:
        for member in archive.namelist():
            if member.startswith(module + "/") and not member.endswith("/"):
                assert (location / member.split("/", 1)[1]).read_bytes() == archive.read(member)
                if name == "nexus" and not member.startswith(module + "/adapters/inbound/http/static/"):
                    assert (ROOT / "src" / member).read_bytes() == archive.read(member)
    verified[name] = {"installed": str(location), **artifacts[name]}

tests = [ROOT / "tests/execution_r4" / (name + ".py") for name in (
    "test_migration_resume", "test_binding_migration", "test_local_realization",
    "test_binding_operator", "test_binding_replacement", "test_migration_catalog")]
arguments = ["-c", str(Path.cwd() / "pytest.ini"), "--rootdir=" + str(ROOT / "tests/execution_r4"),
    "--confcutdir=" + str(ROOT / "tests/execution_r4"), "-o", "asyncio_mode=auto",
    "-o", "asyncio_default_fixture_loop_scope=function", *map(str, tests), "-q", "--tb=short",
    "--junitxml=" + str(OUT / "migration-cutover-installed.xml")]
code = "import pytest; raise SystemExit(pytest.main(" + repr(arguments) + "))"
command = [sys.executable, "-I", "-c", code]
with (OUT / "migration-cutover-installed.log").open("w", encoding="utf-8") as log:
    result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
(OUT / "migration-cutover-installed.json").write_text(json.dumps({
    "command": command, "cwd": str(Path.cwd()), "verified_packages": verified,
    "exit_code": result.returncode,
    "test_hashes": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in tests},
}, indent=2) + "\n", encoding="utf-8")
print((OUT / "migration-cutover-installed.log").read_text(encoding="utf-8")[-5000:])
raise SystemExit(result.returncode)

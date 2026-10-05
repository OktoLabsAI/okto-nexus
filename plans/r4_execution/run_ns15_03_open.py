"""Build an isolated artifact and verify canonical/legacy callers installed."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "plans/r4_execution/evidence"
WORK = Path(tempfile.mkdtemp(prefix="okto-r4-canonical-open-"))
PYTHON = Path("C:/Users/jpamb/AppData/Local/Temp/okto-r4-migration-resume-bkj6ies1/venv313/Scripts/python.exe")
source = WORK / "source"
shutil.copytree(ROOT / "src", source / "src", ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.egg-info"))
for name in ("pyproject.toml", "README.md", "LICENSE"):
    shutil.copy2(ROOT / name, source / name)
for name in ("assets/index-DTt0-V6O.js", "assets/index-DlAmqHcP.css", "index.html"):
    relative = "src/okto_nexus/adapters/inbound/http/static/" + name
    (source / relative).write_bytes(subprocess.check_output(["rtk", "proxy", "git", "show", "HEAD:" + relative], cwd=ROOT))
with (OUT / "ns15-03-open-build.log").open("w", encoding="utf-8") as log:
    subprocess.run(["rtk", "proxy", "uv", "build", "--wheel", "--out-dir", str(WORK / "dist"), str(source)],
                   stdout=log, stderr=subprocess.STDOUT, check=True)
wheel = next((WORK / "dist").glob("*.whl"))
artifacts = json.loads((OUT / "ns15-02-final-artifacts.json").read_text())
artifacts["nexus"] = dict(wheel=str(wheel), sha256=hashlib.sha256(wheel.read_bytes()).hexdigest())
(OUT / "ns15-03-open-artifacts.json").write_text(json.dumps(artifacts, indent=2) + "\n", encoding="utf-8")
subprocess.run(["rtk", "proxy", "uv", "pip", "install", "--python", str(PYTHON), "--no-deps", "--reinstall", str(wheel)], check=True)
verification = '''import importlib, hashlib, json, pathlib, zipfile
artifacts=json.loads(pathlib.Path(ARTIFACTS).read_text())
for name,module in (("nexus","okto_nexus"),("core","nexus_connector_core"),("connector","okto_nexus_connector")):
 location=pathlib.Path(importlib.import_module(module).__file__).resolve().parent
 assert "site-packages" in str(location)
 wheel=pathlib.Path(artifacts[name]["wheel"])
 assert hashlib.sha256(wheel.read_bytes()).hexdigest()==artifacts[name]["sha256"]
 with zipfile.ZipFile(wheel) as archive:
  for member in archive.namelist():
   if member.startswith(module+"/") and not member.endswith("/"):
    assert (location/member.split("/",1)[1]).read_bytes()==archive.read(member)
    if name=="nexus" and "/static/" not in member:
     assert (pathlib.Path(ROOT)/"src"/member).read_bytes()==archive.read(member)
'''
verification = "ARTIFACTS=" + repr(str(OUT / "ns15-03-open-artifacts.json")) + "\nROOT=" + repr(str(ROOT)) + "\n" + verification
subprocess.run(["rtk", "proxy", str(PYTHON), "-I", "-c", verification], check=True, cwd=WORK)
(WORK / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
campaigns = {
    "r4": ["execution_r4/" + name + ".py" for name in (
        "test_harness_canonical", "test_embedded_dispatch", "test_local_realization")],
    "legacy": [name + ".py" for name in (
        "test_runtime_grants", "test_runtime_monitor_authorization", "test_runtime_disabled_acceptance")],
    "architecture": ["test_import_boundary.py"],
}
results = {}
for campaign, files in campaigns.items():
    paths = [ROOT / "tests" / file for file in files]
    args = ["-c", str(WORK / "pytest.ini"), "--rootdir=" + str(ROOT / "tests"),
            "--confcutdir=" + str(ROOT / "tests/execution_r4" if campaign != "legacy" else ROOT / "tests"),
            "-o", "asyncio_mode=auto", "-o", "asyncio_default_fixture_loop_scope=function",
            *map(str, paths), "-q", "--tb=short",
            "--junitxml=" + str(OUT / ("ns15-03-open-" + campaign + ".xml"))]
    command = ["rtk", "proxy", str(PYTHON), "-I", "-c", "import pytest; raise SystemExit(pytest.main(" + repr(args) + "))"]
    log_path = OUT / ("ns15-03-open-" + campaign + ".log")
    with log_path.open("w", encoding="utf-8") as log:
        result = subprocess.run(command, cwd=WORK, stdout=log, stderr=subprocess.STDOUT)
    results[campaign] = dict(command=command, exit_code=result.returncode,
        test_hashes={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
    print(log_path.read_text(encoding="utf-8")[-4500:], flush=True)
    (OUT / "ns15-03-open-installed.json").write_text(json.dumps(dict(
        cwd=str(WORK), artifacts=artifacts, results=results), indent=2) + "\n", encoding="utf-8")
    if result.returncode:
        raise SystemExit(result.returncode)

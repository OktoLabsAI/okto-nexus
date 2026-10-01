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
WORK = Path(tempfile.mkdtemp(prefix="okto-r4-event-views-"))
PYTHON = Path("C:/Users/jpamb/AppData/Local/Temp/okto-r4-migration-resume-bkj6ies1/venv313/Scripts/python.exe")
artifacts = json.loads((OUT / 'ns15-03-event-views-artifacts.json').read_text())
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
verification = "ARTIFACTS=" + repr(str(OUT / "ns15-03-event-views-artifacts.json")) + "\nROOT=" + repr(str(ROOT)) + "\n" + verification
subprocess.run(["rtk", "proxy", str(PYTHON), "-I", "-c", verification], check=True, cwd=WORK)
(WORK / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
campaigns = {
 'r4': ['execution_r4/test_canonical_consumption.py', 'execution_r4/test_remote_connection.py::test_remote_domain_delivery_keeps_exclusive_claim_from_mcp'],
 'architecture': ['test_import_boundary.py'],
}
results = {}
for campaign, files in campaigns.items():
    paths = [ROOT / "tests" / file for file in files]
    args = ["-c", str(WORK / "pytest.ini"), "--rootdir=" + str(ROOT / "tests"),
            "--confcutdir=" + str(ROOT / "tests/execution_r4" if campaign != "legacy" else ROOT / "tests"),
            "-o", "asyncio_mode=auto", "-o", "asyncio_default_fixture_loop_scope=function",
            *map(str, paths), "-q", "--tb=short",
            "--junitxml=" + str(OUT / ("ns06-05-consumption-" + campaign + ".xml"))]
    command = ["rtk", "proxy", str(PYTHON), "-I", "-c", "import pytest; raise SystemExit(pytest.main(" + repr(args) + "))"]
    log_path = OUT / ("ns06-05-consumption-" + campaign + ".log")
    with log_path.open("w", encoding="utf-8") as log:
        result = subprocess.run(command, cwd=WORK, stdout=log, stderr=subprocess.STDOUT)
    results[campaign] = dict(command=command, exit_code=result.returncode,
        test_hashes={str(p.relative_to(ROOT)): hashlib.sha256(Path(str(p).split(chr(58)+chr(58))[0]).read_bytes()).hexdigest() for p in paths})
    print(log_path.read_text(encoding="utf-8")[-4500:], flush=True)
    (OUT / "ns06-05-consumption-installed.json").write_text(json.dumps(dict(
        cwd=str(WORK), artifacts=artifacts, results=results), indent=2) + "\n", encoding="utf-8")
    if result.returncode:
        raise SystemExit(result.returncode)

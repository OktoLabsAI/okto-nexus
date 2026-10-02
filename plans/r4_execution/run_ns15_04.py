"""Build an isolated artifact and verify canonical/legacy callers installed."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile

parser = argparse.ArgumentParser()
parser.add_argument('--resume', action='store_true')
parser.add_argument('--campaign', choices=('r4', 'legacy', 'architecture'))
options = parser.parse_args()

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "plans/r4_execution/evidence"
PYTHON = Path("C:/Users/jpamb/AppData/Local/Temp/okto-r4-migration-resume-bkj6ies1/venv313/Scripts/python.exe")
if options.resume:
    artifacts = json.loads((OUT / "ns15-04-artifacts.json").read_text())
    WORK = Path(artifacts["nexus"]["wheel"]).parent.parent
else:
    WORK = Path(tempfile.mkdtemp(prefix="okto-r4-ns15-04-"))
    source = WORK / "source"
    shutil.copytree(ROOT / "src", source / "src", ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.egg-info"))
    for name in ("pyproject.toml", "README.md", "LICENSE"):
        shutil.copy2(ROOT / name, source / name)
    for name in ("assets/index-DTt0-V6O.js", "assets/index-DlAmqHcP.css", "index.html"):
        relative = "src/okto_nexus/adapters/inbound/http/static/" + name
        (source / relative).write_bytes(subprocess.check_output(["rtk", "proxy", "git", "show", "HEAD:" + relative], cwd=ROOT))
    with (OUT / "ns15-04-build.log").open("w", encoding="utf-8") as log:
        subprocess.run(["rtk", "proxy", "uv", "build", "--wheel", "--out-dir", str(WORK / "dist"), str(source)],
                       stdout=log, stderr=subprocess.STDOUT, check=True)
    wheel = next((WORK / "dist").glob("*.whl"))
    artifacts = json.loads((OUT / "ns15-02-final-artifacts.json").read_text())
    artifacts["nexus"] = dict(wheel=str(wheel), sha256=hashlib.sha256(wheel.read_bytes()).hexdigest())
    (OUT / "ns15-04-artifacts.json").write_text(json.dumps(artifacts, indent=2) + "\n", encoding="utf-8")
    subprocess.run(["rtk", "proxy", "uv", "pip", "install", "--python", str(PYTHON), "--no-deps", "--reinstall", str(wheel)], check=True)
verification = '''import importlib, hashlib, json, pathlib, zipfile
artifacts=json.loads(pathlib.Path(ARTIFACTS).read_text())
for name,module in (("nexus","okto_nexus"),("core","nexus_connector_core"),("connector","okto_nexus_connector")):
 location=pathlib.Path(importlib.import_module(module).__file__).resolve().parent
 assert "site-packages" in str(location)
 wheel=pathlib.Path(artifacts[name]["wheel"])
 assert hashlib.sha256(wheel.read_bytes()).hexdigest()==artifacts[name]["sha256"]
 with zipfile.ZipFile(wheel) as archive:
  if name == "nexus":
   members = archive.namelist()
   assert not any(member.startswith("legacy_native_fixture/") for member in members)
   for retired in ("pi", "codex", "claude_code_stream", "claude_code_attach", "owned_process", "windows_process", "linux_process", "linux_process_guardian", "event_buffers", "framing"):
    assert "okto_nexus/adapters/outbound/harness/"+retired+".py" not in members
  for member in archive.namelist():
   if member.startswith(module+"/") and not member.endswith("/"):
    assert (location/member.split("/",1)[1]).read_bytes()==archive.read(member)
    if name=="nexus" and "/static/" not in member:
     assert (pathlib.Path(ROOT)/"src"/member).read_bytes()==archive.read(member)
'''
verification = "ARTIFACTS=" + repr(str(OUT / "ns15-04-artifacts.json")) + "\nROOT=" + repr(str(ROOT)) + "\n" + verification
subprocess.run(["rtk", "proxy", str(PYTHON), "-I", "-c", verification], check=True, cwd=WORK)
(WORK / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
campaigns = {
    'r4': [
        'execution_r4/test_ns15.py::test_ns15_04',
        'execution_r4/test_ns15.py::test_ns15_02',
    ],
    'legacy': [
        'test_runtime_backup_restore.py',
    ],
    'architecture': [
        'test_import_boundary.py',
    ],
}
manifest_path = OUT / "ns15-04-installed.json"
results = json.loads(manifest_path.read_text())["results"] if options.resume and manifest_path.exists() else {}
for campaign, files in campaigns.items():
    if options.campaign and campaign != options.campaign:
        continue
    paths = [ROOT / "tests" / file for file in files]
    args = ["-c", str(WORK / "pytest.ini"), "--rootdir=" + str(ROOT / "tests"),
            "--confcutdir=" + str(ROOT / "tests/execution_r4" if campaign not in {"legacy", "fixtures", "lifecycle", "rollout"} else ROOT / "tests"),
            "-o", "asyncio_mode=auto", "-o", "asyncio_default_fixture_loop_scope=function",
            *map(str, paths), "-q", "--tb=short",
            "--junitxml=" + str(OUT / ("ns15-04-" + campaign + ".xml"))]
    command = ["rtk", "proxy", str(PYTHON), "-I", "-c", "import pytest; raise SystemExit(pytest.main(" + repr(args) + "))"]
    log_path = OUT / ("ns15-04-" + campaign + ".log")
    with log_path.open("w", encoding="utf-8") as log:
        result = subprocess.run(command, cwd=WORK, stdout=log, stderr=subprocess.STDOUT)
    if options.resume and manifest_path.exists():
        previous = json.loads(manifest_path.read_text())
        assert previous["artifacts"] == artifacts
        results.update(previous["results"])
    results[campaign] = dict(command=command, exit_code=result.returncode,
        test_hashes={str(p.relative_to(ROOT)): hashlib.sha256(Path(str(p).split("::")[0]).read_bytes()).hexdigest() for p in paths})
    print(log_path.read_text(encoding="utf-8")[-4500:], flush=True)
    (OUT / "ns15-04-installed.json").write_text(json.dumps(dict(
        cwd=str(WORK), artifacts=artifacts, results=results), indent=2) + "\n", encoding="utf-8")
    if result.returncode:
        raise SystemExit(result.returncode)

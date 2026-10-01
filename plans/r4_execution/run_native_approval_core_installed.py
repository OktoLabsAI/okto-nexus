"""Verify operational proposal preservation in the installed Core wheel."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import zipfile
import nexus_connector_core as core

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/"plans/r4_execution/evidence"
CORE=ROOT.parent/"okto-nexus-connector-core"
artifact=json.loads((OUT/"native-approvals-core-artifact.json").read_text())
wheel=Path(artifact["wheel"])
assert hashlib.sha256(wheel.read_bytes()).hexdigest()==artifact["sha256"]
location=Path(core.__file__).resolve().parent
assert "site-packages" in str(location) and core.__version__=="0.2.41.dev0"
assert importlib.util.find_spec("okto_nexus") is None
assert importlib.util.find_spec("okto_nexus_connector") is None
count=0
with zipfile.ZipFile(wheel) as archive:
    for name in archive.namelist():
        if name.startswith("nexus_connector_core/") and not name.endswith("/"):
            relative=name[len("nexus_connector_core/"):]
            assert archive.read(name)==(CORE/"src"/name).read_bytes()==(location/relative).read_bytes()
            count+=1
config=Path.cwd()/"pytest.ini"
assert config.read_text().strip()=="[pytest]"
tests=["test_operational_native_request.py","test_claude_mcp_permissions.py",
       "test_native_runtime_bridge.py","test_native_redaction.py"]
command=[sys.executable,"-I","-m","pytest","-c",str(config),
         "--rootdir="+str(CORE/"tests"),"--confcutdir="+str(CORE/"tests"),
         *[str(CORE/"tests"/name) for name in tests],"-q",
         "--junitxml="+str(OUT/"native-approvals-core-installed.xml")]
with (OUT/"native-approvals-core-installed.log").open("w",encoding="utf-8") as stream:
    result=subprocess.run(command,stdout=stream,stderr=subprocess.STDOUT)
record={"command":command,"cwd":str(Path.cwd()),"core_version":core.__version__,
        "wheel_sha256":artifact["sha256"],"verified_files":count,"application_packages_absent":True,
        "exit_code":result.returncode,"scope":"Technical native adapters; no product journey acceptance."}
(OUT/"native-approvals-core-installed.json").write_text(json.dumps(record,indent=2)+"\n",encoding="utf-8")
print((OUT/"native-approvals-core-installed.log").read_text(encoding="utf-8")[-4500:])
raise SystemExit(result.returncode)

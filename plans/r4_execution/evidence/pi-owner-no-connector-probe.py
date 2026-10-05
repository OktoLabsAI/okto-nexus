"""Run the embedded domain cycle with every Connector import refused."""
import importlib.abc
from pathlib import Path
import sys

class NoConnector(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "okto_nexus_connector" or fullname.startswith("okto_nexus_connector."):
            raise ModuleNotFoundError("Connector is intentionally unavailable in the embedded campaign.")
sys.meta_path.insert(0, NoConnector())
import nexus_connector_core
import okto_nexus
import pytest
assert "site-packages" in nexus_connector_core.__file__
assert "site-packages" in okto_nexus.__file__
root = Path(__file__).resolve().parents[3]
raise SystemExit(pytest.main([
    "-c", str(Path.cwd() / "pytest.ini"), "--rootdir=" + str(root / "tests"),
    "--confcutdir=" + str(root / "tests"), "-q",
    str(root / "tests/execution_r4/test_pi_native_hosts.py"), "-k", "embedded",
    "--junitxml=" + str(root / "plans/r4_execution/evidence/pi-owner-no-connector.xml")
]))

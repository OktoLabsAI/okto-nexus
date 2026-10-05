"""Run authorized local provider probes with installed Core and local R4 grants."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import nexus_connector_core

parser = argparse.ArgumentParser()
parser.add_argument("provider", choices=["pi_rpc", "codex_app_server", "claude_stream"])
args = parser.parse_args()
assert "site-packages" in nexus_connector_core.__file__
assert nexus_connector_core.__version__ == "0.2.38.dev0"
out = Path(__file__).resolve().parent / "evidence"
baseline = json.loads((out / ("local-managed-" + args.provider + ".json")).read_text())
command = [sys.executable, *baseline["command"][1:], "--renew-r4"]
result = subprocess.run(command, capture_output=True, text=True, timeout=300)
report = json.loads(result.stdout) if result.returncode == 0 else None
passed = bool(report and report.get("open_stage") == "SUBMITTED"
    and report.get("turn_receipt_stage") == "SUCCEEDED"
    and report.get("terminal_outcome") == "success"
    and report.get("renewal_stage") == "RENEWED"
    and report.get("lease_serial") == 2
    and report.get("close_receipt_stage") == "SUCCEEDED"
    and report.get("close_receipt_error") is None)
record = dict(command=command, core_version=nexus_connector_core.__version__,
    core_path=nexus_connector_core.__file__, exit_code=result.returncode,
    accepted=passed, report=report, stderr_present=bool(result.stderr),
    scope="Real local provider through installed Core production factory; locally constructed R4 grants. No Server/Connector journey acceptance.")
(out / ("lease-renewal-provider-" + args.provider + ".json")).write_text(
    json.dumps(record, indent=2) + "\n", encoding="utf-8")
print(json.dumps(record, indent=2))
raise SystemExit(0 if passed else 1)

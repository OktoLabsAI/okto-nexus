"""Finalize static oracle-review correction; no application imports or execution."""
import difflib
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
diff = ""
for old, new in (("browser-s3-reviewed.js", "browser-s3-k03.js"), ("run_s3_v2.py", "run_k03.py")):
    diff += "".join(difflib.unified_diff((HERE / old).read_text(encoding="utf-8").splitlines(True),
        (HERE / new).read_text(encoding="utf-8").splitlines(True), fromfile=old, tofile=new))
(HERE / "K03-counterparts.diff").write_text(diff, encoding="utf-8", newline="\n")
manifest = HERE / "PREPARED-K03-R9.json"
data = json.loads(manifest.read_text(encoding="utf-8"))
for name in ("browser-s3-k03.js", "run_k03.py", "K03-counterparts.diff"):
    path = HERE / name
    data["helper_sha256"][str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
data["static_checks"].update(Node_syntax="PASS", Ruff_0_17_5="PASS")
data["oracle_source_notes"] = [
    "R4 approval detail has no decision_detail producer; CanonicalNativeDecision synthesizes form state from the original approval/proposal and operator identity. No legacy-only detail fields are required.",
    "Exact original key comparison: server/executor/binding/agent/workspace/session/request. Outer binds attention_id to the admitted operation_id.",
    "K03 requires classic Home/controls/bell, not a separate Conversations journey. No Conversations navigation is claimed.",
]
manifest.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8", newline="\n")
for name in ("browser-s3-k03.js", "run_k03.py", "K03-counterparts.diff", "PREPARED-K03-R9.json"):
    print(name, hashlib.sha256((HERE / name).read_bytes()).hexdigest())

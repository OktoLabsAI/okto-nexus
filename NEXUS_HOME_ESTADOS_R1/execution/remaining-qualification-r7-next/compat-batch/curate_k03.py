"""Curate public synthetic evidence only; never import or execute the application."""
import hashlib
import json
from pathlib import Path

import psutil

HERE = Path(__file__).resolve().parent
ROOT = Path(r"C:/Users/jpamb/AppData/Local/Temp/nexus-hst-compat-k03-vf54q4q3")
CONTROL = ROOT / "control"
OUT = HERE / "K03-original-controls-r9"
assert not OUT.exists()
OUT.mkdir()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(name):
    return json.loads((CONTROL / name).read_text(encoding="utf-8"))


def save(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


final = read("final.json")
browser = read("browser-result.json")
cycle = read("cli-cycle-s3-current.json")
active = read("cli-active-s3-current.json")
assert not final["failures"] and not final["remaining"] and not final["listeners"] and not final["containment"]
assert len(browser["checks"]) == 19 and all(check["pass"] for check in browser["checks"])
assert browser["writes"] == []
assert final["before"] == final["after"]
assert all(command["exit_code"] == 0 and not command["timed_out"] for command in final["commands"])
same_birth = []
for birth in final["known_births"]:
    try:
        process = psutil.Process(birth["pid"])
        if abs(process.create_time() - birth["birth"]) < .01:
            same_birth.append({"pid": birth["pid"], "birth": birth["birth"]})
    except psutil.NoSuchProcess:
        pass
assert not same_birth
port = read("canonical-stop.json")["effective_configuration"]["port"]
listeners = [row.pid for row in psutil.net_connections(kind="tcp") if row.status == "LISTEN" and row.laddr.port == port]
assert listeners == []
save("browser-checks.json", browser)
save("module-origins.json", read("owner-imports-s3-current.json"))
save("guards-before-after.json", {"before": final["before"], "after": final["after"],
    "generated_pins": final["rendered_script_and_config_pins"]})
owners = {name: read("owner-" + name + ".json") for name in ("before", "after")}
public_owners = {}
for name, value in owners.items():
    public_owners[name] = {"birth": value["birth"], "exe": value["exe"], "service": {
        key: value["service"].get(key) for key in ("pid", "instance_id", "generation", "state", "ready_for_queries")}}
assert public_owners["before"] == public_owners["after"]
save("owner-proof.json", public_owners)
stop = read("canonical-stop.json")
assert stop["state"] == "stopped" and stop["shutdown_outcome"] == "drained"
save("canonical-stop.json", {key: stop.get(key) for key in ("component", "instance_id", "state", "shutdown_outcome", "reason")})
safe_scalars = ("state", "server_id", "agent_id", "binding_id", "workspace_id", "review_revision", "operation_id",
    "client_intent_id", "action", "intent_hash", "admission_state", "executor_stage", "possible_effect", "retry_safe",
    "receipt_revision", "decision_id", "canonical_state", "native_operation_id", "native_stage", "response_digest",
    "component", "instance_id", "generation", "pid", "ready_for_queries")
documents = []
for path in sorted(CONTROL.glob("cli-s3-current-*.stdout"), key=lambda p: int(p.stem.rsplit("-", 1)[1])):
    raw = json.loads(path.read_text(encoding="utf-8"))
    public = {key: raw[key] for key in safe_scalars if key in raw and (raw[key] is None or isinstance(raw[key], (str, int, bool)))}
    if "scope" in raw:
        public["scope"] = raw["scope"]
    session = raw.get("session")
    if isinstance(session, dict):
        public["session"] = {key: session[key] for key in ("scope", "lifecycle_state") if key in session}
    documents.append({"name": path.name, "raw_sha256": sha(path), "public_fields": public})
assert len(documents) == 14
save("cli-public-documents.json", documents)
save("canonical-operations.json", {"decision_id": cycle["decision_id"], "result_operation_id": cycle["result_operation_id"],
    "binding": active["binding"], "session_id": active["session_id"], "operation_id": active["operation_id"], "approval_id": active["approval_id"]})
qualification = {
    "status": "PASS_SCOPED_K03", "source_commit": "f07163ab7fd618b2ff4247ba6cdb2547b5d4e038",
    "wheel_sha256": "e870ea400435d5b736093990af9b56544661e205ad657bbff83f830421a3e628",
    "manifest_sha256": sha(HERE / "PREPARED-K03-R9.json"), "runner_sha256": sha(HERE / "run_k03.py"),
    "root_gate_sha256": sha(HERE / "ROOT-GATE-K03-R9.json"), "runner_exit_code": 0,
    "browser_checks_passed": 19, "previous_S3_predicates_preserved": 13, "new_original_form_checks": 6,
    "UI_non_read_requests": [], "UI_form_selection_or_decision": False, "CLI_commands": 14,
    "CLI_response_after_panel_closed": True, "canonical_stop": {"state": stop["state"], "shutdown_outcome": stop["shutdown_outcome"]},
    "physical_same_birth_remaining": same_birth, "listeners_after": listeners, "audited_port": port,
    "forced_containment": final["containment"], "commands": final["commands"], "guards_before": final["before"], "guards_after": final["after"],
    "input_readers_released": True, "provider_invocations": 0, "request_TTL_changed": False,
    "strict_CLI_invariants": ["same real foreground PID/birth/instance/generation", "exact profile/checkpoint bytes across browser interval",
        "selected root/configuration/binding/grant digest unchanged", "reconnect same binding and no additional Test/version probe", "close receipt SUCCEEDED and session CLOSED"],
    "raw_final_sha256": sha(CONTROL / "final.json"), "private_logs_copied": False, "cookie_or_token_copied": False,
    "layer": "Installed R9 CLI + real foreground HTTP ServiceLifecycle + actual Chrome with own canonical human cookie; inert Core protocol/Test/version peers",
    "limits": ["Foreground local scope only; no Windows service/logoff/reboot", "Selected protected rows/config/file invariants, not wholeDB read-only",
        "No Conversations navigation claimed or required by literal K03", "No UI answer/selection/deny/Seen/Snooze; CLI alone answered",
        "No real provider, human acceptance or performance qualification", "Private raw logs/auth remain in owned Temp; public data is allowlisted"]}
save("qualification.json", qualification)
(OUT / "report.md").write_text("# K03 original controls complement\n\nPASS scoped: 19 browser predicates (13 preserved + 6 original-form checks), 14 installed CLI documents. The exact request opened from the classic Home bell and retained its original canonical form and controls. No UI selection or decision occurred; the CLI answered after the panel closed.\n\nCanonical stop was stopped/drained. Physical same-birth remaining=0, actual port scan empty, force=0. Source1829, R9 payload1031, old i4 read-only1028 and CLI192 guards stayed unchanged.\n\nNo Conversations navigation, personal service, real provider, human acceptance or performance claim. Selected config/grant/root/file invariants are not a whole-database immutability claim.\n", encoding="utf-8")
# Reject accidental copies of the exact private cookie; no raw log is copied.
cookie = read("operator-cookie.private.json")["cookie"]
assert all(cookie.encode() not in path.read_bytes() for path in OUT.iterdir())
save("manifest.json", {path.name: sha(path) for path in OUT.iterdir()})
print(json.dumps({"folder": str(OUT), "qualification_sha256": sha(OUT / "qualification.json"), "manifest_sha256": sha(OUT / "manifest.json")}, indent=2))

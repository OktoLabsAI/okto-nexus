"""Build a finite, blocked v10 proposal in this new Temp directory; no product calls."""
from pathlib import Path
import ast
import copy
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "draft"
OLD = Path(r"C:/Users/jpamb/AppData/Local/Temp/m1-v9-preparation-t4xaqhca")
REPO = Path(r"D:/Projetos/Techridy/okto_labs_okto_nexus")
IDENTITY = Path(r"D:/Projetos/Techridy/okto-nexus-connector/src/okto_nexus_connector/platform/service_identity.py")
PORT = 56237  # Proposed only: no socket bind, availability or reservation claim.
EXPECTED = {
    OLD / "draft/m1-codex-campaign-proposal-v9-lf.json": "099215c658e4b16cfb69456ea1ad9a21875b45a090c439a6504b05912491d204",
    REPO / "plans/agent_ops/evidence/r3-m1-v9-execution/public/closure.json": "fd568cf79300b85fc9f9ad4944869dae7fa2bd54845a109e0e79915d610f8936",
    REPO / "plans/agent_ops/evidence/r3-m1-v9-execution/checkpoint/controller.json": "02d025ef1d09d8158573f553f58813e96b810d992110007c05971ba1cc44e588",
    IDENTITY: "f61f0d437fa6b0b2ffce1cb7d76e256ae096c21cb9ee28661f3bf85b06ce25d5",
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(name, value):
    data = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    with (OUT / name).open("xb") as stream:
        stream.write(data)


def rebase(value):
    if isinstance(value, dict):
        return {k: rebase(v) for k, v in value.items()}
    if isinstance(value, list):
        return [rebase(v) for v in value]
    if isinstance(value, str):
        return (value.replace(str(OLD), str(ROOT)).replace(OLD.as_posix(), ROOT.as_posix())
                .replace("m1v9-", "m1v10-").replace("m1_v9_", "m1_v10_")
                .replace("http://127.0.0.1:54913", f"http://127.0.0.1:{PORT}")
                .replace("54913", str(PORT)))
    return value


def task_names(paths, principal):
    home = os.path.normcase(str(Path(paths["server_home"]).resolve()))
    database = os.path.normcase(str((Path(paths["server_home"]) / "nexus.db").resolve()))
    state = os.path.normcase(str(Path(paths["connector_state"]).resolve()))
    server = sha(json.dumps(["server", home, database, principal[4:]], ensure_ascii=False, separators=(",", ":")).encode())
    connector = sha(json.dumps(["connector", state, principal], separators=(",", ":")).encode())
    return {key: {"name": prefix + digest, "instance_id": "svc_" + digest,
                  "exists": None, "absence_observed": False}
            for key, prefix, digest in (("nexus", "OktoNexus-server-", server),
                                        ("connector", "OktoNexus-connector-", connector))}


def main():
    if OUT.exists() or (ROOT / "campaign").exists():
        raise RuntimeError("FRESH_OUTPUT_REQUIRED")
    for path, expected in EXPECTED.items():
        if sha(path.read_bytes()) != expected:
            raise RuntimeError("INPUT_CHANGED:" + path.name)
    old = load(OLD / "draft/m1-codex-campaign-proposal-v9-lf.json")
    closure = load(REPO / "plans/agent_ops/evidence/r3-m1-v9-execution/public/closure.json")
    assert closure["cumulative_reserved_admissions"] == 5
    assert closure["carry_in_minimum_observed_tokens"] == 67658
    assert closure["new_confirmed_productive_admissions"] == 1
    assert closure["billing_final"] is False and closure["replay_allowed"] is False
    # Only the existing public identity helper is evaluated; no product import.
    node = next(n for n in ast.parse(IDENTITY.read_text(encoding="utf-8")).body
                if isinstance(n, ast.FunctionDef) and n.name == "effective_principal")
    namespace = {"ctypes": ctypes, "wintypes": wintypes, "os": os}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(IDENTITY), "exec"), namespace)
    principal = namespace["effective_principal"]()
    if not principal.startswith("sid:"):
        raise RuntimeError("WINDOWS_PRINCIPAL_REQUIRED")
    old_tasks = task_names(old["paths"], principal)
    for name in old_tasks:
        assert old_tasks[name]["name"] == old["topology"]["task_names"][name]["name"]
    paths = rebase(old["paths"])
    tasks = task_names(paths, principal)
    assert all(tasks[k]["name"] != old_tasks[k]["name"] for k in tasks)
    policy = {"revision": 10, "carry_in_admissions": 5, "carry_in_tokens": 67658,
              "max_cumulative_admissions": 11, "max_new_admissions": 6,
              "preventive_cumulative_tokens": 200000, "operational_tolerance": 700000,
              "deadline_seconds": 120}
    ancestry = {"closure_sha256": EXPECTED[REPO / "plans/agent_ops/evidence/r3-m1-v9-execution/public/closure.json"],
                "checkpoint_sha256": EXPECTED[REPO / "plans/agent_ops/evidence/r3-m1-v9-execution/checkpoint/controller.json"],
                "predecessor_faults": closure["faults_preserved"],
                "prior_ancestry": copy.deepcopy(old["controller_preparation"]["ancestry"])}
    counting = {"conservative_carry_in_reservations": 5, "historical_confirmed_productive": 3,
                "v8_reserved_without_confirmed_productive": 1,
                "v9_work_reserved_with_canonical_no_native_admission": 1,
                "new_reservations_maximum": 6, "cumulative_reservations_maximum": 11,
                "maximum_confirmed_productive_if_all_new_confirm": 9,
                "observed_token_minimum_carry_in": 67658, "v9_new_observed_tokens": 21815,
                "billing_final": False, "unused_slots_reassignable": False}
    semantics = ("Five reservations are retained, not five inferences: three productive admissions confirmed; "
                 "v8 retains one unconfirmed reservation and v9 useful work one reservation despite canonical "
                 "no-native-admission evidence. No reservation is refunded. Six proposed new reservations "
                 "yield at most eleven cumulative reservations, not a promise of eleven inferences.")
    blockers = ["Corrected Nexus wheel and complete installed qualification pending; no new wheel pin selected.",
                "New observation composition and its controller integration/qualification pending.",
                "Revision-10 controller policy/ancestry and all entry guards not composed or qualified.",
                "Fresh dependency-only environment and manifest-derived payload set not prepared.",
                "Final artifact snapshot/hash and exact new user authorization receipt absent.",
                "Pre-effect task absence, port availability, fresh homes and owner checks not performed."]
    commands = rebase(load(OLD / "draft/proposed-commands.json"))
    commands.update(status="SKELETON_ONLY_NOT_AUTHORIZED_NOT_EXECUTED", tasks=tasks,
                    package_pin_status="PENDING_NEW_NEXUS_AND_OBSERVER_QUALIFICATION", execution_authorized=False)
    for step in commands["steps"]:
        step["task_name"] = tasks[step["component"]]["name"]
    commands["counts"].update(provider_cumulative_admissions_max=11, conservative_cumulative_reservations_max=11,
                              historical_confirmed_productive=3, prior_unconfirmed_reserved=1,
                              prior_reserved_with_no_native_admission=1, maximum_confirmed_productive_if_all_new_confirm=9)
    commands["execution_blocked"] = True
    commands["baseline_preflight"] = None
    commands["port_availability_observed"] = False
    planning = rebase(load(OLD / "draft/planning-commands.json"))
    planning.update(status="REFERENCE_COMMANDS_ONLY_NO_RUNNER_COMPOSED", execution_authorized=False,
                    execution_blocked=True, commands_executed=0)
    selected = ("format", "paths", "native_selection", "provider_context", "finite_work", "steps", "request_ids",
                "operator_bootstrap", "fixed_plan_map", "evidence_policy", "excluded", "base06_measurement", "dx43_observation")
    proposal = {key: rebase(old[key]) for key in selected}
    proposal.update(revision=10, status="OFFLINE_SKELETON_INCOMPLETE_NOT_QUALIFIED_NOT_AUTHORIZED",
                    prepared_at_utc=datetime.now(timezone.utc).isoformat(), execution_authorized=False,
                    qualification_status="PENDING", final_proposal=False, blocking_preconditions=blockers,
                    authorization={"execution_authorized": False, "provider_use_authorized_for_successor": False,
                                   "service_actions_authorized_for_successor": False, "installation_authorized": False,
                                   "approval_receipt_created": False, "direct_user_approval_received": False,
                                   "scope": "Preparation only. Prior v7/v8/v9 approvals do not authorize this successor."},
                    counting=counting, controller_preparation={"status": "PENDING_COMPOSITION_AND_QUALIFICATION",
                                   "policy": policy, "ancestry": ancestry, "execution_blocked": True,
                                   "approval_receipt_created": False, "controller_sha256": None,
                                   "observer_sha256": None},
                    topology={"origin": commands["origin"], "task_names": tasks, "user_tasks": 2,
                              "port_availability_observed": False, "service_commands": "proposed-commands.json",
                              "implicit_scheduler_start_maximum": 1, "explicit_lifecycle_commands": 8,
                              "network": old["topology"]["network"],
                              "fresh_home_reason": "Preserve all v9 and earlier faults/receipts; never reset or replay old roots."})
    proposal["finite_work"].update(maximum_cumulative_admissions=11,
                                   maximum_confirmed_productive_including_history=9, counter_semantics=semantics)
    proposal["steps"][0]["gate"] = "Corrected Nexus diagnostic wheel plus unchanged selected Core/Connector pins, new observer and controller composed and qualified before final freeze."
    proposal["token_accounting"] = {"observed_tokens_carry_in": 67658, "admissions_carry_in": 5,
        "new_admissions_maximum": 6, "cumulative_admissions_maximum": 11,
        "proposed_preventive_threshold": 200000, "proposed_remaining_observed_headroom": 132342,
        "total_tolerance": 700000, "serial_turn_deadline_seconds": 120,
        "limits_proposed_not_approved": True, "hard_cap_supported": False, "billing_final": False,
        "counter_semantics": semantics,
        "required_invariants": ["Reserve durably before each setup/work/continuation; serial effects only.",
            "Keep the exact predecessor closure/checkpoint and nested ancestry immutable.",
            "Carry 67658 minimum observed tokens once; unknown observation is not zero or final billing.",
            "Monitor setup and work without replacing endpoint diagnostics or inferring all([]) completion.",
            "Unknown coverage or stop confirmation blocks new admissions; no automatic replay or fault reset.",
            "At 200000 observed cumulative tokens select canonical interruption/close/normal owned stop; no force.",
            "The observation component must define bounded calls and preserve first sanitized error; pending qualification."],
        "remote_setup_source": old["token_accounting"]["remote_setup_source"]}
    prefix = OUT / "installation/venv"
    packages = {}
    for name in ("okto_nexus", "okto_nexus_connector", "nexus_connector_core"):
        prev = old["package_pins"]["packages"][name]
        packages[name] = {"wheel": None if name == "okto_nexus" else prev["wheel"],
                          "sha256": None if name == "okto_nexus" else prev["sha256"],
                          "status": "PENDING_DIAGNOSTIC_FIX_WHEEL" if name == "okto_nexus" else "UNCHANGED_PREDECESSOR_PIN_REFERENCE",
                          "manifest_payload_count": None, "installed_in_target": False}
    proposal["package_pins"] = {"status": "PENDING_FINAL_WHEELS_AND_MANIFEST", "packages": packages,
        "python_prefix": str(prefix), "python": str(prefix / "Scripts/python.exe"), "files": [],
        "expected_product_payload_count": None, "expected_total_pin_count": None,
        "count_rule": "Derive exact raw-byte payload set from final wheel manifests and compare source/wheel/install; add verified interpreter pins separately. Never retain v9 counts as a v10 acceptance constant."}
    proposal["base06_installation"] = {"status": "OPTIONAL_SINGLE_OFFLINE_INSTALL_NOT_PREPARED",
        "selected": None, "maximum_install_attempts_after_reservation": 1, "installer_enabled": False,
        "python": str(prefix / "Scripts/python.exe"), "python_prefix": str(prefix),
        "products_installed": False, "dependencies_prepared": False, "expected_payload_count": None,
        "requirements": str(OUT / "installation/products-requirements.txt"), "requirements_sha256": None,
        "requirements_encoding": "UTF-8 without BOM; LF bytes via exclusive binary write; hash the actual bytes",
        "script": None, "script_sha256": None, "result": str(OUT / "installation/installation-result.json"),
        "reservation": str(OUT / "installation/installation-reserved.json"),
        "requirements_renderer": "../requirements_lf.py", "effects_executed": 0,
        "guard": "Actual installer remains absent. Validate final proposal and approval before reservation; any reserved/unknown result forbids replay. No pip, environment creation or install in this preparation."}
    proposal["execution_bundle"] = {"status": "NOT_COMPOSED", "entry_gate": "../execution_gate.py",
        "all_entry_points_blocked": True, "unconditional_error": "V10_SKELETON_NOT_EXECUTABLE",
        "requires_root_composition": True, "lifecycle_runner": None, "setup_runner": None,
        "work_runner": None, "observer": None, "approval_path": None}
    proposal["predecessor"] = {"closure": str(REPO / "plans/agent_ops/evidence/r3-m1-v9-execution/public/closure.json"),
        "closure_sha256": ancestry["closure_sha256"], "checkpoint_sha256": ancestry["checkpoint_sha256"],
        "original_approved_v9_proposal_sha256": "9a7004d1670076fd516311932bb894fbd55e47e2625fb6b3dfd89dc66caed279",
        "executed_derived_v9_proposal_sha256": EXPECTED[OLD / "draft/m1-codex-campaign-proposal-v9-lf.json"],
        "historical_evidence_unchanged": True, "new_execution_authority_inherited": False}
    proposal["acceptance"] = {"promoted": False, "m1_complete": False, "base06_measured": False,
        "scope": "Finite preparation only. No installation, service, account or provider effect."}
    references = []
    for name, path, expected in [
        ("publication", OLD / "draft/publication.py", "e1b604a40dda2742e8a9029cd523b37ea68ea4c39135df5b51792ae337264385"),
        ("response_loss", OLD / "draft/response_loss.py", "90384048f66c4eded5c119d7380debf22a288ff3c03270d01714b685326b8d56"),
        ("supervisor_check", OLD / "draft/supervisor_check.py", "c1becafab3a870d0f1fd5f6701e00f5d92f70827e6b7968bc12269f0ab7a87c3"),
        ("protected_pty", Path(r"C:/Users/jpamb/AppData/Local/Temp/m1-protected-pty-j_c21e97/revision-5/protected_pty.py"), "3e9819f37d7bd04a55dc094f3e05d62f13eb8fcbf0b404abf3f2f1e9279291b1"),
        ("owned_job", Path(r"C:/Users/jpamb/AppData/Local/Temp/m1-protected-pty-j_c21e97/revision-5/owned_job.py"), "1b6923d36a9ec047bc67b66d898eac017cd9f7930969e8f894330d0eca56570c")]:
        if sha(path.read_bytes()) != expected:
            raise RuntimeError("HELPER_CHANGED:" + name)
        references.append({"name": name, "path": str(path), "sha256": expected,
                           "qualification": "Historical unchanged bytes only; no v10 execution/integration claim."})
    OUT.mkdir()
    write("m1-codex-campaign-proposal-v10-draft.json", proposal)
    write("proposed-commands.json", commands)
    write("planning-commands.json", planning)
    write("unchanged-helper-references.json", references)
    write("identity-preparation.json", {"status": "DERIVED_ONLY_NOT_PREFLIGHT", "source": str(IDENTITY),
        "source_sha256": EXPECTED[IDENTITY], "principal_sha256": sha(principal.encode()),
        "prior_v9_names_reproduced": True, "new_names_distinct": True, "tasks": tasks,
        "process_sid_only": True, "scheduler_queries": 0, "scheduler_mutations": 0,
        "port_checks": 0, "child_processes": 0, "campaign_directory_created": False})
    source_paths = list(EXPECTED) + [OLD / "build_preparation.py", OLD / "bind_candidate.py",
                    OLD / "draft/proposed-commands.json", OLD / "draft/planning-commands.json"]
    write("source-map.json", [{"path": str(p), "sha256": sha(p.read_bytes()), "bytes": p.stat().st_size} for p in source_paths])
    write("scope-delta.json", {"from_revision": 9, "to_revision": 10,
        "changed": {"carry_in_reservations": [3, 5], "minimum_observed_tokens": [45843, 67658],
                    "cumulative_reservation_limit": [9, 11], "confirmed_historical_productive": [2, 3],
                    "homes_task_ids_port": "Fresh; derived only, not probed", "Nexus": "Pending corrected diagnostic wheel",
                    "observation": "Pending new qualified composition", "requirements": "Explicit LF bytes; final pins absent"},
        "unchanged": {"new_reservations_maximum": 6, "preventive_tokens": 200000, "tolerance": 700000,
                      "deadline_seconds": 120, "user_tasks": 2, "explicit_lifecycle_commands": 8,
                      "implicit_connector_start_maximum": 1, "force": False, "old_replay": False,
                      "native_build": "0.157.0 exact predecessor reference", "finite_work": "Same two-lane task/continuation/one actual command decision per lane"},
        "scope_expansion": False, "authorization_inferred": False, "finalization_blockers": blockers})
    write("approval-requirements.json", {"is_receipt": False, "execution_authorized": False,
        "purpose": "Requirements only; not an approval template with a purported user quote.",
        "required_after_final_freeze": ["actual user authorization of final v10 scope", "exact proposal SHA256",
            "receipt SHA256", "proposal_revision=10", "exact policy", "exact nested ancestry",
            "exact fresh campaign_root", "actual nonempty user_quote", "qualified package and entrypoint hashes"],
        "no_receipt_created": True, "entry_guard_remains_unconditionally_blocked": True})
    print(json.dumps({"status": "OFFLINE_SKELETON_CREATED", "root": str(ROOT),
                      "proposal_sha256": sha((OUT / "m1-codex-campaign-proposal-v10-draft.json").read_bytes()),
                      "campaign_directory_exists": (ROOT / "campaign").exists()}))


if __name__ == "__main__":
    main()

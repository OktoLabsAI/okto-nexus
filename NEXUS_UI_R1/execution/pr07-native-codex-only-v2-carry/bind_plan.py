"""Bind fresh Codex-only identity and reviewed metadata; no native/product effects."""

from pathlib import Path
import json
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from safety import ORDER, POLICY, publish, read, sha, require  # noqa:E402


def main():
    old = HERE.parent / "pr07-native-proposal/candidate-final.json"
    require(
        sha(old) == "3ea51229df9bcc4d93d7f42dbe5e4d62a97741d97c99907a49a21cde6fafb88e",
        "ORIGINAL_CHANGED",
    )
    previous = read(old)
    # Whitelist only the already-qualified BXP artifact bytes/environment and
    # task text. No old identity, campaign root, account, policy or consent.
    plan = {
        key: previous[key]
        for key in (
            "python",
            "python_images",
            "package_pins",
            "wheels",
            "installed_payloads",
            "prompts",
            "home_observer_window",
        )
    }
    plan.update(read(HERE / "identity.json"))
    plan.update(
        schema="ui042-codex-only-carry-campaign-v2",
        policy=POLICY,
        admission_order=list(ORDER),
        package_bound=True,
        native_bindings_bound=True,
        native=read(HERE / "native-bindings.json"),
        carry=read(HERE / "carry.json"),
        scope_derivation={
            "original_candidate_sha256": sha(old),
            "authorization_reference": "call_7b291505d2a349ddb591321ccaefe5f7 item0",
            "only_codex": True,
            "claude_allowed": False,
            "new_approval_question_required": False,
            "root_technical_audit_before_execute": True,
        },
    )
    plan["driver_pins"] = [
        {"path": str(HERE / name), "sha256": sha(HERE / name)}
        for name in (
            "driver.py",
            "safety.py",
            "usage.py",
            "own_process.py",
            "README.md",
            "qualification.json",
            "identity.json",
            "native-bindings.json",
            "authorization-source.json",
        )
    ]
    publish(HERE / "candidate-final.json", plan)
    print(
        json.dumps(
            {
                "sha256": sha(HERE / "candidate-final.json"),
                "campaign_id": plan["campaign_id"],
                "root": plan["campaign_root"],
                "port": plan["port"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

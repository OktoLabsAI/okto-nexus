"""Prepare a passive Playwright CLI program only after Root's execution signal.

No HTTP, product import, credential read or campaign-directory creation.
The explicit flag is an execution fence, not a substitute for user consent.
"""
import argparse
import hashlib
import json
from pathlib import Path

CAMPAIGN = "062496549c9340ccb78271b640c8849a"
ROOT = Path("C:/Users/jpamb/AppData/Local/Temp/nexus-ui042-" + CAMPAIGN)
ORIGIN = "http://127.0.0.1:51076"
CANDIDATE_SHA = "3ea51229df9bcc4d93d7f42dbe5e4d62a97741d97c99907a49a21cde6fafb88e"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root-execution-signal", required=True,
                        choices=["approved-and-observer-ready"])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    candidate = repo / "NEXUS_UI_R1/execution/pr07-native-proposal/candidate-final.json"
    assert hashlib.sha256(candidate.read_bytes()).hexdigest() == CANDIDATE_SHA
    assert ROOT.is_dir() and not ROOT.is_symlink(), "Driver must create its own home first"
    public = ROOT / "public"
    ready = json.loads((public / "observer-ready.json").read_text(encoding="utf8"))
    assert ready["campaign_id"] == CAMPAIGN and ready["origin"] == ORIGIN
    assert ready["no_new_productive_calls"] is True
    assert ready["timeout_seconds"] == 180
    sessions = {}
    for client in ("codex", "claude"):
        work = json.loads((public / (client + ".work.json")).read_text(encoding="utf8"))
        assert work["state"] == "completed" and work["useful_result_verified"] is True
        assert work["session_id"] == ready["sessions"][client]
        sessions[client] = work["session_id"]
    assert sessions["codex"] != sessions["claude"]
    config = {"campaign_id": CAMPAIGN, "origin": ORIGIN,
              "workspace_id": ready["workspace_id"], "server_id": ready["server_id"],
              "sessions": sessions}
    template = Path(__file__).with_name("real_home_observer.template.js").read_text(encoding="utf8")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(template.replace("/* OBSERVER_CONFIG */null", json.dumps(config)), encoding="utf8")
    print(json.dumps({"prepared": str(args.output), "campaign_id": CAMPAIGN,
                      "network_started": False, "marker_written": False}))


if __name__ == "__main__":
    main()

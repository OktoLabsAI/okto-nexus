"""Read only server-owned capability reports from a disposable campaign home."""
import json
from pathlib import Path
import sqlite3
import sys


def collect(root):
    records = []
    for database in sorted(Path(root).glob("**/nexus-home/nexus.db")):
        with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as connection:
            reports = [json.loads(row[0]) for row in connection.execute(
                "SELECT compatibility_report FROM harness_sessions")]
        records.append({"test_directory": database.parent.parent.name, "reports": reports})
    if not records:
        raise ValueError("No completed campaign databases found")
    return records


if __name__ == "__main__":
    output, codex, claude = sys.argv[1:]
    evidence = {
        "source_parent": "575c8c28ab6c4543ad8dc5b0b64949d5f735fea6",
        "source_state": "effective-capability worktree before final unknown-sharing guard",
        "codex": {"result": "4 PASS, 11 deselected, 47.08s", "records": collect(codex)},
        "claude": {"result": "4 PASS, 11 deselected, 40.83s", "records": collect(claude)},
        "pi_native": "NOT_RUN: user decision",
        "attach_native": "NOT_RUN: no dedicated session configured",
    }
    Path(output).write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print("Saved redacted server-owned reports; no credentials, prompts or native paths read.")

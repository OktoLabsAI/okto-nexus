"""PostToolUse hook: lint-fix + format the edited Python file with ruff.

Reads the Claude Code hook payload from stdin, extracts the edited file path,
and — only for existing .py files — runs `ruff check --fix` then `ruff format`
on that single file. Always exits 0 so it never blocks an edit; jq is not
available on this host, so parsing is done in Python (which the project uses
anyway). No project ruff config exists, so this relies on ruff defaults.
"""

import json
import os
import subprocess
import sys


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return  # malformed / empty stdin — do nothing

    tool_response = payload.get("tool_response") or {}
    tool_input = payload.get("tool_input") or {}
    file_path = tool_response.get("filePath") or tool_input.get("file_path")

    if not file_path or not file_path.endswith(".py") or not os.path.isfile(file_path):
        return

    for args in (["ruff", "check", "--fix", file_path], ["ruff", "format", file_path]):
        try:
            subprocess.run(args, capture_output=True)
        except FileNotFoundError:
            return  # ruff not installed — skip silently


if __name__ == "__main__":
    main()
    sys.exit(0)

"""Collect actual pytest node IDs without running tests or claiming acceptance."""

from __future__ import annotations

import importlib.metadata
import json
import platform
import sys
from pathlib import Path

import pytest


class Collection:
    def __init__(self) -> None:
        self.nodes: list[str] = []
        self.errors: list[str] = []

    def pytest_collection_finish(self, session):
        self.nodes = sorted(item.nodeid for item in session.items)

    def pytest_collectreport(self, report):
        if report.failed:
            self.errors.append(str(report.longrepr))


def main() -> int:
    output = Path(sys.argv[1])
    # Match `python -m pytest` for repository-owned test helpers, without
    # inserting src/ or any sibling application's source into the import path.
    sys.path.insert(0, str(Path.cwd()))
    plugin = Collection()
    code = int(pytest.main(["tests", "--collect-only", "-q"], plugins=[plugin]))
    packages = {}
    for name in ("okto-nexus", "okto-nexus-connector", "nexus-connector-core"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    output.write_text(json.dumps({
        "python": sys.version, "platform": platform.platform(),
        "interpreter": sys.executable, "packages": packages,
        "exit_code": code, "nodes": plugin.nodes, "errors": plugin.errors,
        "test_execution": "NOT_RUN",
    }, indent=2) + "\n", encoding="utf-8")
    return code


if __name__ == "__main__":
    raise SystemExit(main())

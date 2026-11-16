"""Explicitly authorized TEST ONLY: real own Server, zero perform/model/native calls."""

from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import os
import socket
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
spec = importlib.util.spec_from_file_location(
    "ui042_lifecycle_test_driver", HERE / "driver.py"
)
driver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(driver)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(tempfile.mkdtemp(prefix="ui042-lifecycle-only-")).resolve()
    for name in (
        "home",
        "private",
        "public",
        "project",
        "empty-path",
        "codex-inert-root",
        "claude-inert-root",
        "profile",
        "profile/roaming",
        "profile/local",
    ):
        (root / name).mkdir(parents=True, exist_ok=True)
    # Modify only THIS short-lived test process's environment, never the user's
    # persisted environment or the paid candidate. No native executable exists
    # in its PATH or approved installation roots.
    env = driver.campaign_environment(os.environ)
    env.update(
        PATH=str(root / "empty-path"),
        HOME=str(root / "profile"),
        USERPROFILE=str(root / "profile"),
        APPDATA=str(root / "profile/roaming"),
        LOCALAPPDATA=str(root / "profile/local"),
    )
    os.environ.clear()
    os.environ.update(env)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    images = {
        str(Path(path).resolve()): hashlib.sha256(Path(path).read_bytes()).hexdigest()
        for path in {sys.executable, sys._base_executable}
    }
    plan = {
        "campaign_root": str(root),
        "port": port,
        "python_images": images,
        "native": {
            name: {"installation_root": str(root / (name + "-inert-root"))}
            for name in ("codex", "claude")
        },
    }

    class LifecycleOnly(driver.ProductPort):
        def perform(self, *args, **kwargs):
            raise AssertionError("NO_ADMISSIONS_IN_LIFECYCLE_TEST")

    adapter = LifecycleOnly(plan)
    report = {
        "test_only": True,
        "own_root": str(root),
        "started_at": datetime.now(timezone.utc).isoformat(),
        "native_invoked": False,
        "provider_called": False,
        "auth_or_provider_home_opened": False,
        "perform_calls": 0,
    }
    try:
        adapter.start()
        adapter.watched()
        report["owner"] = adapter.owner
        with sqlite3.connect(
            (root / "home/nexus.db").as_uri() + "?mode=ro", uri=True
        ) as db:
            db.execute("PRAGMA query_only=ON")
            report["canonical_counts"] = {
                table: db.execute("SELECT COUNT(*) FROM " + table).fetchone()[0]
                for table in (
                    "execution_operations",
                    "connection_setup_commits",
                    "runtime_execution_grants",
                )
            }
        assert all(value == 0 for value in report["canonical_counts"].values())
        assert not list((root / "home/connection-tests").glob("*/journal.db"))
        report["ready"] = True
    finally:
        try:
            report["cleanup"] = adapter.cleanup()
        except BaseException as error:
            report["cleanup"] = {
                "error_type": type(error).__name__,
                "reason": str(error),
                "settlement_confirmed": False,
            }
        report["ended_at"] = datetime.now(timezone.utc).isoformat()
        report["status"] = (
            "PASS"
            if report.get("ready") and report["cleanup"].get("settlement_confirmed")
            else "FAIL"
        )
        args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

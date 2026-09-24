"""Real resource lifetime regressions for the bounded pressure fixtures."""
import gc
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time

from test_runtime_relay_process_restart import Owner


def test_rows_closes_sqlite_without_relying_on_gc(tmp_path):
    owner = Owner.__new__(Owner)
    owner.home = tmp_path
    connection = sqlite3.connect(tmp_path / "nexus.db")
    connection.execute("CREATE TABLE example(value)")
    connection.close()
    gc.collect()
    gc.disable()
    try:
        assert owner.rows("SELECT * FROM example") == []
        # On Windows an open SQLite handle prevents this rename.
        (tmp_path / "nexus.db").rename(tmp_path / "closed.db")
    finally:
        gc.enable()
        gc.collect()


def test_load_worker_survives_snapshot_reader(tmp_path):
    import runpy
    source = runpy.run_path(str(Path(__file__).resolve().parents[1] /
        "plans/pr34-remediation/runtime_crash_pressure_campaign.py"))["LOAD"]
    script = tmp_path / "load.py"
    script.write_text(source, encoding="utf-8")
    snapshot = tmp_path / "load-0.json"
    (tmp_path / "active").touch()
    env = {k: v for k, v in os.environ.items() if k.upper() in {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP"}}
    env.update(HOME=str(tmp_path), USERPROFILE=str(tmp_path))
    with (tmp_path / "stderr").open("w") as log:
        process = subprocess.Popen([sys._base_executable, str(script), str(tmp_path), "load-0"],
            env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=log,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        try:
            deadline = time.monotonic() + 10
            while not snapshot.exists():
                assert process.poll() is None and time.monotonic() < deadline
                time.sleep(.02)
            before = json.loads(snapshot.read_text())
            with snapshot.open("rb"):
                time.sleep(.7)
                assert process.poll() is None, (tmp_path / "stderr").read_text()
            while json.loads(snapshot.read_text())["iterations"] <= before["iterations"]:
                assert process.poll() is None and time.monotonic() < deadline
                time.sleep(.02)
        finally:
            (tmp_path / "stop").touch()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        assert process.returncode == 0

import importlib.util
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

spec = importlib.util.spec_from_file_location(
    "live_http", Path(__file__).resolve().parents[1] / "scripts/live_client.py"
)
live = importlib.util.module_from_spec(spec)
spec.loader.exec_module(live)


def test_own_environment_has_no_personal_credentials_or_provider_paths(
    tmp_path, monkeypatch
):
    for key in (
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "CLAUDE_CONFIG_DIR",
        "CODEX_HOME",
        "OKTO_NEXUS_HOME",
        "NEXUS_CONNECTOR_TOKEN",
        "PYTHONPATH",
        "HTTPS_PROXY",
    ):
        monkeypatch.setenv(key, "personal-value")
    value = live.isolated_environment(tmp_path)
    assert "personal-value" not in value.values()
    for key in ("HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "PATH"):
        assert Path(value[key]).resolve().is_relative_to(tmp_path.resolve())
    command = live.serve_command(tmp_path / "home", tmp_path / "project", 43123)
    assert command[1:5] == ["-I", "-m", live.PKG_MODULE, "serve"]
    assert command[command.index("--host") + 1] == "127.0.0.1"
    assert command[command.index("--embedding-mode") + 1] == "off"
    assert "--no-browser" not in command


def test_canonical_envelope_parser_never_accepts_tool_error_or_non_envelope():
    assert live.envelope_of(
        SimpleNamespace(structuredContent={"ok": True, "data": {}}, isError=False)
    )["ok"]
    assert live.envelope_of(
        SimpleNamespace(
            content=[SimpleNamespace(text=json.dumps({"ok": True, "data": {}}))],
            isError=False,
        )
    )["ok"]
    with pytest.raises(RuntimeError):
        live.envelope_of(SimpleNamespace(structuredContent={"ok": True}, isError=True))
    with pytest.raises(RuntimeError):
        live.envelope_of(SimpleNamespace(content=[]))


def test_local_provisioning_releases_all_database_handles(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    home = tmp_path / "home"
    workspace, keys = live.bootstrap_agents(home, project)
    assert workspace and set(keys) == {"agent-alpha", "agent-beta"}
    # On Windows this refuses an open pooled SQLite handle, as the real
    # HTTP smoke's first cleanup attempt exposed.
    database = home / "nexus.db"
    moved = home / "closed.db"
    database.rename(moved)
    moved.unlink()
    keys.clear()


def test_cleanup_uses_only_canonical_owned_home_then_waits_physical_exit(
    tmp_path, monkeypatch
):
    calls = []

    class Process:
        def poll(self):
            return None

        def wait(self, timeout):
            calls.append(("wait", timeout))
            return 0

    def stop(command, **kwargs):
        calls.append(command)
        assert command[command.index("--home") + 1] == str(tmp_path / "home")
        assert command[command.index("--timeout") + 1] == "15"
        assert "--force" not in command
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(live.subprocess, "run", stop)
    assert live.stop_server(Process(), tmp_path / "home", {}, 43123)["physical_exit"]
    assert calls[0][4:6] == ["service", "stop"]
    assert calls[1] == ("wait", 10)


def test_unconfirmed_cleanup_does_not_erase_owner_or_kill_pid(tmp_path, monkeypatch):
    class Process:
        def poll(self):
            return None

        def wait(self, timeout):
            raise subprocess.TimeoutExpired("own", timeout)

    monkeypatch.setattr(
        live.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=1)
    )
    with pytest.raises(RuntimeError, match="state is preserved"):
        live.stop_server(Process(), tmp_path / "home", {}, 43123)


def test_recursive_cleanup_is_fenced_to_exact_allocated_temp_root(tmp_path):
    owned = tmp_path / "okto-live-http-mcp-owned"
    outside = tmp_path / "unrelated"
    owned.mkdir()
    outside.mkdir()
    sentinel = outside / "keep.txt"
    sentinel.write_bytes(b"unchanged")
    for target, snapshot, parent in (
        (outside, owned, tmp_path),
        (owned, outside, tmp_path),
        (owned, owned, outside),
        (tmp_path, tmp_path, tmp_path.parent),
    ):
        with pytest.raises(RuntimeError, match="out-of-scope"):
            live.remove_owned_root(target, snapshot.resolve(), parent.resolve())
        assert sentinel.read_bytes() == b"unchanged" and owned.is_dir()
    live.remove_owned_root(owned, owned.resolve(), tmp_path.resolve())
    assert not owned.exists() and sentinel.read_bytes() == b"unchanged"

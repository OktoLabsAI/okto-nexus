"""Transport tests use synthetic subprocesses, not a claimed live Herdr fixture."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time

import pytest

from okto_nexus.adapters.outbound.observation import herdr
from okto_nexus.domain.herdr_observations import HerdrObservationError


@pytest.fixture
def client(tmp_path):
    executable = tmp_path / "directory with spaces" / "herdr.exe"
    executable.parent.mkdir()
    executable.write_bytes(b"synthetic transport boundary; never executed")
    return herdr.HerdrCLI(executable, "qualified-test", environment={
        key: value for key, value in os.environ.items()
        if key.upper() in {"SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP"}
    })


def child(monkeypatch, body):
    """Run a real bounded child while recording the proposed Herdr argv/env."""
    original = subprocess.Popen
    calls = []

    def start(argv, **kwargs):
        process = original([sys.executable, "-I", "-c", body], **kwargs)
        calls.append((list(argv), kwargs, process))
        return process

    monkeypatch.setattr(herdr.subprocess, "Popen", start)
    return calls


def encode(value):
    return json.dumps(value, separators=(",", ":")).encode()


def live_status():
    return {
        "status": "running", "running": True, "version": "0.9.5", "protocol": 22,
        "session": "qualified-test", "compatible": True, "endpoint_compatible": True,
        "capabilities": {"live_handoff": False, "endpoint_protocol_generation": 1,
                         "surface_interest": True, "health_check": True},
        "socket": "PRIVATE_LOCAL_PATH", "extra": "PRIVATE_REMOTE_VALUE",
    }


def response(kind, request, **values):
    return encode({"id": request, "result": {"type": kind, **values}})


@pytest.mark.parametrize("changes", [
    {"executable": "relative.exe"}, {"session": ""},
    {"session": "../escape"}, {"session": "--remote"}, {"session": "a" * 65},
    {"timeout": True}, {"timeout": 0}, {"timeout": 31}, {"timeout": float("nan")},
    {"max_output": True}, {"max_output": 0}, {"max_output": 1024 * 1024 + 1},
])
def test_rejects_invalid_configuration_before_launch(client, changes):
    values = {"executable": client.executable, "session": client.session}
    values.update(changes)
    with pytest.raises(herdr.HerdrTransportError, match="HERDR_CONFIG_INVALID"):
        herdr.HerdrCLI(**values)


def test_argv_is_fixed_explicit_and_never_uses_shell(client, monkeypatch):
    calls = child(monkeypatch, "import sys; sys.stdout.buffer.write(b'herdr 0.9.5\\n')")
    assert client._run("version") == b"herdr 0.9.5\n"
    argv, options, process = calls[0]
    assert argv == [str(client.executable), "--session", "qualified-test", "--version"]
    assert options["shell"] is False
    assert options["stdin"] == subprocess.DEVNULL
    assert options["close_fds"] is True
    assert process.returncode == 0
    with pytest.raises(herdr.HerdrTransportError, match="HERDR_COMMAND_INVALID"):
        client._run("server")
    assert len(calls) == 1


def test_environment_never_forwards_credentials_or_routing(client, monkeypatch, tmp_path):
    dangerous = {
        "HERDR_SOCKET_PATH": "personal-socket", "HERDR_SESSION": "personal",
        "HERDR_MACHINE": "remote", "HERDR_PANE_ID": "w9:p9", "HERDR_ENV": "1",
        "HERDR_CONFIG_PATH": str(tmp_path / "inherited.toml"),
        "NEXUS_API_KEY": "private-key", "OPENAI_API_KEY": "provider-key",
        "NEXUS_OBSERVATION_TOKEN": "nxobs_private", "arbitrary": "private",
    }
    for name, value in dangerous.items():
        monkeypatch.setenv(name, value)
    observer = herdr.HerdrCLI(client.executable, client.session)
    calls = child(monkeypatch, "print('ok')")
    observer._run("version")
    environment = calls[0][1]["env"]
    assert not (set(environment) & set(dangerous))
    assert environment["NO_COLOR"] == "1"
    assert "private" not in json.dumps(environment)
    explicit = dict(observer._environment, **dangerous)
    isolated_config = str(tmp_path / "isolated.toml")
    explicit["HERDR_CONFIG_PATH"] = isolated_config
    observer = herdr.HerdrCLI(client.executable, client.session, environment=explicit)
    observer._run("version")
    assert calls[1][1]["env"]["HERDR_CONFIG_PATH"] == isolated_config
    assert not (set(calls[1][1]["env"]) & (set(dangerous) - {"HERDR_CONFIG_PATH"}))


def test_credential_cannot_be_smuggled_through_an_allowed_environment_key(client):
    with pytest.raises(herdr.HerdrTransportError, match="HERDR_CONFIG_INVALID"):
        herdr.HerdrCLI(client.executable, client.session, environment={"LANG": "nxobs_private"})


def test_combined_stdout_stderr_limit_stops_only_owned_child(client, monkeypatch):
    client.max_output = 100
    calls = child(monkeypatch,
        "import sys,time; sys.stdout.buffer.write(b'x'*60); sys.stdout.flush(); "
        "sys.stderr.buffer.write(b'y'*60); sys.stderr.flush(); time.sleep(30)")
    started = time.monotonic()
    with pytest.raises(herdr.HerdrTransportError, match="HERDR_OUTPUT_LIMIT"):
        client._run("version")
    assert time.monotonic() - started < 3
    assert len(calls) == 1
    assert calls[0][2].poll() is not None


def test_timeout_covers_incomplete_output_and_reaps_owned_child(client, monkeypatch):
    client.timeout = 0.15
    calls = child(monkeypatch,
        "import sys,time; sys.stdout.buffer.write(b'{'); sys.stdout.flush(); time.sleep(30)")
    started = time.monotonic()
    with pytest.raises(herdr.HerdrTransportError, match="HERDR_TIMEOUT") as caught:
        client._run("version")
    assert caught.value.requires_reassociation is False
    assert time.monotonic() - started < 3
    assert calls[0][2].poll() is not None


def test_failure_does_not_disclose_stdout_stderr_or_command(client, monkeypatch, capsys):
    child(monkeypatch,
        "import sys; print('SECRET_STDOUT'); print('SECRET_STDERR', file=sys.stderr); sys.exit(7)")
    with pytest.raises(herdr.HerdrTransportError) as caught:
        client._run("version")
    assert str(caught.value) == "Herdr observation unavailable: HERDR_COMMAND_FAILED"
    assert caught.value.requires_reassociation is False
    assert "SECRET" not in repr(caught.value)
    assert str(client.executable) not in repr(caught.value)
    assert capsys.readouterr() == ("", "")


@pytest.mark.parametrize("raw", [
    b'{"running":true,"running":false}', b'{"value":NaN}', b'{"value":Infinity}',
    b'{"value":-Infinity}', b'[]', b'{} {}', b'\xff', b'{',
])
def test_strict_json_rejects_duplicate_keys_nonfinite_and_invalid_encoding(client, monkeypatch, raw):
    monkeypatch.setattr(client, "_run", lambda *args: raw)
    with pytest.raises(herdr.HerdrTransportError, match="HERDR_RESPONSE_INVALID"):
        client.status()


def test_contract_pins_raw_schema_bytes_and_version(client, monkeypatch):
    assert herdr.QUALIFIED_SCHEMA_SHA256 == (
        "9e2af207e9aa8183d4aeca5fde9cc48e7909bb40cdbd7cf21608a6d3ea78075b")
    # A deliberately synthetic JSON document exercises pinning, not acceptance
    # evidence for Herdr. The real release/schema is qualified separately.
    schema = encode({"protocol": 22, "schema_version": 1})
    digest = hashlib.sha256(schema).hexdigest()
    monkeypatch.setattr(herdr, "QUALIFIED_SCHEMA_SHA256", digest)
    monkeypatch.setattr(client, "_run", lambda cmd: b"herdr 0.9.5\n" if cmd == "version" else schema)
    assert client.contract() == {"version": "0.9.5", "protocol": 22,
                                 "schema_version": 1, "schema_sha256": digest}
    monkeypatch.setattr(client, "_run", lambda cmd: b"herdr 0.9.5\n" if cmd == "version" else schema + b" ")
    with pytest.raises(herdr.HerdrTransportError, match="HERDR_CONTRACT_UNSUPPORTED"):
        client.contract()
    monkeypatch.setattr(client, "_run", lambda cmd: b"herdr 0.9.6\n")
    with pytest.raises(herdr.HerdrTransportError, match="HERDR_CONTRACT_UNSUPPORTED"):
        client.contract()


def test_live_status_is_current_explicit_and_sanitized(client, monkeypatch):
    raw = live_status()
    monkeypatch.setattr(client, "_run", lambda cmd: encode(raw))
    value = client.status()
    assert value == {key: raw[key] for key in ("running", "version", "protocol", "session", "capabilities")}
    assert "PRIVATE" not in json.dumps(value)
    raw["running"] = False
    with pytest.raises(herdr.HerdrTransportError, match="HERDR_SERVER_UNAVAILABLE"):
        client.status()


@pytest.mark.parametrize("changes", [
    {"running": 1}, {"session": "another"}, {"compatible": False},
    {"endpoint_compatible": False}, {"endpoint_compatible": None}, {"endpoint_compatible": 1},
    {"version": "0.9.6"}, {"protocol": 21}, {"protocol": True},
    {"capabilities": {"live_handoff": "yes"}},
    {"capabilities": {"endpoint_protocol_generation": True}},
])
def test_live_status_rejects_unknown_contract_and_selector(client, monkeypatch, changes):
    raw = dict(live_status(), **changes)
    monkeypatch.setattr(client, "_run", lambda cmd: encode(raw))
    with pytest.raises((HerdrObservationError, herdr.HerdrTransportError)):
        client.status()


def test_snapshot_sanitizes_nested_domain_boundary(client, monkeypatch):
    snapshot = {"version": "0.9.5", "protocol": 22, "agents": [], "panes": [],
                "workspaces": [{"title": "PRIVATE"}], "tabs": [], "layouts": [],
                "unknown": "PRIVATE"}
    monkeypatch.setattr(client, "_run", lambda cmd: response(
        "session_snapshot", "cli:api:snapshot", snapshot=snapshot))
    assert client.snapshot() == {"version": "0.9.5", "protocol": 22, "agents": [], "panes": []}


@pytest.mark.parametrize("payload", [
    {"id": "wrong", "result": {"type": "session_snapshot", "snapshot": {}}},
    {"id": "cli:api:snapshot", "error": {"message": "PRIVATE"}},
    {"id": "cli:api:snapshot", "result": {"type": "pane_read", "text": "PRIVATE"}},
])
def test_snapshot_rejects_wrong_envelope_without_disclosing_payload(client, monkeypatch, payload):
    monkeypatch.setattr(client, "_run", lambda cmd: encode(payload))
    with pytest.raises(herdr.HerdrTransportError, match="HERDR_RESPONSE_INVALID") as caught:
        client.snapshot()
    assert "PRIVATE" not in repr(caught.value)


def test_process_info_checks_live_release_and_discards_free_text(client, monkeypatch):
    calls = []
    info = {"pane_id": "w1:p2", "shell_pid": 101, "foreground_process_group_id": 202,
            "foreground_processes": [{"pid": 202, "name": "PRIVATE", "argv": ["PRIVATE"],
                                      "cmdline": "PRIVATE", "cwd": "PRIVATE"}], "tty": "PRIVATE"}

    def run(command, *args):
        calls.append((command, args))
        if command == "status":
            return encode(live_status())
        return response("pane_process_info", "cli:pane:process_info", process_info=info)

    monkeypatch.setattr(client, "_run", run)
    assert client.process_info("w1:p2") == {
        "pane_id": "w1:p2", "shell_pid": 101, "foreground_process_group_id": 202,
        "foreground_processes": [{"pid": 202}],
    }
    assert calls == [("status", ()), ("process_info", ("w1:p2",))]
    info["pane_id"] = "w9:p2"
    with pytest.raises(herdr.HerdrTransportError, match="HERDR_TARGET_CHANGED"):
        client.process_info("w1:p2")


def test_moved_pane_alias_requires_reassociation(client, monkeypatch):
    """A live process at a new canonical pane cannot retain the old binding."""
    calls = []

    def run(command, *args):
        calls.append((command, args))
        if command == "status":
            return encode(live_status())
        return response("pane_process_info", "cli:pane:process_info", process_info={
            "pane_id": "w2:p1", "shell_pid": 101, "foreground_process_group_id": 202,
            "foreground_processes": [{"pid": 202}],
        })

    monkeypatch.setattr(client, "_run", run)
    with pytest.raises(herdr.HerdrTransportError) as caught:
        client.process_info("w1:p1")
    assert caught.value.code == "HERDR_TARGET_CHANGED"
    assert caught.value.requires_reassociation is True
    assert calls == [("status", ()), ("process_info", ("w1:p1",))]


@pytest.mark.parametrize("pane", ["", "--current", "reviewer", "w1:p2 --remote host", "w1:pI", None])
def test_process_info_never_accepts_implicit_or_option_targets(client, monkeypatch, pane):
    def forbidden(*args):
        pytest.fail("invalid target reached child launch")
    monkeypatch.setattr(client, "_run", forbidden)
    with pytest.raises(herdr.HerdrTransportError, match="HERDR_TARGET_INVALID"):
        client.process_info(pane)


@pytest.mark.parametrize("pane", ["wA:pB", "w0:p0", "w11:pZ"])
def test_process_targets_accept_real_herdr_public_alphabet(client, monkeypatch, pane):
    def run(command, *args):
        if command == "status":
            return encode(live_status())
        assert args == (pane,)
        return response("pane_process_info", "cli:pane:process_info", process_info={
            "pane_id": pane, "shell_pid": 101, "foreground_process_group_id": 202,
            "foreground_processes": [{"pid": 202}],
        })
    monkeypatch.setattr(client, "_run", run)
    assert client.process_info(pane)["pane_id"] == pane


def test_default_session_requires_explicit_selection_and_null_runtime_name(client, monkeypatch):
    explicit = herdr.HerdrCLI(client.executable, "default", environment=client._environment)
    calls = child(monkeypatch, "print('ok')")
    explicit._run("version")
    assert calls[0][0][1:3] == ["--session", "default"]
    raw = dict(live_status(), session=None)
    monkeypatch.setattr(explicit, "_run", lambda cmd: encode(raw))
    assert explicit.status()["session"] == "default"
    monkeypatch.setattr(client, "_run", lambda cmd: encode(raw))
    with pytest.raises(herdr.HerdrTransportError, match="HERDR_RESPONSE_INVALID"):
        client.status()
    del raw["session"]
    with pytest.raises(herdr.HerdrTransportError, match="HERDR_RESPONSE_INVALID"):
        explicit.status()

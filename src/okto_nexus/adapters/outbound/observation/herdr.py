"""Bounded metadata-only CLI transport for the qualified Herdr 0.9.5 release.

This adapter never starts a Herdr server, attaches a terminal, reads terminal
contents, or changes an observed pane. Process metadata is reduced to IDs before
it leaves this boundary. A successful read is not proof of occupant continuity;
the caller must bracket observations with the independent process identity guard.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import threading
import time
from collections.abc import Mapping

from ....domain.herdr_observations import (
    HerdrObservationError,
    normalize_process_info,
    normalize_snapshot,
    validate_runtime,
)


QUALIFIED_VERSION = "0.9.5"
QUALIFIED_PROTOCOL = 22
QUALIFIED_SCHEMA_VERSION = 1
QUALIFIED_SCHEMA_SHA256 = "9e2af207e9aa8183d4aeca5fde9cc48e7909bb40cdbd7cf21608a6d3ea78075b"
MAX_OUTPUT_BYTES = 1024 * 1024
MAX_TIMEOUT_SECONDS = 30
_SESSION = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
# v0.9.5 uses this public base-32 alphabet, not decimal IDs. In particular
# w0/p0 are valid generated IDs after Z, and I/L/O/U are not digits.
_PANE = re.compile(r"w[123456789ABCDEFGHJKMNPQRSTVWXYZ0]{1,13}:p[123456789ABCDEFGHJKMNPQRSTVWXYZ0]{1,13}\Z")
_ENVIRONMENT_KEYS = frozenset({
    "PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "OS",
    "PROCESSOR_ARCHITECTURE", "NUMBER_OF_PROCESSORS", "TEMP", "TMP",
    "USERPROFILE", "APPDATA", "LOCALAPPDATA", "HOME", "XDG_CONFIG_HOME",
    "LANG", "LC_ALL",
})
_CAPABILITY_FLAGS = (
    "live_handoff", "detached_server_daemon", "surface_interest",
    "health_check", "ssh_agent_registration",
)


class HerdrTransportError(HerdrObservationError):
    """Only a fixed local code is exposed, never a child command or output."""

    @property
    def requires_reassociation(self) -> bool:
        # Herdr may resolve an old pane ID as an alias after a move. A different
        # canonical target contradicts the binding; an unavailable read does not.
        return self.code == "HERDR_TARGET_CHANGED"

def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _invalid_constant(_):
    raise ValueError


def _decode(content: bytes) -> dict:
    try:
        value = json.loads(content.decode("utf-8"), object_pairs_hook=_object,
                           parse_constant=_invalid_constant)
        if type(value) is not dict:
            raise ValueError
        return value
    except (ValueError, UnicodeError, RecursionError):
        raise HerdrTransportError("HERDR_RESPONSE_INVALID") from None


def _environment(explicit: Mapping[str, str] | None) -> dict[str, str]:
    source = os.environ if explicit is None else explicit
    if not isinstance(source, Mapping):
        raise HerdrTransportError("HERDR_CONFIG_INVALID")
    result = {}
    for name, value in source.items():
        if type(name) is not str or type(value) is not str:
            raise HerdrTransportError("HERDR_CONFIG_INVALID")
        upper = name.upper()
        if upper not in _ENVIRONMENT_KEYS:
            continue
        if "\0" in name or "\0" in value:
            raise HerdrTransportError("HERDR_CONFIG_INVALID")
        # These are filesystem/locale/system variables, never credential slots.
        # Reject accidental Nexus credentials even under an allowed key.
        if "nxobs_" in value or "nxs_" in value:
            raise HerdrTransportError("HERDR_CONFIG_INVALID")
        result[upper] = value
    if explicit is not None:
        config = explicit.get("HERDR_CONFIG_PATH")
        if config is not None:
            if (type(config) is not str or "\0" in config or not Path(config).is_absolute()
                    or "nxobs_" in config or "nxs_" in config):
                raise HerdrTransportError("HERDR_CONFIG_INVALID")
            result["HERDR_CONFIG_PATH"] = config
    result["NO_COLOR"] = "1"
    return result


class HerdrCLI:
    """Use one absolute executable and one explicit local session.

    ``max_output`` bounds stdout and stderr combined, before JSON decoding.
    No ambient HERDR routing, pane context, provider key or Nexus token is passed
    to children. An explicit environment may supply HERDR_CONFIG_PATH only.
    """

    def __init__(self, executable: str | Path, session: str, *,
                 environment: Mapping[str, str] | None = None,
                 timeout: float = 5, max_output: int = MAX_OUTPUT_BYTES):
        try:
            path = Path(executable)
            if (not path.is_absolute() or not path.is_file()
                    or type(session) is not str or not _SESSION.fullmatch(session)
                    or type(timeout) not in (int, float) or not math.isfinite(timeout)
                    or not 0 < timeout <= MAX_TIMEOUT_SECONDS
                    or type(max_output) is not int or not 0 < max_output <= MAX_OUTPUT_BYTES):
                raise ValueError
        except (ValueError, TypeError, OSError):
            raise HerdrTransportError("HERDR_CONFIG_INVALID") from None
        self.executable = path
        self.session = session
        self.timeout = float(timeout)
        self.max_output = max_output
        self._environment = _environment(environment)

    def contract(self) -> dict:
        version = self._run("version")
        if version.strip() != b"herdr 0.9.5":
            raise HerdrTransportError("HERDR_CONTRACT_UNSUPPORTED")
        schema_bytes = self._run("schema")
        digest = hashlib.sha256(schema_bytes).hexdigest()
        if digest != QUALIFIED_SCHEMA_SHA256:
            raise HerdrTransportError("HERDR_CONTRACT_UNSUPPORTED")
        schema = _decode(schema_bytes)
        if (type(schema.get("protocol")) is not int or schema["protocol"] != QUALIFIED_PROTOCOL
                or type(schema.get("schema_version")) is not int
                or schema["schema_version"] != QUALIFIED_SCHEMA_VERSION):
            raise HerdrTransportError("HERDR_CONTRACT_UNSUPPORTED")
        return {"version": QUALIFIED_VERSION, "protocol": QUALIFIED_PROTOCOL,
                "schema_version": QUALIFIED_SCHEMA_VERSION, "schema_sha256": digest}

    def status(self) -> dict:
        value = _decode(self._run("status"))
        if value.get("running") is False:
            raise HerdrTransportError("HERDR_SERVER_UNAVAILABLE")
        # Herdr represents its default session as JSON null. Accept that only
        # when the caller explicitly supplied --session default, never as a
        # fallback for a missing/mismatched named session.
        expected_session = None if self.session == "default" else self.session
        if (value.get("running") is not True or value.get("status") != "running"
                or value.get("compatible") is not True
                or value.get("endpoint_compatible") is not True
                or "session" not in value or value["session"] != expected_session):
            raise HerdrTransportError("HERDR_RESPONSE_INVALID")
        validate_runtime(value.get("version"), value.get("protocol"))
        caps = value.get("capabilities")
        if type(caps) is not dict:
            raise HerdrTransportError("HERDR_RESPONSE_INVALID")
        safe_caps = {}
        for name in _CAPABILITY_FLAGS:
            if name in caps:
                if type(caps[name]) is not bool:
                    raise HerdrTransportError("HERDR_RESPONSE_INVALID")
                safe_caps[name] = caps[name]
        generation = caps.get("endpoint_protocol_generation")
        if generation is not None:
            if type(generation) is not int or generation < 1:
                raise HerdrTransportError("HERDR_RESPONSE_INVALID")
            safe_caps["endpoint_protocol_generation"] = generation
        return {"running": True, "version": value["version"], "protocol": value["protocol"],
                "session": self.session, "capabilities": safe_caps}

    def snapshot(self) -> dict:
        result = self._response(self._run("snapshot"), "cli:api:snapshot", "session_snapshot")
        return normalize_snapshot(result.get("snapshot"))

    def process_info(self, pane_id: str) -> dict:
        if type(pane_id) is not str or not _PANE.fullmatch(pane_id):
            raise HerdrTransportError("HERDR_TARGET_INVALID")
        # This response has no version/protocol of its own. The CLI also pings
        # before its request; our status check additionally pins the release.
        self.status()
        result = self._response(self._run("process_info", pane_id),
                                "cli:pane:process_info", "pane_process_info")
        safe = normalize_process_info(result.get("process_info"))
        if safe["pane_id"] != pane_id:
            raise HerdrTransportError("HERDR_TARGET_CHANGED")
        return safe

    @staticmethod
    def _response(content: bytes, request_id: str, result_type: str) -> dict:
        value = _decode(content)
        if (value.get("id") != request_id or "error" in value
                or type(value.get("result")) is not dict
                or value["result"].get("type") != result_type):
            raise HerdrTransportError("HERDR_RESPONSE_INVALID")
        return value["result"]

    def _run(self, command: str, pane_id: str | None = None) -> bytes:
        commands = {
            "version": ("--version",),
            "schema": ("api", "schema", "--json"),
            "status": ("status", "server", "--json"),
            "snapshot": ("api", "snapshot"),
            "process_info": ("pane", "process-info", "--pane", pane_id),
        }
        if command not in commands or (command == "process_info" and (
                type(pane_id) is not str or not _PANE.fullmatch(pane_id))):
            raise HerdrTransportError("HERDR_COMMAND_INVALID")
        argv = [str(self.executable), "--session", self.session, *commands[command]]
        deadline = time.monotonic() + self.timeout
        try:
            process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, shell=False, cwd=self.executable.parent,
                env=dict(self._environment), close_fds=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        except (OSError, ValueError):
            raise HerdrTransportError("HERDR_UNAVAILABLE") from None
        output = bytearray()
        lock = threading.Lock()
        exceeded, read_failed = threading.Event(), threading.Event()
        total = 0

        def drain(stream, keep):
            nonlocal total
            try:
                while chunk := stream.read1(16 * 1024):
                    with lock:
                        total += len(chunk)
                        if total > self.max_output:
                            exceeded.set()
                            return
                        if keep:
                            output.extend(chunk)
            except (OSError, ValueError):
                read_failed.set()
            finally:
                stream.close()

        readers = [threading.Thread(target=drain, args=(process.stdout, True), daemon=True),
                   threading.Thread(target=drain, args=(process.stderr, False), daemon=True)]
        try:
            for reader in readers:
                reader.start()
            while process.poll() is None or any(reader.is_alive() for reader in readers):
                if exceeded.is_set():
                    raise HerdrTransportError("HERDR_OUTPUT_LIMIT")
                if read_failed.is_set():
                    raise HerdrTransportError("HERDR_READ_FAILED")
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise HerdrTransportError("HERDR_TIMEOUT")
                exceeded.wait(min(remaining, 0.01))
            if exceeded.is_set():
                raise HerdrTransportError("HERDR_OUTPUT_LIMIT")
            if read_failed.is_set():
                raise HerdrTransportError("HERDR_READ_FAILED")
            if process.returncode != 0:
                raise HerdrTransportError("HERDR_COMMAND_FAILED")
            return bytes(output)
        finally:
            # Only this exact child is ours. Never terminate a server, a process
            # group, descendants, or a PID discovered in external metadata.
            if process.poll() is None:
                try:
                    process.kill()
                except OSError:
                    pass
            try:
                process.wait(timeout=0.25)
            except (OSError, subprocess.TimeoutExpired):
                pass
            for reader in readers:
                if reader.ident is not None:
                    reader.join(timeout=0.25)

"""Explicit local Codex/Claude campaign with content-free protocol frame evidence.

Intercepts the existing transport boundaries, without changing commands, security
profiles, waits or native replies. Never persists frame bodies or native IDs.
The existing native fixture owns the disposable login copy and process cleanup.
"""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import ExitStack
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import threading
import time
from unittest.mock import patch


CODEX_COMMANDS = {"initialize": "initialize", "initialized": "initialize",
    "thread/start": "session_start", "thread/unsubscribe": "session_detach",
    "turn/start": "turn_start", "turn/steer": "steer", "turn/interrupt": "interrupt"}
CODEX_QUERIES = {"thread/read", "thread/list", "thread/loaded/list", "turn/read", "get_status"}
CODEX_EVENTS = {"thread/started", "thread/status/changed", "turn/started", "turn/completed",
    "item/started", "item/completed", "item/agentMessage/delta", "item/reasoning/textDelta",
    "item/reasoning/summaryTextDelta", "item/reasoning/summaryPartAdded",
    "thread/tokenUsage/updated", "account/rateLimits/updated", "model/rerouted",
    "item/commandExecution/requestApproval", "item/fileChange/requestApproval",
    "item/tool/requestUserInput", "error"}
CLAUDE_TYPES = {"system", "assistant", "user", "result", "stream_event",
                "control_request", "control_response", "control_cancel_request", "keep_alive"}
CLAUDE_CONTROLS = {"initialize": "initialize", "interrupt": "interrupt", "can_use_tool": "approval_request"}


class FrameRecorder:
    def __init__(self, *, limit=100_000):
        self.limit = limit
        self.frames = []
        self.overflow = False
        self._lock = threading.Lock()
        self._started = time.monotonic_ns()
        self._identities = {}
        self.current_test = "setup"
        self.test_results = []

    def _alias(self, family, value):
        if not isinstance(value, (str, int)) or isinstance(value, bool):
            return None
        key = family, type(value).__name__, value
        if key not in self._identities:
            self._identities[key] = len(self._identities) + 1
        return self._identities[key]

    def record(self, adapter, direction, payload, *, boundary="observed", peer=None):
        with self._lock:
            if len(self.frames) >= self.limit:
                self.overflow = True
                return None
            obj = payload if isinstance(payload, dict) else {}
            category, name = "unclassified", "unclassified"
            if adapter == "codex":
                method = obj.get("method")
                if isinstance(method, str):
                    if direction == "out":
                        category = "status_query" if method in CODEX_QUERIES else CODEX_COMMANDS.get(method, "unclassified")
                        name = method if category != "unclassified" else "unclassified"
                    else:
                        category = "native_request" if "id" in obj else "native_event"
                        name = method if method in CODEX_EVENTS else "other_native_method"
                elif "id" in obj and ("result" in obj or "error" in obj):
                    category = "native_reply" if direction == "in" else "control_reply"
                    name = "jsonrpc_reply"
                params = obj.get("params", {})
                params = params if isinstance(params, dict) else {}
                request = obj.get("id")
                thread, turn = params.get("threadId"), params.get("turnId")
                # The alias is only linkage, never an assertion of authority.
                if isinstance(params.get("turn"), dict):
                    turn = turn or params["turn"].get("id")
            else:
                kind = obj.get("type")
                name = kind if isinstance(kind, str) and kind in CLAUDE_TYPES else "unclassified"
                category = "native_event" if direction == "in" else "unclassified"
                if kind == "user" and direction == "out":
                    category = "turn_start"
                elif kind == "control_response":
                    category = "control_reply" if direction == "out" else "native_reply"
                elif kind == "control_request":
                    request_body = obj.get("request", {})
                    subtype = request_body.get("subtype") if isinstance(request_body, dict) else None
                    category = CLAUDE_CONTROLS.get(subtype, "unclassified") if isinstance(subtype, str) else "unclassified"
                    name = "control_request:" + subtype if category != "unclassified" else "unclassified"
                response = obj.get("response", {})
                request = obj.get("request_id") or (response.get("request_id") if isinstance(response, dict) else None)
                thread, turn = obj.get("session_id"), None
            row = {"sequence": len(self.frames) + 1, "elapsed_ns": time.monotonic_ns() - self._started,
                   "test": self.current_test, "adapter": adapter, "direction": direction,
                   "category": category, "name": name, "boundary": boundary,
                   "peer_alias": self._alias("peer", peer),
                   "request_alias": self._alias((adapter, peer, "request"), request),
                   "thread_alias": self._alias((adapter, peer, "thread"), thread),
                   "turn_alias": self._alias((adapter, peer, "turn"), turn)}
            self.frames.append(row)
            return row

    def writer(self, adapter, original):
        def wrapped(peer, payload, *args, **kwargs):
            stream = getattr(getattr(peer, "_proc", None), "stdout", None)
            row = self.record(adapter, "out", payload, boundary="write_attempted", peer=id(stream if stream is not None else peer))
            try:
                result = original(peer, payload, *args, **kwargs)
            except BaseException:
                if row is not None:
                    row["boundary"] = "write_failed_or_uncertain"
                raise
            if row is not None:
                row["boundary"] = "write_returned"
            return result
        return wrapped

    def reader(self, adapter, original):
        def wrapped(stream, *args, **kwargs):
            for line in original(stream, *args, **kwargs):
                try:
                    obj = json.loads(line)
                except (ValueError, TypeError):
                    obj = None
                self.record(adapter, "in", obj, peer=id(stream))
                yield line
        return wrapped

    def pytest_runtest_setup(self, item):
        self.current_test = item.nodeid

    def pytest_runtest_logreport(self, report):
        self.test_results.append({"test": report.nodeid, "phase": report.when,
                                  "outcome": report.outcome})

    def qualification(self, exit_code):
        outbound = [frame for frame in self.frames if frame["direction"] == "out"]
        forbidden = [frame for frame in outbound if frame["category"] in {"status_query", "unclassified"}]
        calls = [row for row in self.test_results if row["phase"] == "call"]
        return (exit_code == 0 and bool(calls) and all(row["outcome"] == "passed" for row in calls)
                and not any(row["outcome"] != "passed" for row in self.test_results)
                and not self.overflow and bool(outbound) and not forbidden
                and any(frame["direction"] == "in" for frame in self.frames))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adapter", required=True, choices=["codex", "claude_code"])
    parser.add_argument("--executable", required=True, type=Path)
    parser.add_argument("--auth-source", required=True, type=Path)
    parser.add_argument("--selection", default="two_turns or active_control or active_close or approval_denial or question_roundtrip or multiplex or explicit_work")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    for value in (args.executable, args.auth_source):
        if not value.is_absolute() or not value.is_file():
            parser.error("Explicit installed executable and approved login-file paths are required")
    root = Path(__file__).resolve().parents[2]
    if Path.cwd() != root:
        parser.error("Run from the repository root")
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    # Preserve the source/test freeze; generated dashboard files are unrelated.
    diff = subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=all", "--", "src", "tests",
        ":!src/okto_nexus/adapters/inbound/http/static"])
    if diff:
        parser.error("Commit implementation and tests before the native qualification campaign")
    base = Path(tempfile.mkdtemp(prefix="okto-frame-" + args.adapter + "-"))
    print("source_sha=" + sha, flush=True)
    print("evidence_temp=" + str(base), flush=True)
    sys.path.insert(0, str(root / "src"))
    import pytest
    from okto_nexus.adapters.outbound.harness import codex, claude_code_stream
    from collect_effective_capability_evidence import collect
    assert Path(codex.__file__).resolve().is_relative_to(root / "src")
    assert Path(claude_code_stream.__file__).resolve().is_relative_to(root / "src")
    recorder = FrameRecorder()
    env = {"OKTO_NEXUS_NATIVE_CAMPAIGN": args.adapter,
           "OKTO_NEXUS_TEST_EXECUTABLE": str(args.executable),
           "OKTO_NEXUS_TEST_AUTH_SOURCE": str(args.auth_source),
           "OKTO_NEXUS_CODEX_LIVE": "0", "OKTO_NEXUS_CLAUDE_LIVE": "0", "OKTO_NEXUS_UI_CAMPAIGN": "0",
           "OKTO_NEXUS_QUALIFY_NATIVE_CONTRACT": "0"}
    with ExitStack() as stack:
        stack.enter_context(patch.dict(os.environ, env))
        stack.enter_context(patch.object(codex._CodexTransport, "_write", recorder.writer("codex", codex._CodexTransport._write)))
        stack.enter_context(patch.object(codex, "protocol_lines", recorder.reader("codex", codex.protocol_lines)))
        stack.enter_context(patch.object(claude_code_stream.ClaudeCodeStreamConnector, "_write_json",
            recorder.writer("claude_code", claude_code_stream.ClaudeCodeStreamConnector._write_json)))
        stack.enter_context(patch.object(claude_code_stream, "protocol_lines", recorder.reader("claude_code", claude_code_stream.protocol_lines)))
        code = int(pytest.main(["-q", "--tb=short", "tests/test_runtime_native_campaign.py",
            "-k", args.adapter + " and (" + args.selection + ")", "--basetemp=" + str(base / "pytest"),
            "--junitxml=" + str(base / "results.xml")], plugins=[recorder]))
    try:
        compatibility = collect(base)
    except ValueError:
        compatibility = []
    counts = Counter(frame["category"] for frame in recorder.frames if frame["direction"] == "out")
    result = {"source_sha": sha, "recorder_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "recorded_at": datetime.now(timezone.utc).isoformat(), "platform": platform.platform(),
        "python": platform.python_version(), "architecture": platform.machine(),
        "backend_profile_id": "native-fixture", "executable_name": args.executable.name,
        "selection": args.selection,
        "command": "python plans/pr34-remediation/native_frame_campaign.py --adapter=<recorded adapter> --executable=<explicit installed binary> --auth-source=<approved login file> --selection=<recorded selection> --output=<evidence JSON>",
        "adapter": args.adapter, "pytest_exit_code": code,
        "status": "PASS" if recorder.qualification(code) else "FAIL",
        "test_results": recorder.test_results, "outbound_categories": dict(counts),
        "overflow": recorder.overflow, "compatibility": compatibility, "frames": recorder.frames,
        "limitations": "Protocol JSON frames observed at existing reader/writer boundaries; stderr is not protocol. Write return is not harness acceptance. Raw prompts, credentials, native IDs and payloads omitted. Peer alias identifies the owned stdout stream; request/thread/turn aliases are observational linkage, not authentication. Test driver polls Nexus operation reads; this is not harness status polling. Real qualification is limited to recorded versions and isolated configuration. Pi/dedicated attach NOT_RUN."}
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "outbound_categories": dict(counts), "frames": len(recorder.frames)}))
    return code or (0 if result["status"] == "PASS" else 1)


if __name__ == "__main__":
    sys.exit(main())

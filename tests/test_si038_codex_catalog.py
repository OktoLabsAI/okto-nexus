"""Protocol tests for the SI-038 account/model observation."""

import asyncio
import hashlib
import json
import os
import socket
import sys
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from tools import si038_codex_catalog
from tools.si038_codex_catalog import CatalogError, isolated_catalog, observe

PEER = """
import json
import sys
from pathlib import Path

mode = sys.argv[1]
for line in sys.stdin:
    request = json.loads(line)
    with Path("requests.jsonl").open("a", encoding="utf-8") as output:
        output.write(line)
    method = request["method"]
    if method == "initialize":
        result = {"userAgent": "fixture"}
    elif method == "initialized":
        continue
    elif method == "account/read":
        if mode == "server_request":
            print(json.dumps({"id": 11, "method": "account/chatgptAuthTokens/refresh"}), flush=True)
            continue
        result = {"account": {"type": "chatgpt", "email": "private-fixture@example.test"},
                  "requiresOpenaiAuth": True}
    elif method == "model/list":
        assert request["params"]["limit"] == 50 and request["params"]["includeHidden"] is False
        if request["params"].get("cursor") is None:
            result = {"data": [{"model": "fixture-main", "isDefault": True}], "nextCursor": "page-2"}
        else:
            tail = "page-2" if mode == "repeat_cursor" else None
            result = {"data": [{"model": "fixture-other", "isDefault": False}], "nextCursor": tail}
    else:
        raise AssertionError("Unexpected method")
    print(json.dumps({"id": request["id"], "result": result}), flush=True)
"""


def run_peer(tmp_path, mode):
    peer = tmp_path / "peer.py"
    peer.write_text(PEER, encoding="utf-8")
    return asyncio.run(observe([sys.executable, "-I", str(peer), mode], tmp_path, os.environ.copy()))


def requests(tmp_path):
    return [json.loads(line) for line in (tmp_path / "requests.jsonl").read_text(encoding="utf-8").splitlines()]


def test_catalog_has_only_presence_and_model_names(tmp_path):
    assert run_peer(tmp_path, "complete") == {
        "provider_session_present": True,
        "models": ["fixture-main", "fixture-other"],
        "defaults": ["fixture-main"],
    }
    calls = requests(tmp_path)
    assert [call["method"] for call in calls] == [
        "initialize", "initialized", "account/read", "model/list", "model/list",
    ]
    assert calls[2]["params"] == {"refreshToken": False}
    assert calls[4]["params"]["cursor"] == "page-2"


def test_engine_request_aborts_without_reply_or_another_read(tmp_path):
    with pytest.raises(CatalogError, match="requested an action"):
        run_peer(tmp_path, "server_request")
    assert [call["method"] for call in requests(tmp_path)] == ["initialize", "initialized", "account/read"]


def test_cursor_loop_fails_without_returning_partial_catalog(tmp_path):
    with pytest.raises(CatalogError, match="complete model catalog"):
        run_peer(tmp_path, "repeat_cursor")
    assert len(requests(tmp_path)) == 5


def test_wrong_engine_refused_before_accessing_auth_snapshot(tmp_path):
    executable = tmp_path / "wrong-engine.exe"
    executable.write_bytes(b"fixture")
    with pytest.raises(CatalogError, match="differs from the reviewed"):
        isolated_catalog(executable, Path("missing-auth-snapshot.json"))


@pytest.mark.parametrize("staged", [False, True])
def test_probe_contains_profile_and_blocks_auth_refresh(tmp_path, monkeypatch, staged):
    executable = tmp_path / "engine.exe"
    executable.write_bytes(b"fixture-engine")
    snapshot = tmp_path / "fixture-auth.json"
    snapshot.write_text('{"synthetic": true}', encoding="utf-8")
    monkeypatch.setattr(si038_codex_catalog, "ENGINE_SHA256", hashlib.sha256(b"fixture-engine").hexdigest())
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-reach-child")
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "personal"))
    workspaces = []

    async def inspect(command, workspace, env):
        workspaces.append(workspace)
        assert command == [str(executable), "app-server"]
        profile = Path(env["CODEX_HOME"])
        assert profile.parent == workspace.parent and profile != tmp_path / "personal"
        assert "OPENAI_API_KEY" not in env
        assert (profile / "auth.json").exists() == staged
        if staged:
            assert (profile / "auth.json").read_bytes() == snapshot.read_bytes()
        assert ("HTTPS_PROXY" not in env) == staged
        refresh = urlsplit(env["CODEX_REFRESH_TOKEN_URL_OVERRIDE"])
        assert refresh.hostname == "127.0.0.1"
        assert env["CODEX_REVOKE_TOKEN_URL_OVERRIDE"] == refresh.geturl()
        with socket.socket() as sock:
            sock.settimeout(1)
            assert sock.connect_ex((refresh.hostname, refresh.port)) != 0
        return {"provider_session_present": staged}

    monkeypatch.setattr(si038_codex_catalog, "observe", inspect)
    assert isolated_catalog(executable, snapshot if staged else None) == {"provider_session_present": staged}
    assert not workspaces[0].parent.exists()
    assert snapshot.read_text(encoding="utf-8") == '{"synthetic": true}'

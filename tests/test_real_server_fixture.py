"""Self-tests for the `real_server` fixture (Phase 1.1, S1.1).

These are the first tests in this repo that bind a REAL socket: a real
`okto-nexus serve` child process, hit over real HTTP (httpx) rather than
FastAPI's in-process TestClient. This is evidence infrastructure for the
harness-integrations DoD gate - see plans/harness-integrations/00-plan.md.
"""

from __future__ import annotations

import sqlite3

import pytest

httpx = pytest.importorskip("httpx")


def test_real_server_answers_info_over_real_socket(real_server):
    resp = httpx.get(f"{real_server.base_url}/api/v1/info", timeout=5.0)
    assert resp.status_code == 200
    body = resp.json()
    data = body.get("data", body)
    assert data["service"] == "okto-nexus"
    assert "schema_version" in data


def test_agent_register_and_read_back_over_real_http(real_server):
    agent_id = "fixture-check-agent"
    create = httpx.post(
        f"{real_server.base_url}/api/v1/agents",
        json={"agent_id": agent_id, "role": "worker"},
        timeout=5.0,
    )
    assert create.status_code == 200, create.text
    created = create.json()["data"]
    assert created["agent_id"] == agent_id
    assert created["api_key"]  # plaintext key issued exactly once

    read_back = httpx.get(
        f"{real_server.base_url}/api/v1/agents/{agent_id}", timeout=5.0
    )
    assert read_back.status_code == 200, read_back.text
    fetched = read_back.json()["data"]
    assert fetched["agent_id"] == agent_id
    assert fetched["role"] == "worker"
    # The plaintext key is a create-only, single-exposure surface (BR7/AC3):
    # the read-back path must never carry it.
    assert "api_key" not in fetched


def test_isolated_db_is_used_not_the_developer_real_home(real_server):
    db_path = real_server.home_dir / "nexus.db"
    assert db_path.exists(), (
        "expected the isolated DB under the fixture's tmp home, "
        f"not the developer's real ~/.okto_nexus: {real_server.output()}"
    )
    # Confirm it is a real, migrated okto-nexus DB - not an empty stray file.
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM agents WHERE agent_id = ?",
            ("fixture-check-agent",),
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    # The row may or may not exist yet depending on test order within the
    # session; the assertion that matters is that THIS file, not
    # ~/.okto_nexus/nexus.db, is the one the server wrote to - proven by the
    # file existing under the fixture's own tmp home dir at all.
    assert real_server.home_dir.name.startswith("okto_nexus_home")

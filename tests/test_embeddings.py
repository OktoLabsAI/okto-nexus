"""Semantic search over message content (Frente 3): generation, cosine search,
CASCADE lifecycle, age-pure message retention, packaging/degradation and the
fail-closed knobs.

Every test asserts the OBSERVABLE effect (rows in ``message_embeddings``, the
HTTP envelope, prune report counts, config errors) - never implementation
source. Generation runs under the deterministic STUB provider
(``embedding_mode=stub``) so vectors are reproducible without the optional
sentence-transformers extra.

Scenario coverage (spec 27e8867f):
* generation + deterministic stub vector (AC1)
* cosine-ranked search, k clamp/validation (AC2)
* CASCADE drops the embedding when the message is deleted (AC3)
* messages reaper purges by PURE AGE regardless of status, batched + thread
  self-FK (AC4)
* keep-days < 7 fails closed (AC5)
* degradation + domain import-boundary without the extra (AC6)
* empty body never generates an embedding
* invalid embedding_mode fails closed
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from okto_nexus.adapters.inbound.http.app import build_app  # noqa: E402
from okto_nexus.adapters.inbound.mcp.server import bootstrap  # noqa: E402
from okto_nexus.adapters.inbound.mcp.tools.messages import (  # noqa: E402
    build_service as build_message_service,
)
from okto_nexus.adapters.outbound.embedding import (  # noqa: E402
    EMBEDDING_DIM,
    STUB_MODEL_NAME,
    StubEmbeddingProvider,
    resolve_embedding_provider,
)
from okto_nexus.application.retention import RetentionService  # noqa: E402
from okto_nexus.application.settings import (  # noqa: E402
    SettingsService,
    detect_pinned_fields,
)
from okto_nexus.config import load_config  # noqa: E402
from okto_nexus.domain.base import iso_plus, utc_now_iso  # noqa: E402
from okto_nexus.errors import ErrorCode, OktoNexusError  # noqa: E402


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def make_deps(tmp_path, mode: str = "stub"):
    return bootstrap({}, ["--home", str(tmp_path / "home"), "--embedding-mode", mode])


def seed_agents(deps, *agent_ids: str) -> None:
    with deps.connection_factory.unit_of_work() as uow:
        for agent_id in agent_ids:
            deps.repos.agents.upsert(uow, agent_id=agent_id)


def embedding_ids(deps) -> set[str]:
    conn = deps.connection_factory.get_connection()
    try:
        rows = conn.execute("SELECT message_id FROM message_embeddings").fetchall()
        return {row[0] for row in rows}
    finally:
        conn.close()


def embedding_row(deps, message_id: str):
    conn = deps.connection_factory.get_connection()
    try:
        return conn.execute(
            "SELECT model, dim, vec FROM message_embeddings WHERE message_id = ?",
            (message_id,),
        ).fetchone()
    finally:
        conn.close()


def message_ids(deps) -> set[str]:
    conn = deps.connection_factory.get_connection()
    try:
        rows = conn.execute("SELECT message_id FROM messages").fetchall()
        return {row[0] for row in rows}
    finally:
        conn.close()


def backdate_message(deps, message_id: str, iso: str) -> None:
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute(
            "UPDATE messages SET created_at = ? WHERE message_id = ?",
            (iso, message_id),
        )


def make_retention(deps, *, batch_size: int = 500) -> RetentionService:
    repos = deps.repos
    return RetentionService(
        connection_factory=deps.connection_factory,
        clock=deps.clock,
        config=deps.config,
        events=repos.events,
        deliveries=repos.deliveries,
        sessions=repos.sessions,
        messages=repos.messages,
        batch_size=batch_size,
    )


# --------------------------------------------------------------------------- #
# AC1 - generation + deterministic stub vector (ts_85a397cd)
# --------------------------------------------------------------------------- #
def test_create_message_persists_one_deterministic_embedding(tmp_path):
    deps = make_deps(tmp_path, mode="stub")
    seed_agents(deps, "alice", "bob")
    service = build_message_service(deps)
    root = str(tmp_path)

    sent = service.create_message(
        project_root=root, from_agent_id="alice", subject="hi",
        body="the quick brown fox", target={"strategy": "direct", "agent_id": "bob"},
    )
    message_id = sent["message_id"]

    row = embedding_row(deps, message_id)
    assert row is not None
    assert row["model"] == STUB_MODEL_NAME
    assert row["dim"] == EMBEDDING_DIM
    assert len(row["vec"]) == EMBEDDING_DIM * 4  # float32 little-endian BLOB
    assert embedding_ids(deps) == {message_id}  # exactly one row

    # Deterministic: an identical subject+body yields the identical vector.
    twin = service.create_message(
        project_root=root, from_agent_id="alice", subject="hi",
        body="the quick brown fox", target={"strategy": "direct", "agent_id": "bob"},
    )
    assert embedding_row(deps, twin["message_id"])["vec"] == row["vec"]


def test_stub_provider_is_deterministic_and_fixed_dim():
    provider = StubEmbeddingProvider()
    assert provider.dim == EMBEDDING_DIM
    a = provider.encode("hello world")
    b = provider.encode("hello world")
    c = provider.encode("a different string")
    assert a == b and len(a) == EMBEDDING_DIM
    assert a != c  # distinct text -> distinct vector


# --------------------------------------------------------------------------- #
# AC2 - cosine-ranked search (ts_fa5c31d2) + k clamp/validation (ts_446c24f1)
# --------------------------------------------------------------------------- #
@pytest.fixture
def stub_client(tmp_path):
    deps = make_deps(tmp_path, mode="stub")
    seed_agents(deps, "alice", "bob")
    service = build_message_service(deps)
    root = str(tmp_path)
    sent = []
    for i, body in enumerate(
        ["alpha report on widgets", "beta notes about gadgets", "gamma summary"]
    ):
        sent.append(
            service.create_message(
                project_root=root, from_agent_id="alice", subject=f"s{i}",
                body=body, target={"strategy": "direct", "agent_id": "bob"},
            )
        )
    app = build_app(deps)
    with TestClient(app, client=("127.0.0.1", 50300)) as client:
        yield client, sent


def test_search_returns_cosine_ranked_items(stub_client):
    client, sent = stub_client
    target = sent[0]
    # The stored embed text is "subject\nbody"; querying it back yields cosine
    # 1.0 with that message, so it MUST rank first.
    query = f"s0\nalpha report on widgets"
    data = client.get(
        "/api/v1/messages/search", params={"q": query, "k": 3}
    ).json()["data"]

    assert data["query"] == query and data["k"] == 3
    assert len(data["items"]) <= 3
    scores = [item["score"] for item in data["items"]]
    assert scores == sorted(scores, reverse=True)  # cosine DESC
    top = data["items"][0]
    assert top["message_id"] == target["message_id"]
    assert top["score"] > 0.999  # self-similarity
    for item in data["items"]:  # contract shape
        assert set(item) >= {
            "message_id", "score", "from_agent_id", "subject", "created_at"
        }


def test_search_validates_blank_query_and_clamps_k(stub_client):
    client, _ = stub_client
    # Blank / missing q -> 422 VALIDATION_ERROR.
    assert client.get("/api/v1/messages/search", params={"q": "  "}).status_code == 422
    assert client.get("/api/v1/messages/search").status_code == 422

    # k absent -> 10; out-of-range CLAMPED to [1, 50]; non-integer -> 422.
    assert client.get("/api/v1/messages/search", params={"q": "x"}).json()["data"]["k"] == 10
    assert (
        client.get("/api/v1/messages/search", params={"q": "x", "k": "999"})
        .json()["data"]["k"]
        == 50
    )
    assert (
        client.get("/api/v1/messages/search", params={"q": "x", "k": "0"})
        .json()["data"]["k"]
        == 1
    )
    bad = client.get("/api/v1/messages/search", params={"q": "x", "k": "abc"})
    assert bad.status_code == 422
    assert bad.json()["error"]["code"] == "VALIDATION_ERROR"


# --------------------------------------------------------------------------- #
# AC3 - CASCADE drops the embedding on message delete (ts_6f8be7e9)
# --------------------------------------------------------------------------- #
def test_deleting_a_message_cascades_to_its_embedding(tmp_path):
    deps = make_deps(tmp_path, mode="stub")
    service = build_message_service(deps)
    # Broadcast (no present agents) -> message persists with NO deliveries, so
    # the embedding is the only inbound reference; deleting the row cascades.
    sent = service.create_message(
        project_root=str(tmp_path), from_agent_id="alice", subject="solo",
        body="content to be indexed then removed", target=None,
    )
    message_id = sent["message_id"]
    assert embedding_ids(deps) == {message_id}

    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute(
            "DELETE FROM messages WHERE message_id = ?", (message_id,)
        )
    # foreign_keys=ON + ON DELETE CASCADE -> zero orphan embeddings.
    assert embedding_ids(deps) == set()


# --------------------------------------------------------------------------- #
# AC4 - messages reaper: pure age, any status (ts_9594174d)
# --------------------------------------------------------------------------- #
def test_reaper_purges_messages_by_age_regardless_of_status(tmp_path):
    deps = make_deps(tmp_path, mode="stub")
    seed_agents(deps, "alice", "bob")
    service = build_message_service(deps)
    root = str(tmp_path)
    now = utc_now_iso()

    old_unread = service.create_message(
        project_root=root, from_agent_id="alice", subject="old1",
        body="ancient unread", target={"strategy": "direct", "agent_id": "bob"},
    )["message_id"]
    old_read = service.create_message(
        project_root=root, from_agent_id="alice", subject="old2",
        body="ancient read", target={"strategy": "direct", "agent_id": "bob"},
    )["message_id"]
    fresh = service.create_message(
        project_root=root, from_agent_id="alice", subject="new",
        body="recent message", target={"strategy": "direct", "agent_id": "bob"},
    )["message_id"]

    # Age the two "old" messages past the 7-day window; drive one delivery to
    # 'read' so we prove status is IRRELEVANT to the age-pure reaper.
    backdate_message(deps, old_unread, iso_plus(now, -10 * 86400.0))
    backdate_message(deps, old_read, iso_plus(now, -10 * 86400.0))
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute(
            "UPDATE message_deliveries SET status = 'read' WHERE message_id = ?",
            (old_read,),
        )

    report = make_retention(deps).prune(messages_keep_days=7)

    assert report["tables"]["messages"]["deleted"] == 2
    assert message_ids(deps) == {fresh}
    # Embeddings followed the messages (CASCADE); the fresh one survived.
    assert embedding_ids(deps) == {fresh}
    # Deliveries of the purged messages went too; the bus did not RESTRICT.
    conn = deps.connection_factory.get_connection()
    try:
        remaining = conn.execute(
            "SELECT COUNT(*) FROM message_deliveries WHERE message_id IN (?, ?)",
            (old_unread, old_read),
        ).fetchone()[0]
    finally:
        conn.close()
    assert remaining == 0


# --------------------------------------------------------------------------- #
# ts_46acb486 - reaper in batches + thread parent self-FK
# --------------------------------------------------------------------------- #
def test_reaper_batches_and_handles_thread_parent_self_fk(tmp_path):
    deps = make_deps(tmp_path, mode="stub")
    service = build_message_service(deps)
    root = str(tmp_path)
    now = utc_now_iso()

    # A thread: parent (to be aged out) + a FRESH reply pointing at it.
    parent = service.create_message(
        project_root=root, from_agent_id="alice", subject="root",
        body="thread root body", target=None,
    )["message_id"]
    child = service.create_message(
        project_root=root, from_agent_id="alice", subject="reply",
        body="thread reply body", target=None, parent_message_id=parent,
    )["message_id"]
    # Two more standalone old messages, so batch_size=1 forces multiple batches.
    extra = [
        service.create_message(
            project_root=root, from_agent_id="alice", subject=f"x{i}",
            body=f"old standalone {i}", target=None,
        )["message_id"]
        for i in range(2)
    ]

    old_iso = iso_plus(now, -30 * 86400.0)
    for message_id in [parent, *extra]:
        backdate_message(deps, message_id, old_iso)
    # child stays fresh (now) -> survives, but references a purged parent.

    report = make_retention(deps, batch_size=1).prune(messages_keep_days=7)

    # 3 old messages purged across 3 single-row batches; the table drained.
    assert report["tables"]["messages"] == {"deleted": 3, "complete": True}
    assert message_ids(deps) == {child}
    # The surviving reply had its dangling parent pointer cleared (no FK error).
    conn = deps.connection_factory.get_connection()
    try:
        parent_ref = conn.execute(
            "SELECT parent_message_id FROM messages WHERE message_id = ?", (child,)
        ).fetchone()[0]
    finally:
        conn.close()
    assert parent_ref is None
    assert embedding_ids(deps) == {child}  # parent's embedding cascaded away


# --------------------------------------------------------------------------- #
# AC5 - keep-days < 7 fails closed (ts_45334b71)
# --------------------------------------------------------------------------- #
def test_messages_keep_days_below_seven_fails_closed_at_config():
    assert load_config({}, []).retention_messages_keep_days == 30  # default
    assert (
        load_config({"OKTO_NEXUS_RETENTION_MESSAGES_KEEP_DAYS": "7"}, [])
        .retention_messages_keep_days
        == 7
    )
    with pytest.raises(OktoNexusError) as ei:
        load_config({"OKTO_NEXUS_RETENTION_MESSAGES_KEEP_DAYS": "5"}, [])
    assert ei.value.code == ErrorCode.CONFIG_ERROR.value


def test_reaper_override_below_seven_fails_closed(tmp_path):
    deps = make_deps(tmp_path, mode="stub")
    service = build_message_service(deps)
    service.create_message(
        project_root=str(tmp_path), from_agent_id="alice", subject="s",
        body="body", target=None,
    )
    with pytest.raises(OktoNexusError) as ei:
        make_retention(deps).prune(messages_keep_days=5)
    assert ei.value.code == ErrorCode.VALIDATION_ERROR.value
    assert message_ids(deps)  # nothing was purged on the rejected call


# --------------------------------------------------------------------------- #
# AC6 - degradation without the extra + domain import boundary (ts_d0c64ecd)
# --------------------------------------------------------------------------- #
def test_search_unavailable_when_disabled_but_rest_works(tmp_path):
    deps = make_deps(tmp_path, mode="off")  # no provider, search disabled
    seed_agents(deps, "alice", "bob")
    service = build_message_service(deps)
    service.create_message(
        project_root=str(tmp_path), from_agent_id="alice", subject="hello",
        body="still works without embeddings",
        target={"strategy": "direct", "agent_id": "bob"},
    )
    # No embedding was generated in off mode.
    assert embedding_ids(deps) == set()

    app = build_app(deps)
    with TestClient(app, client=("127.0.0.1", 50301)) as client:
        search = client.get("/api/v1/messages/search", params={"q": "hello"})
        assert search.status_code == 503
        assert search.json()["error"]["code"] == "EMBEDDINGS_UNAVAILABLE"
        # The rest of the system is unaffected: the message history still reads.
        listing = client.get("/api/v1/messages").json()["data"]
        assert listing["total"] == 1


def test_build_app_honors_stored_embedding_mode_override(tmp_path):
    """Regression: a dashboard-set embedding_mode must take effect on restart.

    bootstrap resolves the embedding capability from the UN-overridden config,
    so a stored override (set via the Settings screen) only lands later in
    build_app. build_app must apply the override AND re-resolve the capability -
    otherwise a saved embedding_mode=stub/local stayed inert (provider off,
    search disabled) until the operator passed a CLI/env flag.
    """
    # Default off (no --embedding-mode flag): the exact pre-fix latent state.
    deps = bootstrap({}, ["--home", str(tmp_path / "home")])
    assert deps.embedding.mode == "off"
    assert deps.embedding.search_enabled is False

    # Persist a dashboard-style override, exactly as PATCH /api/v1/settings does.
    settings = SettingsService(
        deps.config, deps.clock, detect_pinned_fields(deps.config)
    )
    with deps.connection_factory.unit_of_work() as uow:
        settings.update(uow, {"embedding_mode": "stub"})

    app = build_app(deps)

    # build_app applied the override to config AND re-resolved the capability.
    assert deps.config.embedding_mode == "stub"
    assert deps.embedding.mode == "stub"
    assert deps.embedding.search_enabled is True

    # End to end: generation now runs and the search surface answers live.
    seed_agents(deps, "alice", "bob")
    service = build_message_service(deps)
    service.create_message(
        project_root=str(tmp_path), from_agent_id="alice", subject="hi",
        body="semantic content here",
        target={"strategy": "direct", "agent_id": "bob"},
    )
    assert len(embedding_ids(deps)) == 1
    with TestClient(app, client=("127.0.0.1", 50311)) as client:
        search = client.get(
            "/api/v1/messages/search", params={"q": "semantic content here"}
        )
        assert search.status_code == 200
        assert search.json()["data"]["total"] >= 1


def test_domain_and_application_do_not_import_embedding_libraries():
    pkg_root = Path(__file__).resolve().parents[1] / "src" / "okto_nexus"
    forbidden = {"sentence_transformers", "torch", "numpy"}
    violations: list[str] = []
    for package in ("domain", "application"):
        for path in (pkg_root / package).rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.split(".", 1)[0] in forbidden:
                            violations.append(f"{path}: import {alias.name}")
                elif isinstance(node, ast.ImportFrom) and node.level == 0:
                    root = (node.module or "").split(".", 1)[0]
                    if root in forbidden:
                        violations.append(f"{path}: from {node.module}")
    assert not violations, "embedding libs leaked into domain/application:\n" + "\n".join(
        violations
    )


# --------------------------------------------------------------------------- #
# Empty body never generates an embedding (ts_bfbdc695)
# --------------------------------------------------------------------------- #
def test_empty_body_never_generates_an_embedding(tmp_path):
    deps = make_deps(tmp_path, mode="stub")
    service = build_message_service(deps)

    # The public path rejects an empty/whitespace body outright.
    with pytest.raises(OktoNexusError) as ei:
        service.create_message(
            project_root=str(tmp_path), from_agent_id="alice", subject="s",
            body="   ", target=None,
        )
    assert ei.value.code == ErrorCode.VALIDATION_ERROR.value

    # And the generation guard itself is a no-op for a blank/None body: it
    # returns BEFORE touching the store (no row, no FK attempt).
    service._maybe_generate_embedding(
        message_id="ghost", subject="s", body="   ", created_at=utc_now_iso()
    )
    service._maybe_generate_embedding(
        message_id="ghost", subject="s", body=None, created_at=utc_now_iso()
    )
    assert embedding_ids(deps) == set()


# --------------------------------------------------------------------------- #
# Invalid embedding_mode fails closed (ts_6e854d13)
# --------------------------------------------------------------------------- #
def test_invalid_embedding_mode_fails_closed():
    assert load_config({}, []).embedding_mode == "off"  # safe default
    for mode in ("stub", "local", "off"):
        assert load_config({"OKTO_NEXUS_EMBEDDING_MODE": mode}, []).embedding_mode == mode
    with pytest.raises(OktoNexusError) as ei:
        load_config({"OKTO_NEXUS_EMBEDDING_MODE": "banana"}, [])
    assert ei.value.code == ErrorCode.CONFIG_ERROR.value
    # The factory is defensive too (it never sees an unvalidated mode in prod).
    with pytest.raises(OktoNexusError):
        resolve_embedding_provider("banana")


def test_resolution_flags_per_mode(tmp_path):
    off = resolve_embedding_provider("off")
    assert off.provider is None and off.search_enabled is False
    stub = resolve_embedding_provider("stub")
    assert stub.provider is not None and stub.search_enabled is True
    # local: real provider when the extra imports, else a degraded stub with
    # search disabled. Both are valid; assert the invariant that holds either way.
    local = resolve_embedding_provider("local")
    assert local.provider is not None
    if local.degraded:
        assert local.search_enabled is False  # extra absent -> search off
    else:
        assert local.search_enabled is True

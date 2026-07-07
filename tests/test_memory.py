"""Workspace memory (spec 8928b320, R-I6) - scenarios TS0..TS11.

Sections map to the Pulse test cards:

* T1/TS0: the PURE domain grammar - title chars, content UTF-8 BYTES,
  topics normalization, the atomic provenance pair, id shape, constants.
* T2/TS1+TS2: happy memory_put (row + vector + metadata-only event) and the
  rejection battery (no row / no vector / no event persists).
* T3/TS3: the fail-closed feature_memory gate on all three verbs + live flip.
* T4/TS4+TS5: semantic (stub) and lexical/recent ranking, declared modes.
* T5/TS6+TS7: supersede chain (bilateral, linear, CONFLICT) + memory_get.
* T6/TS8+TS9: projection promotion of memory_id + trace interop.
* T7/TS10+TS11: operator REST surface + the frozen MCP surface contract.

Declared scenario drifts (also recorded on the Pulse cards):

* TS0 names ``validate_memory_fields``/``validate_source``/
  ``memory_embed_text`` - the shipped names are ``validate_memory_title``/
  ``validate_memory_content``/``normalize_memory_topics``/
  ``validate_memory_provenance``, and the embedded text is
  ``f"{title}\\n{content}"`` built inside the service (topics deliberately
  NOT embedded - the message-embedding subject/body precedent).
* TS2 names a ``memory_entries`` table - the shipped table is ``memories``.
* TS11 names ``reference/memory`` + ``tool-docs/memory`` resources - the
  docs ship INLINE in the three tool descriptions (decision recorded on the
  SURFACE_REVISION 23 comment); a test below locks that decision.
"""

from __future__ import annotations

import asyncio
import functools
import inspect
import json

import pytest

from okto_nexus.adapters.inbound.mcp.projection import (
    MAX_ITEM_BYTES,
    project_event,
)
from okto_nexus.adapters.inbound.mcp.resources import resource_uris
from okto_nexus.adapters.inbound.mcp.server import (
    SURFACE_REVISION,
    bootstrap,
    register_tools,
)
from okto_nexus.adapters.inbound.mcp.surface_metrics import APPROVED_GROWTH
from okto_nexus.adapters.outbound.embedding import (
    EMBEDDING_DIM,
    STUB_MODEL_NAME,
    StubEmbeddingProvider,
)
from okto_nexus.application.memory import (
    CONTENT_PREVIEW_CHARS,
    SEARCH_K_DEFAULT,
    SEARCH_K_MAX,
    SEARCH_K_MIN,
    SEARCH_MODE_LEXICAL,
    SEARCH_MODE_RECENT,
    SEARCH_MODE_SEMANTIC,
)
from okto_nexus.domain.memory import (
    MEMORY_CONTENT_MAX_BYTES,
    MEMORY_CREATED_EVENT,
    MEMORY_SOURCE_ID_MAX_LEN,
    MEMORY_SOURCE_KINDS,
    MEMORY_STREAM,
    MEMORY_SUPERSEDED_EVENT,
    MEMORY_TITLE_MAX_LEN,
    MEMORY_TOPIC_MAX_LEN,
    MEMORY_TOPICS_MAX,
    new_memory_id,
    normalize_memory_topics,
    validate_memory_content,
    validate_memory_provenance,
    validate_memory_title,
)
from okto_nexus.errors import ErrorCode, OktoNexusError


def _raises(fn, *args, code=ErrorCode.VALIDATION_ERROR, **kwargs) -> OktoNexusError:
    with pytest.raises(OktoNexusError) as exc_info:
        fn(*args, **kwargs)
    assert exc_info.value.code == code, exc_info.value
    return exc_info.value


# --------------------------------------------------------------------------- #
# T1 / TS0 - pure domain grammar (no I/O; import-boundary keeps it pure)
# --------------------------------------------------------------------------- #
class TestMemoryDomainGrammar:
    def test_constants_lock(self):
        assert MEMORY_TITLE_MAX_LEN == 200
        assert MEMORY_CONTENT_MAX_BYTES == 16384
        # BR8: one memory always fits a default projection item untruncated.
        assert MEMORY_CONTENT_MAX_BYTES == MAX_ITEM_BYTES
        assert MEMORY_TOPICS_MAX == 10
        assert MEMORY_TOPIC_MAX_LEN == 50
        assert MEMORY_SOURCE_KINDS == {"event", "message", "handoff"}
        assert MEMORY_SOURCE_ID_MAX_LEN == 128
        assert MEMORY_STREAM == "workspace"
        assert MEMORY_CREATED_EVENT == "memory.created"
        assert MEMORY_SUPERSEDED_EVENT == "memory.superseded"
        # Service-level search contract (FR4/BR6).
        assert (SEARCH_K_DEFAULT, SEARCH_K_MIN, SEARCH_K_MAX) == (10, 1, 50)
        assert CONTENT_PREVIEW_CHARS == 240
        assert (SEARCH_MODE_SEMANTIC, SEARCH_MODE_LEXICAL, SEARCH_MODE_RECENT) == (
            "semantic",
            "lexical",
            "recent",
        )

    def test_new_memory_id_shape(self):
        mid = new_memory_id()
        assert mid.startswith("mem_") and len(mid) == 36
        int(mid[4:], 16)  # 32 hex chars
        assert new_memory_id() != mid

    def test_title_boundaries(self):
        assert validate_memory_title("  DB uses WAL  ") == "DB uses WAL"
        assert validate_memory_title("x" * MEMORY_TITLE_MAX_LEN) == "x" * 200
        assert validate_memory_title(" " + "x" * 200 + " ") == "x" * 200
        _raises(validate_memory_title, "x" * 201)
        _raises(validate_memory_title, "")
        _raises(validate_memory_title, "   ")
        _raises(validate_memory_title, None)
        _raises(validate_memory_title, 123)

    def test_content_boundary_is_utf8_bytes_not_chars(self):
        # "e-acute" is 2 UTF-8 bytes: 8192 chars == exactly 16384 bytes (OK).
        two_byte = "é" * 8192
        assert validate_memory_content(two_byte) == two_byte
        # One more char crosses the byte ceiling at only 8193 CHARS.
        exc = _raises(validate_memory_content, two_byte + "x")
        assert exc.details["content_bytes"] == 16385
        assert "artifact_put" in exc.message  # points at the escape hatch (BR8)
        # 4-byte emoji: 4096 chars == 16384 bytes (OK), 4097 rejected.
        four_byte = "\U0001f9e0" * 4096
        assert validate_memory_content(four_byte) == four_byte
        _raises(validate_memory_content, four_byte + "!")
        _raises(validate_memory_content, "")
        _raises(validate_memory_content, None)

    def test_topics_normalization(self):
        assert normalize_memory_topics(None) == []
        assert normalize_memory_topics([]) == []
        # trim + lowercase + silent dedup, first-seen order preserved.
        assert normalize_memory_topics([" SQLite ", "sqlite", "OPS", "ops"]) == [
            "sqlite",
            "ops",
        ]
        # 10 DISTINCT topics pass even with extra duplicates in the input.
        ten = [f"t{i}" for i in range(10)]
        assert normalize_memory_topics(ten + ["T0", "t1"]) == ten
        exc = _raises(normalize_memory_topics, [f"t{i}" for i in range(11)])
        assert exc.details["topics_count"] == 11
        assert normalize_memory_topics(["A" * MEMORY_TOPIC_MAX_LEN]) == ["a" * 50]
        _raises(normalize_memory_topics, ["a" * 51])
        _raises(normalize_memory_topics, [""])
        _raises(normalize_memory_topics, [1])
        _raises(normalize_memory_topics, "notalist")

    def test_provenance_atomic_pair(self):
        assert validate_memory_provenance(None, None) == (None, None)
        assert validate_memory_provenance(" Event ", " evt-1 ") == ("event", "evt-1")
        assert validate_memory_provenance("message", "m" * 128)[1] == "m" * 128
        # One without the other: atomic pair (BR3), both directions.
        _raises(validate_memory_provenance, "event", None)
        _raises(validate_memory_provenance, None, "evt-1")
        exc = _raises(validate_memory_provenance, "commit", "abc123")
        assert exc.details["supported"] == sorted(MEMORY_SOURCE_KINDS)
        _raises(validate_memory_provenance, "event", "")
        _raises(validate_memory_provenance, "event", "s" * 129)

    def test_stub_embedding_is_deterministic(self):
        # TS0 drift, declared: there is no domain-level memory_embed_text -
        # the service embeds f"{title}\n{content}" (topics NOT included).
        # Here we lock the provider half: same text -> same vector.
        provider = StubEmbeddingProvider()
        assert provider.model == STUB_MODEL_NAME
        assert provider.dim == EMBEDDING_DIM == 384
        assert provider.encode("T\nC") == provider.encode("T\nC")
        assert provider.encode("T\nC") != provider.encode("T\nC2")


# --------------------------------------------------------------------------- #
# Harness (the test_verification.py / test_handoff_dependencies.py shape):
# the REAL bootstrap in a temp home, tools registered through the same path
# both MCP transports mount, three registered agents.
# --------------------------------------------------------------------------- #
class FakeServer:
    """Captures FastMCP-style ``@server.tool()`` registrations by name."""

    def __init__(self) -> None:
        self.tools: dict = {}

    def tool(self, *args, **kwargs):
        def deco(fn):
            if inspect.iscoroutinefunction(fn):

                @functools.wraps(fn)
                def _sync(*a, **k):
                    return asyncio.run(fn(*a, **k))

                self.tools[fn.__name__] = _sync
            else:
                self.tools[fn.__name__] = fn
            return fn

        return deco


def _ok(env: dict) -> dict:
    assert env["ok"] is True, f"expected ok envelope, got: {env}"
    return env["data"]


def _err(env: dict, code: str) -> dict:
    assert env["ok"] is False, f"expected error envelope, got: {env}"
    assert env["error"]["code"] == code, env["error"]
    return env["error"]


def make_env(
    tmp_path,
    *,
    memory: bool = True,
    embedding: str | None = None,
    extra: dict | None = None,
):
    """Real bootstrap + alpha/beta/gamma over a temp home (feature_memory ON)."""
    env = {"OKTO_NEXUS_HOME": str(tmp_path / "home")}
    if memory:
        env["OKTO_NEXUS_FEATURE_MEMORY"] = "true"
    if embedding is not None:
        env["OKTO_NEXUS_EMBEDDING_MODE"] = embedding
    env.update(extra or {})
    deps = bootstrap(env, [])
    server = FakeServer()
    register_tools(server, deps)
    tools = server.tools
    project = tmp_path / "project"
    project.mkdir(exist_ok=True)
    root = str(project)
    workspace_id = _ok(tools["workspace_resolve"](project_root=root))["workspace_id"]
    _ok(tools["agent_register"](agent_id="alpha", role="builder"))
    _ok(tools["agent_register"](agent_id="beta", role="executor"))
    _ok(tools["agent_register"](agent_id="gamma", role="reviewer"))
    return deps, tools, root, workspace_id


def _count(deps, table: str) -> int:
    conn = deps.connection_factory.get_connection()
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        conn.close()


def _snapshot(deps) -> tuple[int, int, int]:
    """Row counts of every table a rejected memory_put could have touched."""
    return (
        _count(deps, "memories"),
        _count(deps, "memory_embeddings"),
        _count(deps, "events"),
    )


def _events(deps, event_type: str) -> list[dict]:
    conn = deps.connection_factory.get_connection()
    try:
        rows = conn.execute(
            "SELECT payload FROM events WHERE type = ? ORDER BY event_id",
            (event_type,),
        ).fetchall()
        return [json.loads(row["payload"]) for row in rows]
    finally:
        conn.close()


def _vector_row(deps, memory_id: str):
    conn = deps.connection_factory.get_connection()
    try:
        return conn.execute(
            "SELECT vec, model, dim FROM memory_embeddings WHERE memory_id = ?",
            (memory_id,),
        ).fetchone()
    finally:
        conn.close()


def _put(tools, root: str, *, agent="alpha", title="t", content="c", **kwargs) -> dict:
    return _ok(
        tools["memory_put"](
            project_root=root, agent_id=agent, title=title, content=content, **kwargs
        )
    )


def _client(deps):
    """Operator-authenticated TestClient over the SAME deps."""
    from fastapi.testclient import TestClient

    from okto_nexus.adapters.inbound.http.app import build_app, ensure_operator_key
    from okto_nexus.application.auth import AgentKeyAuthService

    auth = AgentKeyAuthService(deps.repos.agents, deps.clock)
    issued = ensure_operator_key(deps, auth)
    assert issued is not None, "expected the cold-start operator key"
    _, operator_key = issued
    client = TestClient(build_app(deps))
    client.headers.update({"x-api-key": operator_key})
    return client


def _issue_key(deps, agent_id: str) -> str:
    from okto_nexus.application.auth import AgentKeyAuthService

    auth = AgentKeyAuthService(deps.repos.agents, deps.clock)
    with deps.connection_factory.unit_of_work() as uow:
        return auth.issue_key(uow, agent_id=agent_id)


# --------------------------------------------------------------------------- #
# T2 / TS1 - happy memory_put: row + vector + metadata-only event
# --------------------------------------------------------------------------- #
def test_ts1_put_persists_row_vector_and_metadata_only_event(tmp_path):
    deps, tools, root, workspace_id = make_env(tmp_path, embedding="stub")
    data = _put(
        tools,
        root,
        title="  DB uses WAL  ",
        content="Writers serialize via WAL mode.",
        topics=[" SQLite ", "WAL", "sqlite"],
        source_kind="event",
        source_id="42",
    )
    assert data["memory_id"].startswith("mem_")
    assert data["workspace_id"] == workspace_id
    assert data["author_agent_id"] == "alpha"
    assert data["title"] == "DB uses WAL"  # stripped by the domain
    assert data["content"] == "Writers serialize via WAL mode."
    assert data["content_bytes"] == len(data["content"].encode("utf-8"))
    assert data["topics"] == ["sqlite", "wal"]  # normalized + deduped
    assert data["source_kind"] == "event" and data["source_id"] == "42"
    assert "created_at" in data and "event_id" in data
    # Conditional fields absent when null (lean full shape).
    for absent in ("supersedes", "superseded_by", "trace_id"):
        assert absent not in data

    assert _count(deps, "memories") == 1
    row = _vector_row(deps, data["memory_id"])
    assert row is not None
    assert row["model"] == STUB_MODEL_NAME and row["dim"] == EMBEDDING_DIM

    payloads = _events(deps, MEMORY_CREATED_EVENT)
    assert len(payloads) == 1
    payload = payloads[0]
    # Metadata-only (BR5): NEVER title nor content on the event.
    assert "title" not in payload and "content" not in payload
    assert payload["memory_id"] == data["memory_id"]
    assert payload["workspace_id"] == workspace_id
    assert payload["author_agent_id"] == "alpha"
    assert payload["topics"] == ["sqlite", "wal"]


def test_ts1_embed_input_is_title_and_content_only(tmp_path):
    # Declared TS0/TS1 drift: topics are NOT part of the embedded text - two
    # memories with identical title+content but different topics get the SAME
    # vector (the embed input is f"{title}\n{content}").
    deps, tools, root, _ = make_env(tmp_path, embedding="stub")
    m1 = _put(tools, root, title="Same", content="Body.", topics=["alpha"])
    m2 = _put(tools, root, title="Same", content="Body.", topics=["beta", "gamma"])
    m3 = _put(tools, root, title="Other", content="Body.")
    v1 = _vector_row(deps, m1["memory_id"])["vec"]
    v2 = _vector_row(deps, m2["memory_id"])["vec"]
    v3 = _vector_row(deps, m3["memory_id"])["vec"]
    assert v1 == v2  # topics do not change the embedding
    assert v1 != v3  # the title does


def test_ts1_put_succeeds_without_vector_when_embedding_off(tmp_path):
    deps, tools, root, _ = make_env(tmp_path)  # embedding mode defaults to off
    data = _put(tools, root, title="No vector", content="Still persists.")
    assert _count(deps, "memories") == 1
    assert _count(deps, "memory_embeddings") == 0
    assert _vector_row(deps, data["memory_id"]) is None


# --------------------------------------------------------------------------- #
# T2 / TS2 - rejection battery: nothing persists on ANY rejection
# --------------------------------------------------------------------------- #
def test_ts2_rejected_puts_leave_no_row_no_vector_no_event(tmp_path):
    deps, tools, root, _ = make_env(tmp_path, embedding="stub")
    base = dict(project_root=root, agent_id="alpha", title="t", content="c")
    before = _snapshot(deps)

    cases = [
        (dict(base, title=""), "VALIDATION_ERROR"),
        (dict(base, title="x" * 201), "VALIDATION_ERROR"),
        (dict(base, content=""), "VALIDATION_ERROR"),
        (dict(base, content="é" * 8192 + "x"), "VALIDATION_ERROR"),
        (dict(base, topics=[f"t{i}" for i in range(11)]), "VALIDATION_ERROR"),
        (dict(base, topics=[""]), "VALIDATION_ERROR"),
        (dict(base, source_kind="event"), "VALIDATION_ERROR"),
        (dict(base, source_kind="commit", source_id="x"), "VALIDATION_ERROR"),
        (dict(base, agent_id=""), "VALIDATION_ERROR"),
        (dict(base, agent_id="ghost"), "NOT_FOUND"),
        (dict(base, supersedes="mem_missing"), "NOT_FOUND"),
        (dict(base, project_root=""), "WORKSPACE_REQUIRED"),
    ]
    for kwargs, code in cases:
        _err(tools["memory_put"](**kwargs), code)
        assert _snapshot(deps) == before, f"state changed after rejection: {kwargs}"


# --------------------------------------------------------------------------- #
# T3 / TS3 - the fail-closed feature gate + live flip
# --------------------------------------------------------------------------- #
def test_ts3_flag_off_rejects_all_three_verbs_with_details(tmp_path):
    deps, tools, root, _ = make_env(tmp_path, memory=False, embedding="stub")
    # The tools stay registered in BOTH flag states (the gate is live, not
    # registration-time).
    assert {"memory_put", "memory_get", "memory_search"} <= set(tools)

    attempts = [
        tools["memory_put"](
            project_root=root, agent_id="alpha", title="t", content="c"
        ),
        tools["memory_get"](project_root=root, memory_id="mem_x"),
        tools["memory_search"](project_root=root, query="q"),
    ]
    for env in attempts:
        error = _err(env, "VALIDATION_ERROR")
        assert error["details"] == {"feature_memory": False}
        assert "feature_memory" in error["message"]
    assert _snapshot(deps) == (0, 0, _snapshot(deps)[2])  # no rows, no vectors


def _direct_message(tools, root: str) -> dict:
    return _ok(
        tools["message_create"](
            project_root=root,
            from_agent_id="alpha",
            subject="s",
            body="b",
            target={"strategy": "direct", "agent_id": "beta"},
        )
    )


def test_ts3_live_flip_preserves_data_and_non_memory_surfaces(tmp_path):
    deps, tools, root, _ = make_env(tmp_path, memory=False)
    # Non-memory envelopes, flag OFF (beta is untouched by the puts below).
    off_env = tools["agent_get"](agent_id="beta")
    off_msg = _direct_message(tools, root)

    deps.config.feature_memory = True  # live flip ON (the D6 settings path)
    mid = _put(tools, root, title="Kept", content="Survives the flip.")["memory_id"]
    on_env = tools["agent_get"](agent_id="beta")
    on_msg = _direct_message(tools, root)
    # Byte-identical non-memory read; write envelope same shape (volatiles masked).
    assert json.dumps(off_env, sort_keys=True) == json.dumps(on_env, sort_keys=True)
    assert sorted(off_msg) == sorted(on_msg)

    deps.config.feature_memory = False  # live flip OFF: reads gated too
    error = _err(
        tools["memory_get"](project_root=root, memory_id=mid), "VALIDATION_ERROR"
    )
    assert error["details"] == {"feature_memory": False}
    assert _count(deps, "memories") == 1  # the data never left the DB

    deps.config.feature_memory = True  # ON again: same id resolves
    data = _ok(tools["memory_get"](project_root=root, memory_id=mid))
    assert data["title"] == "Kept"


# --------------------------------------------------------------------------- #
# T4 / TS4 - semantic ranking (stub embeddings)
# --------------------------------------------------------------------------- #
def _seed_corpus(tools, root) -> tuple[dict, dict, dict]:
    m1 = _put(
        tools,
        root,
        title="SQLite WAL mode",
        content="Writers serialize via the WAL journal.",
        topics=["sqlite", "ops"],
    )
    m2 = _put(
        tools,
        root,
        agent="beta",
        title="Frontend build",
        content="Vite builds into http/static.",
        topics=["frontend"],
    )
    m3 = _put(
        tools,
        root,
        title="SQLite WAL mode v2",
        content="Writers serialize via WAL; checkpoints hourly.",
        topics=["sqlite", "ops"],
        supersedes=m1["memory_id"],
    )
    return m1, m2, m3


def test_ts4_semantic_scores_ordering_topics_and_superseded(tmp_path):
    _deps, tools, root, _ = make_env(tmp_path, embedding="stub")
    m1, m2, m3 = _seed_corpus(tools, root)

    # Query identical to m2's embedded text -> cosine with itself -> top-1.
    exact = f"{m2['title']}\n{m2['content']}"
    data = _ok(tools["memory_search"](project_root=root, query=exact, k=50))
    assert data["search_mode"] == SEARCH_MODE_SEMANTIC
    assert data["count"] == len(data["items"]) >= 1
    scores = [item["score"] for item in data["items"]]
    assert scores == sorted(scores, reverse=True)  # stable descending order
    assert all(s == round(s, 4) for s in scores)  # 4-decimal contract
    assert data["items"][0]["memory_id"] == m2["memory_id"]
    assert data["items"][0]["score"] >= 0.99
    # Deterministic stub: the SAME query returns the SAME ranked list.
    again = _ok(tools["memory_search"](project_root=root, query=exact, k=50))
    assert again["items"] == data["items"]
    # Lean items: preview, never the full content.
    assert "content_preview" in data["items"][0]
    assert "content" not in data["items"][0]
    # Superseded m1 excluded by default...
    ids = {item["memory_id"] for item in data["items"]}
    assert m1["memory_id"] not in ids and m3["memory_id"] in ids
    # ...and included on opt-in, flagged with superseded_by.
    full = _ok(
        tools["memory_search"](
            project_root=root, query=exact, k=50, include_superseded=True
        )
    )
    by_id = {item["memory_id"]: item for item in full["items"]}
    assert by_id[m1["memory_id"]]["superseded_by"] == m3["memory_id"]

    # Topic filter is AND-combined and applied post-ranking.
    both = _ok(
        tools["memory_search"](
            project_root=root, query=exact, topics=["sqlite", "ops"], k=50
        )
    )
    assert {i["memory_id"] for i in both["items"]} == {m3["memory_id"]}
    none = _ok(
        tools["memory_search"](
            project_root=root, query=exact, topics=["sqlite", "missing"], k=50
        )
    )
    assert none["count"] == 0


def test_ts4_k_clamps_and_rejects(tmp_path):
    _deps, tools, root, _ = make_env(tmp_path, embedding="stub")
    _seed_corpus(tools, root)
    search = tools["memory_search"]

    assert len(_ok(search(project_root=root))["items"]) >= 2  # default k=10
    assert len(_ok(search(project_root=root, k=0))["items"]) == 1  # clamp to 1
    assert len(_ok(search(project_root=root, k=-5))["items"]) == 1
    assert (
        _ok(search(project_root=root, k=51))["count"] <= SEARCH_K_MAX
    )  # clamp, no error
    assert len(_ok(search(project_root=root, k="1"))["items"]) == 1  # numeric string
    _err(search(project_root=root, k="abc"), "VALIDATION_ERROR")
    _err(search(project_root=root, k=True), "VALIDATION_ERROR")


# --------------------------------------------------------------------------- #
# T4 / TS5 - lexical degrade (mode=off) + recency browse
# --------------------------------------------------------------------------- #
def test_ts5_lexical_mode_declared_and_case_insensitive(tmp_path):
    deps, tools, root, _ = make_env(tmp_path)  # embeddings off
    m1, m2, m3 = _seed_corpus(tools, root)
    assert _count(deps, "memory_embeddings") == 0

    # Title match, case-insensitive, NO score on lexical items.
    data = _ok(tools["memory_search"](project_root=root, query="frontend BUILD"))
    assert data["search_mode"] == SEARCH_MODE_LEXICAL
    assert [i["memory_id"] for i in data["items"]] == [m2["memory_id"]]
    assert "score" not in data["items"][0]
    # Content match.
    data = _ok(tools["memory_search"](project_root=root, query="CHECKPOINTS"))
    assert [i["memory_id"] for i in data["items"]] == [m3["memory_id"]]
    # Topic match; live-only by default (m1 is superseded).
    data = _ok(tools["memory_search"](project_root=root, query="sqlite"))
    ids = {i["memory_id"] for i in data["items"]}
    assert m3["memory_id"] in ids and m1["memory_id"] not in ids


def test_ts5_recent_browse_newest_first_with_bounded_preview(tmp_path):
    _deps, tools, root, _ = make_env(tmp_path)
    long_content = "z" * 300
    m1 = _put(tools, root, title="first", content=long_content)
    m2 = _put(tools, root, title="second", content="short")
    m3 = _put(tools, root, title="third", content="short")

    data = _ok(tools["memory_search"](project_root=root))
    assert data["search_mode"] == SEARCH_MODE_RECENT
    assert [i["memory_id"] for i in data["items"]] == [
        m3["memory_id"],
        m2["memory_id"],
        m1["memory_id"],
    ]
    oldest = data["items"][-1]
    assert oldest["content_preview"] == long_content[:CONTENT_PREVIEW_CHARS]
    assert len(oldest["content_preview"]) == CONTENT_PREVIEW_CHARS
    assert "content" not in oldest


# --------------------------------------------------------------------------- #
# T5 / TS6 - supersede: bilateral, linear, atomic
# --------------------------------------------------------------------------- #
def test_ts6_supersede_bilateral_conflict_and_not_found(tmp_path):
    deps, tools, root, _ = make_env(tmp_path)
    m1 = _put(tools, root, title="v1", content="old")
    m2 = _put(tools, root, title="v2", content="new", supersedes=m1["memory_id"])
    assert m2["supersedes"] == m1["memory_id"]
    # Bilateral stamp, same unit of work (BR4).
    old = _ok(tools["memory_get"](project_root=root, memory_id=m1["memory_id"]))
    assert old["superseded_by"] == m2["memory_id"]
    # memory.superseded audit event, metadata-only (FR6/BR5).
    superseded = _events(deps, MEMORY_SUPERSEDED_EVENT)
    assert len(superseded) == 1
    assert "title" not in superseded[0] and "content" not in superseded[0]
    assert superseded[0]["memory_id"] == m2["memory_id"]
    assert superseded[0]["superseded_memory_id"] == m1["memory_id"]
    # Default reads exclude the superseded entry; the opt-in restores it.
    live = _ok(tools["memory_search"](project_root=root))
    assert {i["memory_id"] for i in live["items"]} == {m2["memory_id"]}
    both = _ok(tools["memory_search"](project_root=root, include_superseded=True))
    assert {i["memory_id"] for i in both["items"]} == {
        m1["memory_id"],
        m2["memory_id"],
    }

    # Linear chain: a second supersede of m1 forks -> CONFLICT, nothing persists.
    before = _snapshot(deps)
    error = _err(
        tools["memory_put"](
            project_root=root,
            agent_id="alpha",
            title="v2b",
            content="fork",
            supersedes=m1["memory_id"],
        ),
        "CONFLICT",
    )
    assert error["details"] == {
        "supersedes": m1["memory_id"],
        "superseded_by": m2["memory_id"],
    }
    assert _snapshot(deps) == before

    # Nonexistent target vs cross-workspace target: indistinguishable NOT_FOUND.
    ghost = _err(
        tools["memory_put"](
            project_root=root,
            agent_id="alpha",
            title="x",
            content="x",
            supersedes="mem_missing",
        ),
        "NOT_FOUND",
    )
    other = tmp_path / "project2"
    other.mkdir(exist_ok=True)
    cross = _err(
        tools["memory_put"](
            project_root=str(other),
            agent_id="alpha",
            title="x",
            content="x",
            supersedes=m1["memory_id"],
        ),
        "NOT_FOUND",
    )
    assert set(ghost["details"]) == set(cross["details"]) == {"supersedes"}
    assert _snapshot(deps) == before


# --------------------------------------------------------------------------- #
# T5 / TS7 - memory_get: lean conditional shape + readable history
# --------------------------------------------------------------------------- #
def test_ts7_get_full_shape_conditionals_and_indistinguishable_not_found(tmp_path):
    _deps, tools, root, workspace_id = make_env(tmp_path)
    plain = _put(tools, root, title="plain", content="no optionals")
    rich = _put(
        tools,
        root,
        title="rich",
        content="all optionals",
        topics=["a"],
        source_kind="message",
        source_id="msg_1",
        supersedes=plain["memory_id"],
    )

    base_keys = {
        "memory_id",
        "workspace_id",
        "author_agent_id",
        "title",
        "content",
        "content_bytes",
        "topics",
        "created_at",
    }
    got_rich = _ok(tools["memory_get"](project_root=root, memory_id=rich["memory_id"]))
    assert set(got_rich) == base_keys | {"source_kind", "source_id", "supersedes"}
    assert got_rich["workspace_id"] == workspace_id

    # Superseded entries stay readable by id forever (BR7 - history is the point).
    got_plain = _ok(
        tools["memory_get"](project_root=root, memory_id=plain["memory_id"])
    )
    assert set(got_plain) == base_keys | {"superseded_by"}
    assert got_plain["superseded_by"] == rich["memory_id"]
    assert got_plain["content"] == "no optionals"

    # NOT_FOUND: nonexistent id and cross-workspace id look identical.
    ghost = _err(
        tools["memory_get"](project_root=root, memory_id="mem_missing"), "NOT_FOUND"
    )
    other = tmp_path / "project2"
    other.mkdir(exist_ok=True)
    cross = _err(
        tools["memory_get"](project_root=str(other), memory_id=plain["memory_id"]),
        "NOT_FOUND",
    )
    assert set(ghost["details"]) == set(cross["details"]) == {"memory_id"}
    _err(tools["memory_get"](project_root=root, memory_id=""), "VALIDATION_ERROR")


# --------------------------------------------------------------------------- #
# T6 / TS8 - projection: memory_id promoted on every profile, scoped by type
# --------------------------------------------------------------------------- #
def _raw_event(type_: str, payload: dict) -> dict:
    return {
        "event_id": 42,
        "workspace_id": "ws_x",
        "stream": "workspace",
        "type": type_,
        "payload": payload,
        "actor_agent_id": "alpha",
        "created_at": "2026-01-01T00:00:00Z",
    }


def test_ts8_memory_id_promotion_across_profiles_unit():
    payload = {
        "memory_id": "mem_abc",
        "workspace_id": "ws_x",
        "author_agent_id": "alpha",
        "topics": ["sqlite"],
    }
    for type_ in (MEMORY_CREATED_EVENT, MEMORY_SUPERSEDED_EVENT):
        raw = _raw_event(type_, dict(payload))

        full, omitted, truncated = project_event(raw, "full")
        assert full == raw and omitted == 0 and truncated is False

        summary, _, _ = project_event(raw, "summary")
        assert summary["memory_id"] == "mem_abc"
        assert "payload" not in summary  # metadata via follow_up, not inline
        assert summary["follow_up"]["hint"] == "profile=full"

        default, _, _ = project_event(raw, "default")
        assert default["memory_id"] == "mem_abc"
        # Deduped out of the payload copy ONLY where it was promoted.
        assert "memory_id" not in default["payload"]
        assert default["payload"]["author_agent_id"] == "alpha"
        assert default["payload"]["topics"] == ["sqlite"]
        assert default["workspace_id"] == "ws_x"


def test_ts8_non_memory_event_shapes_stay_intact():
    # A memory_id inside any OTHER event type is NOT promoted (TR5: scoped by
    # type so every pre-existing shape stays byte-identical) and NOT lost.
    raw = _raw_event("message.created", {"memory_id": "mem_x", "note": "n"})
    default, _, _ = project_event(raw, "default")
    assert "memory_id" not in default
    assert default["payload"]["memory_id"] == "mem_x"  # kept inside the payload
    summary, _, _ = project_event(raw, "summary")
    assert "memory_id" not in summary


def test_ts8_event_get_projection_integration(tmp_path):
    _deps, tools, root, _ = make_env(tmp_path)
    m1 = _put(tools, root, title="v1", content="old")
    _put(tools, root, title="v2", content="new", supersedes=m1["memory_id"])

    def page(type_: str, profile: str) -> list[dict]:
        events = _ok(
            tools["event_get"](
                project_root=root,
                agent_id="alpha",
                stream="workspace",
                filters={"type": type_},
                profile=profile,
            )
        )["events"]
        assert events, f"expected at least one {type_} event"
        return events

    for type_ in (MEMORY_CREATED_EVENT, MEMORY_SUPERSEDED_EVENT):
        for item in page(type_, "summary"):
            assert item["memory_id"].startswith("mem_")
            assert "payload" not in item
        for item in page(type_, "default"):
            assert item["memory_id"].startswith("mem_")
            assert "memory_id" not in item.get("payload", {})
        for item in page(type_, "full"):
            assert item["payload"]["memory_id"].startswith("mem_")
            assert "memory_id" not in item  # full is the raw shape: no promotion


# --------------------------------------------------------------------------- #
# T6 / TS9 - trace interop (feature_trace ON: explicit echo + auto-stamp)
# --------------------------------------------------------------------------- #
def test_ts9_trace_explicit_autostamp_and_filters(tmp_path):
    deps, tools, root, workspace_id = make_env(
        tmp_path, extra={"OKTO_NEXUS_FEATURE_TRACE": "true"}
    )
    traced = _put(tools, root, title="traced", content="c", trace_id="trc_manual_i6")
    assert traced["trace_id"] == "trc_manual_i6"
    # No explicit trace + feature ON -> the server stamps a fresh one (D3).
    stamped = _put(tools, root, title="auto", content="c")
    assert stamped["trace_id"].startswith("trc_")

    # MCP filter: the memory.created event is reachable BY trace.
    data = _ok(
        tools["event_get"](
            project_root=root,
            agent_id="alpha",
            stream="workspace",
            filters={"trace_id": "trc_manual_i6"},
        )
    )
    assert len(data["events"]) == 1
    event = data["events"][0]
    assert event["type"] == MEMORY_CREATED_EVENT
    assert event["trace_id"] == "trc_manual_i6"
    assert event["memory_id"] == traced["memory_id"]

    # Supersede INSIDE the trajectory: memory.superseded rides the trace too.
    v2 = _put(
        tools,
        root,
        title="traced v2",
        content="c",
        trace_id="trc_manual_i6",
        supersedes=traced["memory_id"],
    )
    data = _ok(
        tools["event_get"](
            project_root=root,
            agent_id="alpha",
            stream="workspace",
            filters={"trace_id": "trc_manual_i6"},
        )
    )
    assert len(data["events"]) == 3  # created(traced) + created(v2) + superseded
    assert {e["type"] for e in data["events"]} == {
        MEMORY_CREATED_EVENT,
        MEMORY_SUPERSEDED_EVENT,
    }
    assert all(e["trace_id"] == "trc_manual_i6" for e in data["events"])
    # event_wait parity (timeout 0 = immediate snapshot of the backlog).
    waited = _ok(
        tools["event_wait"](
            project_root=root,
            agent_id="alpha",
            stream="workspace",
            filters={"trace_id": "trc_manual_i6"},
            timeout_seconds=0,
        )
    )
    assert [e["event_id"] for e in waited["events"]] == [
        e["event_id"] for e in data["events"]
    ]
    # The get exposes the conditional trace_id too (row-level persistence).
    got = _ok(tools["memory_get"](project_root=root, memory_id=v2["memory_id"]))
    assert got["trace_id"] == "trc_manual_i6"

    # REST filter parity: GET /api/v1/events?trace=...
    client = _client(deps)
    r = client.get(f"/api/v1/events?workspace={workspace_id}&trace=trc_manual_i6")
    assert r.status_code == 200, r.text
    items = r.json()["data"]["items"]
    assert len(items) == 3
    assert all(item["trace_id"] == "trc_manual_i6" for item in items)

    # Rejection is fail-closed while the trace feature is ON.
    _err(
        tools["memory_put"](
            project_root=root,
            agent_id="alpha",
            title="t",
            content="c",
            trace_id="x" * 129,
        ),
        "VALIDATION_ERROR",
    )
    assert _count(deps, "memories") == 3


def test_ts9_trace_flag_off_accepts_and_ignores(tmp_path):
    deps, tools, root, _ = make_env(tmp_path)  # feature_trace defaults OFF
    data = _put(tools, root, title="untraced", content="c", trace_id="trc_ignored")
    assert "trace_id" not in data  # accepted-and-ignored (D4)
    payloads = _events(deps, MEMORY_CREATED_EVENT)
    assert "trace_id" not in payloads[0]


# --------------------------------------------------------------------------- #
# T7 / TS10 - operator REST surface (NOT feature-gated; delete operator-only)
# --------------------------------------------------------------------------- #
def test_ts10_rest_browse_detail_pagination_and_flag_independence(tmp_path):
    deps, tools, root, workspace_id = make_env(tmp_path, embedding="stub")
    m1, m2, m3 = _seed_corpus(tools, root)
    deps.config.feature_memory = False  # the REST surface ignores the gate (FR7)
    client = _client(deps)

    r = client.get(f"/api/v1/memory?workspace={workspace_id}")
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["search_mode"] == SEARCH_MODE_RECENT and data["count"] == 2
    assert [i["memory_id"] for i in data["items"]] == [m3["memory_id"], m2["memory_id"]]
    assert "content_preview" in data["items"][0] and "content" not in data["items"][0]

    # Facets + include_superseded + pagination + fail-closed limit.
    r = client.get(
        f"/api/v1/memory?workspace={workspace_id}&topic=sqlite&include_superseded=true"
    )
    assert {i["memory_id"] for i in r.json()["data"]["items"]} == {
        m1["memory_id"],
        m3["memory_id"],
    }
    r = client.get(
        f"/api/v1/memory?workspace={workspace_id}&author=beta&include_superseded=true"
    )
    assert {i["memory_id"] for i in r.json()["data"]["items"]} == {m2["memory_id"]}
    r = client.get(f"/api/v1/memory?workspace={workspace_id}&limit=1&offset=1")
    assert [i["memory_id"] for i in r.json()["data"]["items"]] == [m2["memory_id"]]
    assert (
        client.get(f"/api/v1/memory?workspace={workspace_id}&limit=999").status_code
        == 200
    )
    r = client.get(f"/api/v1/memory?workspace={workspace_id}&limit=abc")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"

    # q -> the exact tool-mode selection, declared (semantic with the stub).
    exact = f"{m2['title']}\n{m2['content']}"
    r = client.get("/api/v1/memory", params={"workspace": workspace_id, "q": exact})
    data = r.json()["data"]
    assert data["search_mode"] == SEARCH_MODE_SEMANTIC
    assert data["items"][0]["memory_id"] == m2["memory_id"]
    assert "score" in data["items"][0]

    # Detail is FULL; 404 for a ghost id and for a cross-workspace read.
    r = client.get(f"/api/v1/memory/{m3['memory_id']}?workspace={workspace_id}")
    detail = r.json()["data"]
    assert r.status_code == 200 and detail["content"] == m3["content"]
    assert detail["supersedes"] == m1["memory_id"] and "content_bytes" in detail
    assert (
        client.get(f"/api/v1/memory/mem_nope?workspace={workspace_id}").status_code
        == 404
    )
    assert (
        client.get(f"/api/v1/memory/{m3['memory_id']}?workspace=ws_other").status_code
        == 404
    )


def test_ts10_rest_delete_operator_only_cascade_no_event(tmp_path):
    deps, tools, root, workspace_id = make_env(tmp_path, embedding="stub")
    m1 = _put(tools, root, title="v1", content="old")
    m2 = _put(tools, root, title="v2", content="new", supersedes=m1["memory_id"])
    deps.config.feature_memory = False  # curation is NOT gated either (FR8)
    client = _client(deps)
    alpha_key = _issue_key(deps, "alpha")

    # A regular agent key is authenticated but NOT the operator -> 403.
    r = client.delete(
        f"/api/v1/memory/{m1['memory_id']}?workspace={workspace_id}",
        headers={"x-api-key": alpha_key},
    )
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "PERMISSION_DENIED"
    assert _count(deps, "memories") == 2  # nothing removed

    # Operator delete: physical, CASCADE drops the vector, NO event (BR9).
    events_before = _count(deps, "events")
    r = client.delete(f"/api/v1/memory/{m1['memory_id']}?workspace={workspace_id}")
    assert r.status_code == 200 and r.json()["data"]["deleted"] is True
    assert _count(deps, "events") == events_before  # curation is not protocol
    assert _vector_row(deps, m1["memory_id"]) is None  # ON DELETE CASCADE
    assert _count(deps, "memories") == 1
    # Second delete: already gone.
    r = client.delete(f"/api/v1/memory/{m1['memory_id']}?workspace={workspace_id}")
    assert r.status_code == 404
    # The neighbour keeps its dangling pointer (tolerated by design, BR9).
    detail = client.get(
        f"/api/v1/memory/{m2['memory_id']}?workspace={workspace_id}"
    ).json()["data"]
    assert detail["supersedes"] == m1["memory_id"]

    # Loopback local_open (no api key) is the other operator trust path.
    from fastapi.testclient import TestClient

    from okto_nexus.adapters.inbound.http.app import build_app

    loopback = TestClient(build_app(deps), client=("127.0.0.1", 51521))
    r = loopback.delete(f"/api/v1/memory/{m2['memory_id']}?workspace={workspace_id}")
    assert r.status_code == 200 and r.json()["data"]["deleted"] is True
    assert _count(deps, "memories") == 0


def test_ts10_rest_lexical_mode_declared_when_embeddings_off(tmp_path):
    deps, tools, root, workspace_id = make_env(tmp_path)  # embeddings off
    _put(tools, root, title="DB uses WAL", content="Writers serialize.")
    deps.config.feature_memory = False
    client = _client(deps)
    r = client.get(f"/api/v1/memory?workspace={workspace_id}&q=wal")
    data = r.json()["data"]
    assert data["search_mode"] == SEARCH_MODE_LEXICAL
    assert data["count"] == 1 and "score" not in data["items"][0]


# --------------------------------------------------------------------------- #
# T7 / TS11 - the frozen MCP surface contract
# --------------------------------------------------------------------------- #
def test_ts11_surface_revision_ledger_budgets_and_tool_set(tmp_path):
    assert SURFACE_REVISION == 27
    # The growth is ON the approved ledger (AC5 stays green with it counted).
    assert APPROVED_GROWTH["memory_i6"] > 0

    _deps, tools, _root, _ = make_env(tmp_path)
    memory_tools = sorted(name for name in tools if name.startswith("memory"))
    # EXACTLY three verbs; no agent-facing delete/update exists on the surface
    # (correction is supersede; removal is operator REST curation only).
    assert memory_tools == ["memory_get", "memory_put", "memory_search"]
    assert not any(("delete" in n or "update" in n) for n in memory_tools)
    # Inline one-line docs within the house budget (<=200 chars each).
    for name in memory_tools:
        doc = inspect.getdoc(tools[name])
        assert doc and len(doc) <= 200, f"{name} doc budget: {len(doc or '')}"
    # Every _P_* parameter description: single-line, <=200 chars (AC10).
    import okto_nexus.adapters.inbound.mcp.tools.memory as memory_module

    for name, value in vars(memory_module).items():
        if name.startswith("_P_"):
            assert isinstance(value, str) and "\n" not in value, name
            assert len(value) <= 200, f"{name} budget: {len(value)}"

    # Declared TS11 drift, locked as a decision: NO memory reference resource -
    # the three inline descriptions are self-sufficient (SURFACE_REVISION 23
    # comment records the rationale; adding a URI later is a deliberate bump).
    assert not any("memory" in uri for uri in resource_uris())

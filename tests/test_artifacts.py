"""Tests for the artifacts slice (artifact_put / artifact_get).

Hexagonal unit/integration tests: the application service runs over the real
SQLite artifact repo and the real workspace file store (via ``migrated_factory``)
while ports owned by OTHER slices are faked - the identity ``WorkspaceRepo`` is a
local fake that inserts the FK row, and the Event Log ``EventEmitter`` is a local
double that appends to the real ``events`` table inside the same uow (so
atomicity and the monotonic ``event_id`` can be exercised without depending on
the Event Log slice's concrete implementation).

Covers: the canonical error catalogue (WORKSPACE_REQUIRED/UNRESOLVED,
VALIDATION_ERROR, CONTENT_TOO_LARGE, PATH_OUTSIDE_WORKSPACE, NOT_FOUND), the
64 KB inclusive boundary (incl. a multibyte char on the boundary), JSON
well-formedness, path traversal / absolute-external / symlink-escape
containment, same-uow atomicity + rollback, server-assigned immutable ids,
cross-workspace isolation, monotonic event_id, the MCP tool envelope, and
concurrent writers under the WAL single-writer.
"""

from __future__ import annotations

import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from okto_nexus.adapters.inbound.mcp.tools.artifacts import build_service, register
from okto_nexus.adapters.outbound.file.store import WorkspaceFileStore, _is_contained
from okto_nexus.adapters.outbound.sqlite.artifacts_repo import SqliteArtifactRepo
from okto_nexus.application.artifacts import ArtifactService
from okto_nexus.application.ports import Repos
from okto_nexus.domain.artifacts import (
    ARTIFACT_TYPES,
    ensure_well_formed_json,
    ensure_within_inline_limit,
    normalize_artifact_type,
)
from okto_nexus.domain.ids import resolve_workspace_id
from okto_nexus.domain.models import Workspace
from okto_nexus.errors import ErrorCode, OktoNexusError


# --------------------------------------------------------------------------- #
# Test doubles & helpers
# --------------------------------------------------------------------------- #
class StubClock:
    """Deterministic clock implementing the Clock port."""

    def __init__(self, iso: str = "2026-06-07T00:00:00Z") -> None:
        self._iso = iso

    def now_iso(self) -> str:
        return self._iso

    def now_epoch(self) -> float:
        return 1_780_000_000.0

    def set(self, iso: str) -> None:
        self._iso = iso


class FakeWorkspaceRepo:
    """Fake identity WorkspaceRepo that inserts the FK row (real workspaces table)."""

    def __init__(self) -> None:
        self.upserts: list[str] = []
        self._lock = threading.Lock()

    def upsert(
        self,
        uow,
        *,
        workspace_id,
        display_name=None,
        root_realpath=None,
        last_seen_at=None,
    ) -> Workspace:
        created = last_seen_at or "2026-06-07T00:00:00Z"
        uow.connection.execute(
            """
            INSERT INTO workspaces
                (workspace_id, display_name, root_realpath, created_at, last_seen_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(workspace_id) DO UPDATE SET
                last_seen_at = excluded.last_seen_at,
                root_realpath = COALESCE(excluded.root_realpath, workspaces.root_realpath)
            """,
            (workspace_id, display_name, root_realpath, created, last_seen_at),
        )
        with self._lock:
            self.upserts.append(workspace_id)
        return Workspace(
            workspace_id=workspace_id,
            created_at=created,
            display_name=display_name,
            root_realpath=root_realpath,
            last_seen_at=last_seen_at,
        )

    def get(self, uow, workspace_id) -> Workspace | None:
        cur = uow.connection.execute(
            "SELECT workspace_id, display_name, root_realpath, created_at, last_seen_at "
            "FROM workspaces WHERE workspace_id = ?",
            (workspace_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return Workspace(
            workspace_id=row["workspace_id"],
            created_at=row["created_at"],
            display_name=row["display_name"],
            root_realpath=row["root_realpath"],
            last_seen_at=row["last_seen_at"],
        )


class RecordingEmitter:
    """Fake EventEmitter that writes into the real events table within the uow."""

    def __init__(self) -> None:
        self.events: list[dict] = []
        self._lock = threading.Lock()

    def emit(
        self,
        uow,
        *,
        workspace_id,
        stream,
        type,
        payload=None,
        actor_agent_id=None,
        visibility=None,
        target=None,
    ) -> int:
        cur = uow.connection.execute(
            """
            INSERT INTO events
                (workspace_id, stream, type, actor_agent_id, payload,
                 visibility, target, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                workspace_id,
                stream,
                type,
                actor_agent_id,
                json.dumps(payload) if payload is not None else None,
                visibility,
                target,
                (payload or {}).get("created_at") or "2026-06-07T00:00:00Z",
            ),
        )
        eid = int(cur.lastrowid)
        with self._lock:
            self.events.append(
                {
                    "event_id": eid,
                    "workspace_id": workspace_id,
                    "stream": stream,
                    "type": type,
                    "payload": payload,
                    "target": target,
                }
            )
        return eid


class BoomEmitter:
    """Emitter that fails during emission (after the artifact insert)."""

    def emit(self, uow, **kwargs) -> int:
        raise RuntimeError("simulated event-log failure")


class FakeServer:
    """Captures FastMCP-style ``@server.tool()`` registrations by name."""

    def __init__(self) -> None:
        self.tools: dict = {}

    def tool(self, *args, **kwargs):
        def deco(fn):
            self.tools[fn.__name__] = fn
            return fn

        return deco


def make_service(factory, config, clock, emitter=None, files=None, artifacts=None):
    return ArtifactService(
        connection_factory=factory,
        artifacts=artifacts or SqliteArtifactRepo(clock),
        workspaces=FakeWorkspaceRepo(),
        files=files or WorkspaceFileStore(),
        clock=clock,
        config=config,
        event_emitter=emitter,
    )


def make_deps(factory, config, clock, emitter=None):
    return SimpleNamespace(
        config=config,
        connection_factory=factory,
        clock=clock,
        repos=Repos(),
        event_emitter=emitter,
    )


def count(factory, table: str) -> int:
    conn = factory.get_connection()
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        conn.close()


def event_ids(factory, type_="artifact.created") -> list[int]:
    conn = factory.get_connection()
    try:
        rows = conn.execute(
            "SELECT event_id FROM events WHERE type = ? ORDER BY event_id",
            (type_,),
        ).fetchall()
        return [r[0] for r in rows]
    finally:
        conn.close()


def retry_db(fn, attempts: int = 40, delay: float = 0.02):
    """Retry on transient DB_ERROR (WAL busy under contention)."""
    last = None
    for _ in range(attempts):
        try:
            return fn()
        except OktoNexusError as exc:
            if exc.code != ErrorCode.DB_ERROR.value:
                raise
            last = exc
            time.sleep(delay)
    raise last  # pragma: no cover


def mkroot(tmp_path, name="proj"):
    p = tmp_path / name
    p.mkdir()
    return str(p)


# --------------------------------------------------------------------------- #
# Pure domain helpers
# --------------------------------------------------------------------------- #
def test_artifact_types_whitelist():
    assert ARTIFACT_TYPES == {"file", "text", "json", "markdown"}
    assert normalize_artifact_type("JSON") == "json"
    assert normalize_artifact_type("  markdown ") == "markdown"


@pytest.mark.parametrize("bad", [None, "", "  ", "zip", "binary", 5])
def test_normalize_artifact_type_rejects(bad):
    with pytest.raises(OktoNexusError) as ei:
        normalize_artifact_type(bad)
    assert ei.value.code == ErrorCode.VALIDATION_ERROR.value


def test_ensure_within_inline_limit_boundary():
    assert ensure_within_inline_limit("x" * 10, 65536) == 10
    assert ensure_within_inline_limit("a" * 65536, 65536) == 65536  # inclusive
    with pytest.raises(OktoNexusError) as ei:
        ensure_within_inline_limit("a" * 65537, 65536)
    assert ei.value.code == ErrorCode.CONTENT_TOO_LARGE.value
    assert "max_inline_bytes" in (ei.value.details or {})


def test_ensure_well_formed_json():
    ensure_well_formed_json('{"a": 1, "b": [1, 2]}')  # no raise
    with pytest.raises(OktoNexusError) as ei:
        ensure_well_formed_json("{not json}")
    assert ei.value.code == ErrorCode.VALIDATION_ERROR.value


# --------------------------------------------------------------------------- #
# FileStore containment unit tests
# --------------------------------------------------------------------------- #
def test_file_store_resolve_contained(tmp_path):
    root = mkroot(tmp_path)
    fs = WorkspaceFileStore()
    resolved = fs.resolve(root, os.path.join("sub", "file.txt"))
    assert _is_contained(os.path.realpath(root), resolved)
    assert resolved == os.path.join(os.path.realpath(root), "sub", "file.txt")


def test_file_store_resolve_traversal_rejected(tmp_path):
    root = mkroot(tmp_path)
    fs = WorkspaceFileStore()
    with pytest.raises(OktoNexusError) as ei:
        fs.resolve(root, os.path.join("..", "outside.txt"))
    assert ei.value.code == ErrorCode.PATH_OUTSIDE_WORKSPACE.value


def test_file_store_resolve_absolute_external_rejected(tmp_path):
    root = mkroot(tmp_path)
    outside = tmp_path / "elsewhere" / "x.txt"
    fs = WorkspaceFileStore()
    with pytest.raises(OktoNexusError) as ei:
        fs.resolve(root, str(outside))
    assert ei.value.code == ErrorCode.PATH_OUTSIDE_WORKSPACE.value


# --------------------------------------------------------------------------- #
# artifact_put: workspace resolution (FR0 / AC0 / AC1)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("bad", [None, "", "   "])
def test_put_workspace_required(migrated_factory, tmp_config, bad):
    svc = make_service(migrated_factory, tmp_config, StubClock(), emitter=RecordingEmitter())
    with pytest.raises(OktoNexusError) as ei:
        svc.artifact_put(project_root=bad, artifact_type="text", content="hi")
    assert ei.value.code == ErrorCode.WORKSPACE_REQUIRED.value
    assert count(migrated_factory, "artifacts") == 0


def test_put_workspace_unresolved(migrated_factory, tmp_config, tmp_path):
    svc = make_service(migrated_factory, tmp_config, StubClock(), emitter=RecordingEmitter())
    missing = str(tmp_path / "nope" / "child")  # absolute, nonexistent
    with pytest.raises(OktoNexusError) as ei:
        svc.artifact_put(project_root=missing, artifact_type="text", content="hi")
    assert ei.value.code == ErrorCode.WORKSPACE_UNRESOLVED.value
    assert count(migrated_factory, "artifacts") == 0


# --------------------------------------------------------------------------- #
# artifact_put: input validation (FR1/FR2/FR5 -> AC2/AC3/AC6)
# --------------------------------------------------------------------------- #
def test_put_requires_path_or_content(migrated_factory, tmp_config, tmp_path):
    svc = make_service(migrated_factory, tmp_config, StubClock(), emitter=RecordingEmitter())
    root = mkroot(tmp_path)
    with pytest.raises(OktoNexusError) as ei:
        svc.artifact_put(project_root=root, artifact_type="text")
    assert ei.value.code == ErrorCode.VALIDATION_ERROR.value
    assert count(migrated_factory, "artifacts") == 0


def test_put_invalid_artifact_type(migrated_factory, tmp_config, tmp_path):
    svc = make_service(migrated_factory, tmp_config, StubClock(), emitter=RecordingEmitter())
    root = mkroot(tmp_path)
    with pytest.raises(OktoNexusError) as ei:
        svc.artifact_put(project_root=root, artifact_type="zip", content="data")
    assert ei.value.code == ErrorCode.VALIDATION_ERROR.value
    assert count(migrated_factory, "artifacts") == 0


def test_put_json_malformed_rejected(migrated_factory, tmp_config, tmp_path):
    svc = make_service(migrated_factory, tmp_config, StubClock(), emitter=RecordingEmitter())
    root = mkroot(tmp_path)
    with pytest.raises(OktoNexusError) as ei:
        svc.artifact_put(project_root=root, artifact_type="json", content="{nope}")
    assert ei.value.code == ErrorCode.VALIDATION_ERROR.value
    assert count(migrated_factory, "artifacts") == 0


def test_put_json_wellformed_persists(migrated_factory, tmp_config, tmp_path):
    svc = make_service(migrated_factory, tmp_config, StubClock(), emitter=RecordingEmitter())
    root = mkroot(tmp_path)
    out = svc.artifact_put(
        project_root=root, artifact_type="json", content='{"k": [1, 2, 3]}'
    )
    assert out["stored"] == "inline"
    assert out["artifact_type"] == "json"
    assert count(migrated_factory, "artifacts") == 1


# --------------------------------------------------------------------------- #
# artifact_put: 64KB inline boundary (FR3/FR4 -> AC4/AC5)
# --------------------------------------------------------------------------- #
def test_put_content_too_large(migrated_factory, tmp_config, tmp_path):
    svc = make_service(migrated_factory, tmp_config, StubClock(), emitter=RecordingEmitter())
    root = mkroot(tmp_path)
    content = "a" * 65537  # 65537 bytes UTF-8
    with pytest.raises(OktoNexusError) as ei:
        svc.artifact_put(project_root=root, artifact_type="text", content=content)
    assert ei.value.code == ErrorCode.CONTENT_TOO_LARGE.value
    details = ei.value.details or {}
    assert details.get("max_inline_bytes") == 65536
    assert "file" in details.get("hint", "").lower()
    assert count(migrated_factory, "artifacts") == 0
    assert count(migrated_factory, "events") == 0


def test_put_content_boundary_inclusive_multibyte(migrated_factory, tmp_config, tmp_path):
    svc = make_service(migrated_factory, tmp_config, StubClock(), emitter=RecordingEmitter())
    root = mkroot(tmp_path)
    # Exactly 65536 bytes, ending in a whole 3-byte char (no partial break).
    content = "x" * (65536 - 3) + "€"  # '€' is 3 UTF-8 bytes
    assert len(content.encode("utf-8")) == 65536
    out = svc.artifact_put(project_root=root, artifact_type="text", content=content)
    assert out["stored"] == "inline"
    assert out["size_bytes"] == 65536
    assert count(migrated_factory, "artifacts") == 1


# --------------------------------------------------------------------------- #
# artifact_put: path containment (FR6 -> AC8/AC9/AC10/AC11)
# --------------------------------------------------------------------------- #
def test_put_path_traversal_rejected(migrated_factory, tmp_config, tmp_path):
    svc = make_service(migrated_factory, tmp_config, StubClock(), emitter=RecordingEmitter())
    root = mkroot(tmp_path)
    with pytest.raises(OktoNexusError) as ei:
        svc.artifact_put(
            project_root=root, artifact_type="file", path="../outside.txt"
        )
    assert ei.value.code == ErrorCode.PATH_OUTSIDE_WORKSPACE.value
    assert count(migrated_factory, "artifacts") == 0


def test_put_path_absolute_external_rejected(migrated_factory, tmp_config, tmp_path):
    svc = make_service(migrated_factory, tmp_config, StubClock(), emitter=RecordingEmitter())
    root = mkroot(tmp_path)
    external = str(tmp_path / "external_dir" / "secret.txt")
    with pytest.raises(OktoNexusError) as ei:
        svc.artifact_put(project_root=root, artifact_type="file", path=external)
    assert ei.value.code == ErrorCode.PATH_OUTSIDE_WORKSPACE.value
    assert count(migrated_factory, "artifacts") == 0


def test_put_path_symlink_escape_rejected(migrated_factory, tmp_config, tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("classified", encoding="utf-8")
    link = root / "escape"
    try:
        os.symlink(str(outside), str(link), target_is_directory=True)
    except (OSError, NotImplementedError, AttributeError):
        pytest.skip("symlink creation not permitted in this environment")

    svc = make_service(migrated_factory, tmp_config, StubClock(), emitter=RecordingEmitter())
    with pytest.raises(OktoNexusError) as ei:
        svc.artifact_put(
            project_root=str(root),
            artifact_type="file",
            path=os.path.join("escape", "secret.txt"),
        )
    assert ei.value.code == ErrorCode.PATH_OUTSIDE_WORKSPACE.value
    assert count(migrated_factory, "artifacts") == 0


def test_put_path_contained_ok(migrated_factory, tmp_config, tmp_path):
    svc = make_service(migrated_factory, tmp_config, StubClock(), emitter=RecordingEmitter())
    root = tmp_path / "proj"
    root.mkdir()
    (root / "docs").mkdir()
    (root / "docs" / "readme.md").write_text("hello world", encoding="utf-8")

    out = svc.artifact_put(
        project_root=str(root),
        artifact_type="file",
        path=os.path.join("docs", "readme.md"),
    )
    assert out["stored"] == "path"
    expected = os.path.join(os.path.realpath(str(root)), "docs", "readme.md")
    assert out["path"] == expected
    assert out["size_bytes"] == len("hello world".encode("utf-8"))
    assert count(migrated_factory, "artifacts") == 1


# --------------------------------------------------------------------------- #
# artifact_put: atomicity, ids, rollback (FR7/FR8/FR12 -> AC12/AC13/AC14)
# --------------------------------------------------------------------------- #
def test_put_atomic_row_and_event(migrated_factory, tmp_config, tmp_path):
    clock = StubClock("2026-06-07T12:00:00Z")
    emitter = RecordingEmitter()
    svc = make_service(migrated_factory, tmp_config, clock, emitter=emitter)
    root = mkroot(tmp_path)

    out = svc.artifact_put(project_root=root, artifact_type="text", content="payload")
    assert set(out) == {
        "artifact_id",
        "workspace_id",
        "artifact_type",
        "stored",
        "size_bytes",
        "created_at",
    }
    assert out["workspace_id"] == resolve_workspace_id(root)
    assert out["created_at"] == "2026-06-07T12:00:00Z"
    assert count(migrated_factory, "artifacts") == 1
    assert count(migrated_factory, "events") == 1

    assert len(emitter.events) == 1
    ev = emitter.events[-1]
    assert ev["type"] == "artifact.created"
    assert ev["target"] == out["artifact_id"]
    payload = ev["payload"]
    for key in ("workspace_id", "artifact_id", "artifact_type", "size_bytes", "created_at"):
        assert key in payload
    assert payload["artifact_id"] == out["artifact_id"]


def test_put_rollback_on_emit_failure(migrated_factory, tmp_config, tmp_path):
    svc = make_service(migrated_factory, tmp_config, StubClock(), emitter=BoomEmitter())
    root = mkroot(tmp_path)
    with pytest.raises(RuntimeError):
        svc.artifact_put(project_root=root, artifact_type="text", content="data")
    # The artifact insert and the (failed) event are both rolled back atomically.
    assert count(migrated_factory, "artifacts") == 0
    assert count(migrated_factory, "events") == 0


def test_put_repeated_identical_distinct_ids(migrated_factory, tmp_config, tmp_path):
    svc = make_service(migrated_factory, tmp_config, StubClock(), emitter=RecordingEmitter())
    root = mkroot(tmp_path)
    a = svc.artifact_put(project_root=root, artifact_type="text", content="same")
    b = svc.artifact_put(project_root=root, artifact_type="text", content="same")
    assert a["artifact_id"] != b["artifact_id"]
    assert count(migrated_factory, "artifacts") == 2


# --------------------------------------------------------------------------- #
# artifact_get (FR9/FR10/FR11 -> AC15/AC16/AC17/AC18)
# --------------------------------------------------------------------------- #
def test_get_inline_roundtrip(migrated_factory, tmp_config, tmp_path):
    svc = make_service(migrated_factory, tmp_config, StubClock(), emitter=RecordingEmitter())
    root = mkroot(tmp_path)
    put = svc.artifact_put(project_root=root, artifact_type="markdown", content="# Title")

    got = svc.artifact_get(project_root=root, artifact_id=put["artifact_id"])
    assert got["stored"] == "inline"
    assert got["content"] == "# Title"
    assert got["size_bytes"] == len("# Title".encode("utf-8"))
    assert "path" not in got
    assert got["metadata"] == {}


def test_get_not_found(migrated_factory, tmp_config, tmp_path):
    svc = make_service(migrated_factory, tmp_config, StubClock(), emitter=RecordingEmitter())
    root = mkroot(tmp_path)
    # Establish the workspace so resolution succeeds, then query a ghost id.
    svc.artifact_put(project_root=root, artifact_type="text", content="x")
    with pytest.raises(OktoNexusError) as ei:
        svc.artifact_get(project_root=root, artifact_id="art_does_not_exist")
    assert ei.value.code == ErrorCode.NOT_FOUND.value


def test_get_missing_artifact_id_validation(migrated_factory, tmp_config, tmp_path):
    svc = make_service(migrated_factory, tmp_config, StubClock(), emitter=RecordingEmitter())
    root = mkroot(tmp_path)
    with pytest.raises(OktoNexusError) as ei:
        svc.artifact_get(project_root=root, artifact_id="  ")
    assert ei.value.code == ErrorCode.VALIDATION_ERROR.value


def test_get_cross_workspace_isolation(migrated_factory, tmp_config, tmp_path):
    svc = make_service(migrated_factory, tmp_config, StubClock(), emitter=RecordingEmitter())
    root_a = mkroot(tmp_path, "A")
    root_b = mkroot(tmp_path, "B")
    put = svc.artifact_put(project_root=root_a, artifact_type="text", content="secret-A")

    # Same artifact_id, but resolved from workspace B -> NOT_FOUND, no leak.
    with pytest.raises(OktoNexusError) as ei:
        svc.artifact_get(project_root=root_b, artifact_id=put["artifact_id"])
    assert ei.value.code == ErrorCode.NOT_FOUND.value
    assert (ei.value.details or {}).get("artifact_id") == put["artifact_id"]
    assert "secret-A" not in json.dumps(ei.value.to_error_dict())


def test_get_path_returns_no_inline_bytes(migrated_factory, tmp_config, tmp_path):
    svc = make_service(migrated_factory, tmp_config, StubClock(), emitter=RecordingEmitter())
    root = tmp_path / "proj"
    root.mkdir()
    (root / "data.bin").write_text("ON DISK BYTES", encoding="utf-8")
    put = svc.artifact_put(project_root=str(root), artifact_type="file", path="data.bin")

    got = svc.artifact_get(project_root=str(root), artifact_id=put["artifact_id"])
    assert got["stored"] == "path"
    assert "content" not in got
    assert got["path"].endswith("data.bin")
    assert "ON DISK BYTES" not in json.dumps(got)  # bytes never inlined


def test_metadata_roundtrip(migrated_factory, tmp_config, tmp_path):
    svc = make_service(migrated_factory, tmp_config, StubClock(), emitter=RecordingEmitter())
    root = mkroot(tmp_path)
    put = svc.artifact_put(
        project_root=root,
        artifact_type="text",
        content="hi",
        metadata={"author": "agent-1", "tags": ["a", "b"]},
    )
    got = svc.artifact_get(project_root=root, artifact_id=put["artifact_id"])
    assert got["metadata"] == {"author": "agent-1", "tags": ["a", "b"]}


# --------------------------------------------------------------------------- #
# Event monotonicity (FR12 -> AC19)
# --------------------------------------------------------------------------- #
def test_event_id_monotonic(migrated_factory, tmp_config, tmp_path):
    svc = make_service(migrated_factory, tmp_config, StubClock(), emitter=RecordingEmitter())
    root = mkroot(tmp_path)
    svc.artifact_put(project_root=root, artifact_type="text", content="one")
    svc.artifact_put(project_root=root, artifact_type="text", content="two")
    ids = event_ids(migrated_factory)
    assert len(ids) == 2
    assert ids[0] < ids[1]  # global, monotonically increasing INTEGER
    assert all(isinstance(i, int) for i in ids)


# --------------------------------------------------------------------------- #
# MCP tool registration + canonical envelope
# --------------------------------------------------------------------------- #
def test_register_tools_and_envelope(migrated_factory, tmp_config, tmp_path):
    deps = make_deps(migrated_factory, tmp_config, StubClock(), emitter=RecordingEmitter())
    server = FakeServer()
    register(server, deps)
    assert set(server.tools) == {"artifact_put", "artifact_get"}
    assert deps.repos.artifacts is not None
    assert deps.repos.workspaces is not None
    assert deps.repos.files is not None

    root = mkroot(tmp_path)
    put = server.tools["artifact_put"](
        project_root=root, artifact_type="text", content="hello"
    )
    assert put["ok"] is True
    aid = put["data"]["artifact_id"]

    got = server.tools["artifact_get"](project_root=root, artifact_id=aid)
    assert got["ok"] is True
    assert got["data"]["content"] == "hello"

    # Failures are surfaced as envelopes, never raised.
    missing_ws = server.tools["artifact_put"](
        project_root="", artifact_type="text", content="x"
    )
    assert missing_ws["ok"] is False
    assert missing_ws["error"]["code"] == "WORKSPACE_REQUIRED"

    not_found = server.tools["artifact_get"](project_root=root, artifact_id="ghost")
    assert not_found["ok"] is False
    assert not_found["error"]["code"] == "NOT_FOUND"

    too_big = server.tools["artifact_put"](
        project_root=root, artifact_type="text", content="a" * 65537
    )
    assert too_big["ok"] is False
    assert too_big["error"]["code"] == "CONTENT_TOO_LARGE"


def test_build_service_reuses_existing_repos(migrated_factory, tmp_config):
    deps = make_deps(migrated_factory, tmp_config, StubClock())
    existing = SqliteArtifactRepo(deps.clock)
    deps.repos.artifacts = existing
    build_service(deps)
    assert deps.repos.artifacts is existing  # not overwritten
    assert deps.repos.workspaces is not None  # filled in
    assert deps.repos.files is not None


# --------------------------------------------------------------------------- #
# Concurrency: WAL single-writer serialisation (AC20)
# --------------------------------------------------------------------------- #
def test_concurrent_writers_distinct_ids_and_events(migrated_factory, tmp_config, tmp_path):
    emitter = RecordingEmitter()
    svc = make_service(migrated_factory, tmp_config, StubClock(), emitter=emitter)
    root = mkroot(tmp_path)
    n = 12
    results: list[str] = []
    lock = threading.Lock()
    barrier = threading.Barrier(n)

    def worker(i):
        barrier.wait()
        out = retry_db(
            lambda: svc.artifact_put(
                project_root=root, artifact_type="text", content=f"payload-{i}"
            )
        )
        with lock:
            results.append(out["artifact_id"])

    with ThreadPoolExecutor(max_workers=n) as ex:
        futures = [ex.submit(worker, i) for i in range(n)]
        for f in futures:
            f.result()

    assert len(results) == n
    assert len(set(results)) == n  # distinct artifact_id, no PK collision
    assert count(migrated_factory, "artifacts") == n  # no lost writes

    ids = event_ids(migrated_factory)
    assert len(ids) == n  # one event per put, none lost/duplicated
    assert len(set(ids)) == n  # distinct event_id
    assert ids == sorted(ids)  # monotonic under serialised writes

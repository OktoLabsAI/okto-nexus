"""Cross-implementation CONTRACT tests for the ``EventRepo`` port (M2).

The M2 root cause was FAKE-DRIFT: the unit-test fake implemented
``list_after(stream=None) == all streams`` while the real SQLite adapter
compiled an unconditional ``WHERE stream = ?`` (``stream = NULL`` matches
nothing), so the fake-backed suite stayed green while shared.md's Recent
Events was ALWAYS empty in production.

Structural defense: every test here is parametrized to run the SAME scenario
against BOTH implementations - the fake the shared.md unit tests rely on
(imported from ``test_shared_md``, not a copy) and the real
``SqliteEventRepo`` over a migrated database. If either side ever diverges on
the port semantics (all-streams selection, single-stream filtering, cursor
paging, or the fail-closed emit vocabulary), this file fails loudly instead of
the drift shipping.
"""

from __future__ import annotations

import pytest

from okto_nexus.adapters.outbound.sqlite.events_repo import SqliteEventRepo
from okto_nexus.adapters.outbound.sqlite.identity_repo import SqliteWorkspaceRepo
from okto_nexus.errors import ErrorCode, OktoNexusError

from test_shared_md import (
    WS_A,
    FakeConnectionFactory,
    FakeEventRepo,
    StubClock,
)


class _Backend:
    """One (repo, unit-of-work factory) pair the contract runs against."""

    def __init__(self, name: str, repo, uow_factory) -> None:
        self.name = name
        self.repo = repo
        self.uow = uow_factory


@pytest.fixture(params=["fake", "sqlite"])
def backend(request, migrated_factory) -> _Backend:
    """The SAME contract scenarios run against the fake and the real adapter."""
    if request.param == "fake":
        return _Backend(
            "fake", FakeEventRepo([]), FakeConnectionFactory().unit_of_work
        )
    # Real adapter: seed the workspaces row (events.workspace_id is a FK).
    with migrated_factory.unit_of_work() as uow:
        SqliteWorkspaceRepo(StubClock()).upsert(
            uow, workspace_id=WS_A, root_realpath="/tmp/proj"
        )
    return _Backend("sqlite", SqliteEventRepo(StubClock()), migrated_factory.unit_of_work)


def _append(backend: _Backend, **kwargs) -> int:
    merged = dict(workspace_id=WS_A, stream="workspace", type="evt")
    merged.update(kwargs)
    with backend.uow() as uow:
        return backend.repo.append(uow, **merged)


def _list(backend: _Backend, **kwargs):
    merged = dict(workspace_id=WS_A, stream=None)
    merged.update(kwargs)
    with backend.uow() as uow:
        return backend.repo.list_after(uow, **merged)


# --------------------------------------------------------------------------- #
# list_after: stream=None == ALL streams; a str stream filters (the M2 drift)
# --------------------------------------------------------------------------- #
def test_contract_list_after_stream_none_selects_all_streams(backend):
    _append(backend, stream="workspace", type="w.1")
    _append(backend, stream="task", type="t.1")
    _append(backend, stream="handoff", type="h.1")
    _append(backend, stream="agent", type="a.1")

    rows = _list(backend, stream=None)
    assert [e.type for e in rows] == ["w.1", "t.1", "h.1", "a.1"]
    ids = [e.event_id for e in rows]
    assert ids == sorted(ids)  # oldest-first, ascending event_id


def test_contract_list_after_default_stream_is_all_streams(backend):
    # The port signature defaults ``stream=None``: omitting it == all streams.
    _append(backend, stream="workspace", type="w.1")
    _append(backend, stream="task", type="t.1")
    with backend.uow() as uow:
        rows = backend.repo.list_after(uow, workspace_id=WS_A)
    assert [e.type for e in rows] == ["w.1", "t.1"]


def test_contract_list_after_single_stream_filters(backend):
    _append(backend, stream="workspace", type="w.1")
    _append(backend, stream="task", type="t.1")
    _append(backend, stream="task", type="t.2")

    assert [e.type for e in _list(backend, stream="task")] == ["t.1", "t.2"]
    assert [e.type for e in _list(backend, stream="workspace")] == ["w.1"]
    assert _list(backend, stream="handoff") == []


def test_contract_list_after_cursor_and_limit_with_stream_none(backend):
    ids = [
        _append(backend, stream=s, type=f"e{i}")
        for i, s in enumerate(("workspace", "task", "handoff", "agent", "workspace"))
    ]

    after = _list(backend, stream=None, cursor=ids[1])
    assert [e.event_id for e in after] == ids[2:]  # strictly event_id > cursor

    page = _list(backend, stream=None, limit=2)
    assert [e.event_id for e in page] == ids[:2]  # bounded, oldest-first


def test_contract_list_after_is_workspace_scoped_with_stream_none(backend):
    other_ws = "f" * 64
    if backend.name == "sqlite":  # FK parent for the second workspace
        with backend.uow() as uow:
            SqliteWorkspaceRepo(StubClock()).upsert(
                uow, workspace_id=other_ws, root_realpath="/tmp/other"
            )
    _append(backend, type="mine")
    _append(backend, workspace_id=other_ws, type="theirs")

    rows = _list(backend, stream=None)
    assert [e.type for e in rows] == ["mine"]  # all-streams never crosses workspaces


# --------------------------------------------------------------------------- #
# append/emit: fail-closed vocabulary (garbage never persists on EITHER side)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "bad_kwargs",
    [
        {"stream": "session"},  # the exact identity-slice production bug
        {"stream": ""},
        {"stream": None},
        {"visibility": "workspace"},  # the exact identity-slice production bug
        {"visibility": "loud"},
        {"type": ""},
        {"type": None},
    ],
)
def test_contract_append_rejects_out_of_vocabulary(backend, bad_kwargs):
    with pytest.raises(OktoNexusError) as ei:
        _append(backend, **bad_kwargs)
    assert ei.value.code == ErrorCode.INTERNAL_ERROR.value
    assert _list(backend, stream=None) == []  # fail-closed: nothing persisted


@pytest.mark.parametrize("visibility", [None, "public", "eligible", "private"])
def test_contract_append_accepts_canonical_visibilities(backend, visibility):
    eid = _append(backend, visibility=visibility)
    rows = _list(backend, stream=None)
    assert [e.event_id for e in rows] == [eid]
    assert rows[0].visibility == visibility
    assert rows[0].stream == "workspace" and rows[0].type == "evt"


# --------------------------------------------------------------------------- #
# HandoffRepo port: the Protocol must mirror the adapter (wave-1 integration).
# transition_claimed/reject_open were added to the adapter and called by
# application/handoff.py; if either side drifts (method dropped, parameter
# renamed, default removed) this fails instead of the mismatch shipping.
# --------------------------------------------------------------------------- #
def test_contract_handoff_repo_adapter_satisfies_protocol():
    import inspect

    from okto_nexus.adapters.outbound.sqlite.handoff_repo import SqliteHandoffRepo
    from okto_nexus.application.ports import HandoffRepo

    adapter = SqliteHandoffRepo(StubClock())
    assert isinstance(adapter, HandoffRepo)  # runtime_checkable presence

    protocol_methods = [
        name
        for name, member in vars(HandoffRepo).items()
        if not name.startswith("_") and callable(member)
    ]
    assert {"transition_claimed", "reject_open"} <= set(protocol_methods)

    for name in protocol_methods:
        port_params = inspect.signature(getattr(HandoffRepo, name)).parameters
        impl_params = inspect.signature(
            getattr(SqliteHandoffRepo, name)
        ).parameters
        # Call-compatibility contract: same parameter names, kinds and
        # defaults (annotations are documentation, not the wire contract).
        assert [
            (p.name, p.kind, p.default) for p in port_params.values()
        ] == [
            (p.name, p.kind, p.default) for p in impl_params.values()
        ], f"HandoffRepo.{name} signature drifted between port and adapter"

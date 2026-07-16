"""Replay/export application service (spec c7c1f834, I8).

``ReplayExportService`` turns a workspace's event log into the NDJSON replay
stream: a leading manifest line followed by one raw event per line, ordered by
``event_id`` ASC. It is the SHARED producer behind both export vias — the CLI
``admin export`` and the REST download — so their output is byte-identical by
construction (the bytes come from the one canonical serializer in
:mod:`okto_nexus.domain.replay`).

Layer discipline: this service is gate-agnostic (the ``feature_replay`` opt-in
and operator gate live in the REST adapter; the CLI is intentionally
ungated — decision D3) and IO-light — it takes an already-open read
``UnitOfWork`` and reads through the operator-facing observability port
(``events_page`` -> ``events_after``), which returns EVERY event of the
workspace with NO per-agent visibility filter (decision D4; ``event_get`` would
corrupt the trace). Ports + stdlib + domain only (import boundary enforced).

The manifest is emitted FIRST but reports the drained ``event_count`` and
``event_id`` range, so the whole slice is materialised before serialisation (a
single workspace's log fits in memory for V1; there is NO silent cap — the
drain paginates to exhaustion, BR6). ``generated_at`` is injected by the caller
(from its clock), so the manifest is the only line that may differ between the
two vias (BR3).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from ..config import NexusConfig
from ..domain.replay import canonical_filters, serialize_event, serialize_manifest
from .observability import ObservabilityService
from .ports import UnitOfWork

__all__ = ["ReplayExportService"]


class ReplayExportService:
    """Produce the NDJSON export lines for one workspace's event log."""

    def __init__(
        self,
        observability: ObservabilityService,
        config: NexusConfig,
    ) -> None:
        self._obs = observability
        self._config = config

    def collect_events(
        self,
        uow: UnitOfWork,
        *,
        workspace_id: str,
        stream: str | None = None,
        trace_id: str | None = None,
        since_event_id: int = 0,
        until_event_id: int | None = None,
    ) -> list[dict[str, Any]]:
        """Drain the recorte to exhaustion, paginating by cursor.

        ``since_event_id`` is an EXCLUSIVE cursor (``event_id > since``, the
        native ``events_after`` semantics); ``until_event_id`` is an INCLUSIVE
        upper bound applied client-side (ascending order lets us stop early).
        No total cap — every matching event is returned (BR6).
        """
        page_size = int(self._config.max_event_limit)
        out: list[dict[str, Any]] = []
        cursor = max(0, int(since_event_id))
        while True:
            page = self._obs.events_page(
                uow,
                cursor=cursor,
                workspace_id=workspace_id,
                stream=stream,
                limit=page_size,
                trace_id=trace_id,
            )
            if not page:
                break
            for event in page:
                if until_event_id is not None and event["event_id"] > int(
                    until_event_id
                ):
                    return out
                out.append(event)
            cursor = page[-1]["event_id"]
            if len(page) < page_size:
                break
        return out

    def export_lines(
        self,
        uow: UnitOfWork,
        *,
        workspace_id: str,
        generated_at: str,
        stream: str | None = None,
        trace_id: str | None = None,
        since_event_id: int = 0,
        until_event_id: int | None = None,
    ) -> Iterator[str]:
        """Yield the export as NDJSON lines: manifest first, then one event/line.

        Lines carry NO trailing newline — the caller joins with ``"\\n"`` (the
        CLI writes ``line + "\\n"``; the REST generator does the same), keeping
        both vias byte-identical.
        """
        events = self.collect_events(
            uow,
            workspace_id=workspace_id,
            stream=stream,
            trace_id=trace_id,
            since_event_id=since_event_id,
            until_event_id=until_event_id,
        )
        ids = [event["event_id"] for event in events]
        yield serialize_manifest(
            workspace_id=workspace_id,
            filters=canonical_filters(
                stream=stream,
                trace_id=trace_id,
                since_event_id=since_event_id,
                until_event_id=until_event_id,
            ),
            event_count=len(events),
            event_id_min=min(ids) if ids else None,
            event_id_max=max(ids) if ids else None,
            generated_at=generated_at,
        )
        for event in events:
            yield serialize_event(event)

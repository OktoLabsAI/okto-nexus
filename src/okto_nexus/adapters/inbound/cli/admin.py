"""``okto-nexus admin`` - operator maintenance subcommands.

Currently one command, ``prune``: enforce the retention windows (events /
read deliveries / closed sessions) against the shared store and print a JSON
report. The store is append-mostly by design, so WITHOUT pruning ``nexus.db``
grows without bound; this is the operator-facing counterpart of the
``auto_prune_on_start`` opportunistic reaper.

Usage::

    okto-nexus admin prune --project-root <path> \
        [--dry-run] [--vacuum] \
        [--events-keep-days N] [--read-deliveries-keep-days N] \
        [--closed-sessions-keep-days N]

Semantics worth knowing before running it:

* SCOPE IS THE WHOLE STORE. Every workspace shares one ``nexus.db`` (and an
  agent's inbox is global), so retention is enforced store-wide.
  ``--project-root`` anchors the call to a real workspace exactly like every
  other subcommand (it is validated fail-closed) but does NOT narrow the
  prune.
* ONLY TERMINAL LANES ARE ELIGIBLE: events past their window, ``read``
  deliveries, ``closed`` sessions. ``unread``/``delivered``/``parked``
  deliveries, ``active``/``stale`` sessions and ALL handoffs are never
  deleted, regardless of age.
* ``--dry-run`` only counts (nothing is deleted, ``--vacuum`` is skipped) -
  run it first when unsure.
* ``--vacuum`` compacts the file after pruning (deletes alone leave free
  pages inside the file; only VACUUM shrinks it on disk).

Window overrides default to the ``NexusConfig`` retention section
(``OKTO_NEXUS_RETENTION_*_KEEP_DAYS``). Any flag this subcommand does not
recognise (e.g. ``--home`` / ``--db-path``) is forwarded verbatim to the same
fail-closed ``bootstrap`` the server uses, so config precedence (CLI > env >
default) is identical.

This is an inbound ADAPTER: it may use stdlib I/O (argparse/json/sys) and
import the server bootstrap, but it drives only the application services.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Mapping, Sequence
from typing import Any, Callable, TextIO

from okto_nexus.application.retention import RetentionService
from okto_nexus.domain.ids import resolve_workspace_id
from okto_nexus.errors import OktoNexusError

from ..mcp.server import bootstrap


def _build_parser() -> argparse.ArgumentParser:
    """Build the ``admin`` argument parser (subcommand-local flags only)."""
    parser = argparse.ArgumentParser(
        prog="okto-nexus admin",
        description="Operator maintenance commands for the shared store.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    prune = sub.add_parser(
        "prune",
        help="Enforce retention windows (events/read deliveries/closed sessions).",
        description=(
            "Delete rows older than their retention window across the WHOLE "
            "store (every workspace shares one nexus.db) and print a JSON "
            "report. Only terminal lanes are eligible: unread/delivered/"
            "parked deliveries, active/stale sessions and all handoffs are "
            "NEVER deleted."
        ),
    )
    prune.add_argument(
        "--project-root",
        dest="project_root",
        required=True,
        help=(
            "Absolute path of a workspace root (validated fail-closed, like "
            "every subcommand). Retention itself spans the WHOLE store."
        ),
    )
    prune.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        help="Only COUNT what would be deleted; write nothing, skip --vacuum.",
    )
    prune.add_argument(
        "--vacuum",
        dest="vacuum",
        action="store_true",
        help=(
            "Compact the database file after pruning (VACUUM); without it, "
            "freed pages stay inside the file."
        ),
    )
    prune.add_argument(
        "--events-keep-days",
        dest="events_keep_days",
        type=int,
        default=None,
        metavar="N",
        help="Override the events window (default: config, 30 days).",
    )
    prune.add_argument(
        "--read-deliveries-keep-days",
        dest="read_deliveries_keep_days",
        type=int,
        default=None,
        metavar="N",
        help="Override the read-deliveries window (default: config, 14 days).",
    )
    prune.add_argument(
        "--closed-sessions-keep-days",
        dest="closed_sessions_keep_days",
        type=int,
        default=None,
        metavar="N",
        help="Override the closed-sessions window (default: config, 7 days).",
    )
    prune.add_argument(
        "--messages-keep-days",
        dest="messages_keep_days",
        type=int,
        default=None,
        metavar="N",
        help=(
            "Override the messages window (default: config, 30 days; HARD "
            "minimum 7). Messages expire by PURE AGE regardless of delivery "
            "status, taking their deliveries and embeddings with them."
        ),
    )

    issue_keys = sub.add_parser(
        "issue-keys",
        help="Issue API keys in batch for V1 agents that have none (FR7).",
        description=(
            "Strictly ADDITIVE key migration: every agent whose api_key_hash "
            "is NULL gets a fresh nxs_* key; agents that already hold a key "
            "are NEVER touched (no rotation, no revocation). The agent->key "
            "map is printed ONCE - plaintext is never stored - so capture the "
            "output now. Idempotent: a second run is an informative no-op."
        ),
    )
    issue_keys.add_argument(
        "--project-root",
        dest="project_root",
        required=True,
        help="Absolute path of a workspace root (validated fail-closed).",
    )

    export = sub.add_parser(
        "export",
        help="Export a workspace event log as an NDJSON replay stream (I8).",
        description=(
            "Stream the workspace's append-only event log as NDJSON: a leading "
            "manifest line (format_version/filters/event range) followed by one "
            "RAW event per line, ordered by event_id ASC. This is the "
            "re-executable coordination benchmark - the operator-facing read "
            "path (NO per-agent visibility filter). Unlike the REST download, "
            "the CLI is intentionally UNGATED (operator already holds the "
            "shell) - the feature_replay opt-in gates only the HTTP surface."
        ),
    )
    export.add_argument(
        "--project-root",
        dest="project_root",
        required=True,
        help=(
            "Absolute path of the workspace root to export (validated "
            "fail-closed). The server hashes it to the workspace_id."
        ),
    )
    export.add_argument(
        "--stream",
        dest="stream",
        default=None,
        help="Restrict the export to one stream (e.g. handoff, message).",
    )
    export.add_argument(
        "--trace-id",
        dest="trace_id",
        default=None,
        help="Restrict the export to a single correlation trace_id.",
    )
    export.add_argument(
        "--since-event-id",
        dest="since_event_id",
        type=int,
        default=0,
        metavar="N",
        help="EXCLUSIVE lower bound: only events with event_id > N (default 0).",
    )
    export.add_argument(
        "--until-event-id",
        dest="until_event_id",
        type=int,
        default=None,
        metavar="N",
        help="INCLUSIVE upper bound: only events with event_id <= N.",
    )
    export.add_argument(
        "--output",
        dest="output",
        default=None,
        metavar="PATH",
        help=(
            "Write NDJSON to this file (UTF-8, LF newlines). Omit to stream to stdout."
        ),
    )
    return parser


def _run_export(deps: Any, ns: argparse.Namespace, sink: TextIO) -> int:
    """Stream one workspace's event log as NDJSON (manifest + one event/line).

    Ungated by design (D3): the CLI operates from the operator's own shell.
    Reads through a single read UnitOfWork snapshot so the whole slice is
    internally consistent, and writes UTF-8 with LF newlines so the bytes match
    the REST download exactly (modulo the manifest's generated_at).
    """
    from okto_nexus.adapters.outbound.sqlite.observability_repo import (
        SqliteObservabilityQueries,
    )
    from okto_nexus.application.observability import ObservabilityService
    from okto_nexus.application.replay import ReplayExportService

    workspace_id = resolve_workspace_id(ns.project_root)
    observability = ObservabilityService(
        SqliteObservabilityQueries(), deps.clock, deps.config
    )
    service = ReplayExportService(observability, deps.config)
    generated_at = deps.clock.now_iso()

    def _emit(writer: TextIO) -> None:
        with deps.connection_factory.unit_of_work(write=False) as uow:
            for line in service.export_lines(
                uow,
                workspace_id=workspace_id,
                generated_at=generated_at,
                stream=ns.stream,
                trace_id=ns.trace_id,
                since_event_id=ns.since_event_id,
                until_event_id=ns.until_event_id,
            ):
                writer.write(line + "\n")

    if ns.output:
        with open(ns.output, "w", encoding="utf-8", newline="\n") as fh:
            _emit(fh)
    else:
        # RAW event payloads may carry non-ASCII; force the stdout sink to
        # UTF-8/LF so the stream is faithful and CRLF-free (a no-op for the
        # StringIO sink tests inject).
        reconfigure = getattr(sink, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", newline="\n")
            except (ValueError, OSError):
                pass
        _emit(sink)
        sink.flush()
    return 0


def _run_issue_keys(deps: Any, sink: TextIO) -> int:
    """Issue keys for keyless agents; print the map exactly once."""
    from okto_nexus.application.auth import AgentKeyAuthService

    auth = AgentKeyAuthService(deps.repos.agents, deps.clock)
    issued: dict[str, str] = {}
    with deps.connection_factory.unit_of_work() as uow:
        pending = deps.repos.agents.list_without_key(uow)
        for agent in pending:
            issued[agent.agent_id] = auth.issue_key(uow, agent_id=agent.agent_id)

    if not issued:
        sink.write(
            json.dumps(
                {"issued": 0, "note": "every agent already holds a key"},
                ensure_ascii=True,
            )
            + "\n"
        )
        sink.flush()
        return 0

    sink.write(
        json.dumps(
            {
                "issued": len(issued),
                "keys": issued,
                "warning": (
                    "These plaintext keys are shown ONCE and never stored; "
                    "distribute them to the agents now."
                ),
            },
            indent=2,
            ensure_ascii=True,
        )
        + "\n"
    )
    sink.flush()
    return 0


def run_admin(
    argv: Sequence[str],
    *,
    env: Mapping[str, str] | None = None,
    out: TextIO | None = None,
    deps_factory: Callable[[Mapping[str, str], list[str]], Any] | None = None,
) -> int:
    """Entry point for the ``admin`` subcommand; returns a process exit code.

    Unknown flags are forwarded to ``bootstrap`` (config precedence preserved).
    ``deps_factory`` is an injection seam for tests: ``(env, extra_argv) ->
    Deps``; in production the real fail-closed bootstrap is used. Any
    :class:`OktoNexusError` (bad workspace/config/db/...) is reported to stderr
    and mapped to exit code 1.
    """
    parser = _build_parser()
    ns, extra = parser.parse_known_args(list(argv))
    environ = env if env is not None else os.environ
    sink = out if out is not None else sys.stdout
    try:
        deps = (deps_factory or bootstrap)(environ, extra)
        # Anchor to a real workspace, fail-closed (WORKSPACE_UNRESOLVED on a
        # broken path) - same discipline as every other subcommand even though
        # retention/key issuing spans the whole store.
        resolve_workspace_id(ns.project_root)
        if ns.command == "issue-keys":
            return _run_issue_keys(deps, sink)
        if ns.command == "export":
            return _run_export(deps, ns, sink)
        report = RetentionService.from_deps(deps).prune(
            events_keep_days=ns.events_keep_days,
            read_deliveries_keep_days=ns.read_deliveries_keep_days,
            closed_sessions_keep_days=ns.closed_sessions_keep_days,
            messages_keep_days=ns.messages_keep_days,
            dry_run=ns.dry_run,
            vacuum=ns.vacuum,
        )
        # ensure_ascii keeps the report portable across stdout encodings
        # (e.g. Windows cp1252), mirroring the tail NDJSON stream.
        sink.write(json.dumps(report, indent=2, ensure_ascii=True) + "\n")
        sink.flush()
        return 0
    except OktoNexusError as exc:
        print(f"[okto-nexus admin] {exc.code}: {exc.message}", file=sys.stderr)
        return 1

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
    return parser


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
        # retention spans the whole store.
        resolve_workspace_id(ns.project_root)
        report = RetentionService.from_deps(deps).prune(
            events_keep_days=ns.events_keep_days,
            read_deliveries_keep_days=ns.read_deliveries_keep_days,
            closed_sessions_keep_days=ns.closed_sessions_keep_days,
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

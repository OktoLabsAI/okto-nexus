"""``okto-nexus tail`` - stream the workspace event log as line-delimited JSON.

This subcommand wraps the Event Log slice's ``event_wait`` long-poll with
automatic cursor advancement and prints ONE compact JSON object per event
(line-buffered, flushed after every line) so any agent or shell can ``tail -f``
the live log through the PUBLIC API - visibility/routing are enforced by
``event_get`` / ``event_wait`` exactly as for an MCP caller, and the SQLite file
is never read directly.

Usage::

    okto-nexus tail --project-root <path> --agent-id <id> \
        [--stream workspace|agent|task|handoff] \
        [--from latest|0|<event_id>] \
        [--from-agent <id>] [--exclude-agent <id>] \
        [--limit N] [--timeout-seconds N] [--once]

As a background MONITOR, two things matter beyond the happy path:

* Author filtering. The follower emits EVERY visible event, including the
  caller's OWN - so a naive monitor would react to its own echo. Use
  ``--exclude-agent <you>`` to drop it (client-side, since the event_wait filter
  is equality-only), or ``--from-agent <x>`` to watch a single author
  (server-side). Example monitor that ignores its own writes::

      okto-nexus tail --project-root <path> --agent-id <you> \
          --from latest --exclude-agent <you>

* Resilience. A momentary WAL lock surfaces as a TRANSIENT ``DB_ERROR``; the
  follow loop retries those with bounded backoff (so a long-running monitor is
  not killed by contention) while failing fast on terminal errors and surfacing
  a transient that will not clear.

Any flag this subcommand does not recognise (e.g. ``--home`` / ``--db-path``)
is forwarded verbatim to the same fail-closed ``bootstrap`` the server uses, so
config precedence (CLI > env > default) is identical.

This is an inbound ADAPTER: it may use stdlib I/O (argparse/json/sys) and import
the server bootstrap, but it drives only the application services.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections.abc import Mapping, Sequence
from typing import Any, Callable, TextIO

from okto_nexus.errors import ErrorCode, OktoNexusError

from ..mcp.server import bootstrap
from ..mcp.tools.events import build_service

#: ``--from`` sentinel: follow only events appended AFTER the stream's current end.
_LATEST = "latest"

#: ``--from`` aliases that mean "from the very beginning of the stream".
_BEGIN = frozenset({"0", "begin", "start"})

#: Page size of the LEGACY ``--from latest`` resolution (page-walk to the end),
#: kept only as a fallback for injected services that lack the O(1)
#: ``latest_cursor`` resolver.
_WALK_LIMIT = 1000

#: Error codes that are TRANSIENT under WAL contention: a momentary SQLite lock
#: surfaces as ``DB_ERROR``. The follower retries THESE with bounded backoff
#: instead of dying; every other code is terminal and surfaces immediately.
_TRANSIENT_CODES = frozenset({ErrorCode.DB_ERROR.value})

#: Bounded retry policy for transient errors in the follow loop. The counter
#: RESETS after every successful poll, so sporadic locks over a long-running
#: follow never accumulate - only this many CONSECUTIVE transient failures
#: surface (a persistent fault is never silenced).
_MAX_TRANSIENT_RETRIES = 6
_BACKOFF_BASE_SECONDS = 0.1
_BACKOFF_CAP_SECONDS = 2.0


def _build_parser() -> argparse.ArgumentParser:
    """Build the ``tail`` argument parser (subcommand-local flags only)."""
    parser = argparse.ArgumentParser(
        prog="okto-nexus tail",
        description=(
            "Stream the workspace event log as line-delimited JSON via the "
            "public event_wait long-poll (visibility/routing enforced)."
        ),
        epilog=(
            "Designed as a BACKGROUND FOLLOWER: run it detached and treat each "
            "NDJSON line as a notification, keeping the agent loop free - the "
            "layer-clean way to watch the bus without blocking a turn on "
            "event_wait or reading the SQLite file directly."
        ),
    )
    parser.add_argument(
        "--project-root",
        dest="project_root",
        required=True,
        help="Absolute path whose sha256(realpath) is the workspace_id.",
    )
    parser.add_argument(
        "--agent-id",
        dest="agent_id",
        required=True,
        help="Caller identity; scopes per-event visibility (can_agent_see_event).",
    )
    parser.add_argument(
        "--stream",
        default="workspace",
        help="One of workspace|agent|task|handoff (default: workspace).",
    )
    parser.add_argument(
        "--from",
        dest="from_cursor",
        default=_LATEST,
        metavar="latest|0|N",
        help=(
            "Start cursor: 'latest' (follow only new events, default), "
            "'0' (from the beginning), or an explicit event_id."
        ),
    )
    parser.add_argument(
        "--from-agent",
        dest="from_agent",
        default=None,
        metavar="AGENT_ID",
        help=(
            "Include-by-author (server-side): only events whose actor is "
            "AGENT_ID, via the event_wait filters={agent_id} equality match."
        ),
    )
    parser.add_argument(
        "--exclude-agent",
        dest="exclude_agent",
        default=None,
        metavar="AGENT_ID",
        help=(
            "Exclude-by-author (client-side): skip events authored by AGENT_ID. "
            "Use to drop your OWN echo, e.g. --exclude-agent <you>. The "
            "event_wait filter is equality-only, so exclusion is done here."
        ),
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max events returned per poll window (clamped server-side).",
    )
    parser.add_argument(
        "--timeout-seconds",
        dest="timeout_seconds",
        type=int,
        default=None,
        help="Long-poll ceiling per window in seconds (clamped server-side).",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Emit a single poll window then exit (no follow loop).",
    )
    return parser


def _resolve_start_cursor(service: Any, ns: argparse.Namespace) -> int:
    """Resolve ``--from`` into a concrete starting ``event_id`` cursor.

    ``0``/``begin``/``start`` -> ``0``; an explicit non-negative integer is used
    verbatim; ``latest`` resolves the stream's current end in O(1) via the
    service's ``latest_cursor`` (an indexed ``MAX(event_id)``, never a scan) so
    follower STARTUP COST does not grow with the size of the log - only
    subsequently-appended events are followed. An injected service without the
    resolver falls back to the legacy page-walk over ``event_get``. A malformed
    value raises ``CONFIG_ERROR`` (fail closed).
    """
    raw = (ns.from_cursor or _LATEST).strip().lower()
    if raw in _BEGIN:
        return 0
    if raw == _LATEST:
        latest = getattr(service, "latest_cursor", None)
        if callable(latest):
            return int(
                latest(
                    project_root=ns.project_root,
                    agent_id=ns.agent_id,
                    stream=ns.stream,
                )
            )
        # Legacy fallback (service without latest_cursor): walk to the end.
        cursor = 0
        while True:
            page = service.event_get(
                project_root=ns.project_root,
                agent_id=ns.agent_id,
                stream=ns.stream,
                cursor=cursor,
                limit=_WALK_LIMIT,
            )
            cursor = page["next_cursor"]
            if not page["has_more"]:
                return cursor
    try:
        value = int(raw)
    except ValueError:
        raise OktoNexusError(
            ErrorCode.CONFIG_ERROR,
            "--from must be 'latest', '0', or a non-negative event_id.",
            {"from": ns.from_cursor},
        ) from None
    if value < 0:
        raise OktoNexusError(
            ErrorCode.CONFIG_ERROR,
            "--from event_id must be non-negative.",
            {"from": ns.from_cursor},
        )
    return value


def stream_events(
    service: Any,
    ns: argparse.Namespace,
    out: TextIO,
    *,
    start_cursor: int,
    sleeper: Callable[[float], None] = time.sleep,
) -> int:
    """Follow the log from ``start_cursor``, writing one JSON object per line.

    Each ``event_wait`` window is printed (newest events in ascending order) and
    flushed immediately; the cursor advances to the window's ``next_cursor`` so
    no event is ever re-emitted. Loops until ``--once`` is satisfied or the
    process is interrupted (``Ctrl+C`` -> clean exit 0).

    Author filtering: ``--from-agent`` is pushed down as the ``event_wait``
    ``filters={agent_id}`` equality match (server-side); ``--exclude-agent`` is
    applied HERE (client-side) because the filter has no inequality - this is how
    a monitor drops its own echo.

    Resilience: a TRANSIENT failure (a momentary WAL lock -> ``DB_ERROR``) is
    retried with bounded exponential backoff (counter reset on every successful
    poll), so a long-running follower survives contention instead of dying.
    Terminal errors fail fast, and a transient that exhausts the retry budget is
    re-raised (surfaced on stderr + exit 1) rather than silently swallowed. The
    cursor is NOT advanced across a failed poll, so no event is ever skipped.
    """
    cursor = start_cursor
    filters = {"agent_id": ns.from_agent} if getattr(ns, "from_agent", None) else None
    exclude = getattr(ns, "exclude_agent", None)
    consecutive_transient = 0
    try:
        while True:
            try:
                page = service.event_wait(
                    project_root=ns.project_root,
                    agent_id=ns.agent_id,
                    stream=ns.stream,
                    cursor=cursor,
                    limit=ns.limit,
                    filters=filters,
                    timeout_seconds=ns.timeout_seconds,
                )
            except OktoNexusError as exc:
                if (
                    exc.code in _TRANSIENT_CODES
                    and consecutive_transient < _MAX_TRANSIENT_RETRIES
                ):
                    delay = min(
                        _BACKOFF_CAP_SECONDS,
                        _BACKOFF_BASE_SECONDS * (2**consecutive_transient),
                    )
                    consecutive_transient += 1
                    print(
                        f"[okto-nexus tail] transient {exc.code}; retry "
                        f"{consecutive_transient}/{_MAX_TRANSIENT_RETRIES} "
                        f"in {delay:.1f}s",
                        file=sys.stderr,
                    )
                    sleeper(delay)
                    continue  # same cursor -> the failed window is not skipped
                raise  # terminal, or transient budget exhausted -> surface it
            consecutive_transient = 0  # reset after any successful poll
            for event in page["events"]:
                if exclude is not None and event.get("actor_agent_id") == exclude:
                    continue  # drop own/other author's echo (client-side)
                # ``ensure_ascii=True`` (the default, made explicit): events can
                # carry arbitrary UTF-8 (emoji, accents). Escaping to ASCII keeps
                # the stream portable across stdout encodings (e.g. Windows
                # cp1252) and pipes, where a raw non-ASCII byte would otherwise
                # abort the follow with UnicodeEncodeError. ``\uXXXX`` is valid
                # JSON; any consumer decodes it back losslessly.
                out.write(json.dumps(event, ensure_ascii=True) + "\n")
                out.flush()
            cursor = page["next_cursor"]
            if ns.once:
                return 0
    except KeyboardInterrupt:
        return 0
    except BrokenPipeError:
        # The downstream consumer closed the pipe (e.g. ``okto-nexus tail | head``).
        # Exit cleanly like a POSIX SIGPIPE-aware streamer instead of dumping a
        # traceback on the next write/flush.
        return 0


def run_tail(
    argv: Sequence[str],
    *,
    env: Mapping[str, str] | None = None,
    out: TextIO | None = None,
    service_factory: Callable[[Mapping[str, str], list[str]], Any] | None = None,
) -> int:
    """Entry point for the ``tail`` subcommand; returns a process exit code.

    Unknown flags are forwarded to ``bootstrap`` (config precedence preserved).
    ``service_factory`` is an injection seam for tests: ``(env, extra_argv) ->
    service``; in production the real fail-closed bootstrap + event service are
    used. Any :class:`OktoNexusError` (bad workspace/stream/config/...) is
    reported to stderr and mapped to exit code 1.
    """
    parser = _build_parser()
    ns, extra = parser.parse_known_args(list(argv))
    environ = env if env is not None else os.environ
    sink = out if out is not None else sys.stdout
    try:
        # ``--timeout-seconds <= 0`` makes ``event_wait`` return immediately
        # (single-shot, no sleep). In a follow loop that becomes a 100%-CPU
        # busy-spin, so it is only meaningful with ``--once``. Fail closed.
        if (
            ns.timeout_seconds is not None
            and ns.timeout_seconds <= 0
            and not ns.once
        ):
            raise OktoNexusError(
                ErrorCode.CONFIG_ERROR,
                "--timeout-seconds <= 0 requires --once; otherwise the follow "
                "loop would busy-spin (event_wait returns without sleeping).",
                {"timeout_seconds": ns.timeout_seconds},
            )
        if service_factory is not None:
            service = service_factory(environ, extra)
        else:
            deps = bootstrap(environ, extra)
            service = build_service(deps)
        start_cursor = _resolve_start_cursor(service, ns)
        return stream_events(service, ns, sink, start_cursor=start_cursor)
    except KeyboardInterrupt:
        # SIGINT during ``--from latest`` resolution (before the follow loop)
        # must still exit cleanly, matching stream_events' contract.
        return 0
    except OktoNexusError as exc:
        print(f"[okto-nexus tail] {exc.code}: {exc.message}", file=sys.stderr)
        return 1

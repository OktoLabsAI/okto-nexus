"""Read ONLY usage/correlation projections from owned Core journals; no transcripts."""

from contextlib import closing
import json
import sqlite3

from safety import owned, require


def nonnegative(value):
    require(type(value) is int and value >= 0, "USAGE_COUNTER_UNKNOWN")
    return value


def summarize(adapter, rows, *, selected_model=None):
    totals, terminals, started = {}, set(), {}
    coverage = {}
    report_sequences = {}
    per_operation_totals = {}
    for row in rows:
        operation = row["operation"]
        if row["phase"] == "started" and operation:
            started[operation] = (row["sequence"], row["thread"], row["turn"])
        if row["phase"] == "terminal" and operation:
            require(
                row["outcome"] in ("success", "failed", "interrupted"),
                "TERMINAL_OUTCOME_UNKNOWN",
            )
            terminals.add(operation)
        has_usage = False
        if adapter == "codex_app_server" and row["codex_usage"] is not None:
            usage = json.loads(row["codex_usage"])
            names = (
                "totalTokens",
                "inputTokens",
                "cachedInputTokens",
                "outputTokens",
                "reasoningOutputTokens",
            )
            for name in names:
                nonnegative(usage.get(name))
            require(
                usage["cachedInputTokens"] <= usage["inputTokens"]
                and usage["reasoningOutputTokens"] <= usage["outputTokens"],
                "USAGE_SUBSET_INVALID",
            )
            identity = row["thread"]
            require(isinstance(identity, str) and identity, "NATIVE_THREAD_UNKNOWN")
            require(usage["totalTokens"] >= totals.get(identity, 0), "USAGE_REGRESSION")
            require(
                usage["totalTokens"] == usage["inputTokens"] + usage["outputTokens"],
                "USAGE_TOTAL_INCONSISTENT",
            )
            totals[identity] = usage["totalTokens"]
            has_usage = True
        elif adapter == "claude_stream" and row["claude_models"] is not None:
            models = json.loads(row["claude_models"])
            require(
                isinstance(models, dict) and models and len(models) <= 8,
                "CLAUDE_MODELS_UNKNOWN",
            )
            # Use the full terminal model report per operation. The explicit
            # policy accepts conservative overcount if streaming results carry
            # earlier turns, rather than undercounting separate resumed runs.
            require(
                selected_model in models and set(models) == {selected_model},
                "UNREVIEWED_NATIVE_MODEL",
            )
            identity = row["native_session"]
            require(isinstance(identity, str) and identity, "NATIVE_SESSION_UNKNOWN")
            components = models[selected_model]
            total = sum(
                nonnegative(components.get(name))
                for name in (
                    "inputTokens",
                    "outputTokens",
                    "cacheReadInputTokens",
                    "cacheCreationInputTokens",
                )
            )
            # Counting all reported cache buckets is deliberately conservative;
            # this is an observed guard, never an exact billing calculation.
            require(
                operation and row["phase"] == "terminal",
                "CLAUDE_TERMINAL_USAGE_CORRELATION_REQUIRED",
            )
            require(total >= per_operation_totals.get(operation, 0), "USAGE_REGRESSION")
            per_operation_totals[operation] = total
            # Count each admission's FULL result independently. A resumed
            # process may report only that run; persistent streaming may report
            # earlier turns too. Summing full per-admission reports can overcount
            # the latter, but never uses max(session) to undercount the former.
            totals[identity] = sum(per_operation_totals.values())
            has_usage = True
        if has_usage:
            selected = operation if operation in started else None
            if selected is None and row["thread"] and row["turn"]:
                matches = [
                    key
                    for key, value in started.items()
                    if value[1:] == (row["thread"], row["turn"])
                ]
                if len(matches) == 1:
                    selected = matches[0]
            # A previous turn's cumulative counter cannot cover a new terminal.
            # Ambiguous/missing correlation remains an observed lower bound only.
            if selected and row["sequence"] >= started[selected][0]:
                report_sequences[selected] = row["sequence"]
                if (
                    adapter == "claude_stream"
                    and row["phase"] == "terminal"
                    and selected == operation
                ):
                    coverage[selected] = row["sequence"]
    if adapter == "codex_app_server":
        # Explicit pre-consent policy: this is a correlated OBSERVED counter,
        # not final usage. Its admission's permanent 75k provision is NEVER
        # released by terminal execution, this report or a quiet timer.
        coverage.update(report_sequences)
    require(len(totals) <= 1, "UNEXPECTED_NATIVE_SESSION_OR_RESET")
    return {
        "total": sum(totals.values()),
        "usage_seen": bool(totals),
        "terminal_operations": sorted(terminals),
        "started_operations": sorted(started),
        "accounting_operations": sorted(coverage),
        "usage_sequence_by_operation": coverage,
        "per_operation_totals": per_operation_totals,
        "native_identities": sorted(totals),
        "reported_accounting_final": False,
    }


def snapshot(root, path, adapter, scope, *, selected_model=None):
    path = owned(root, path)
    require(path.is_file(), "JOURNAL_NOT_YET_AVAILABLE")
    require(
        len(scope) == 4 and all(isinstance(item, str) and item for item in scope),
        "EXACT_STREAM_REQUIRED",
    )
    with closing(
        sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=1)
    ) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        stream = db.execute(
            "SELECT next_sequence-1 AS watermark,compacted_sequence FROM event_streams "
            "WHERE server_id=? AND executor_id=? AND session_id=? AND stream_epoch=?",
            scope,
        ).fetchone()
        require(stream is not None, "STREAM_NOT_YET_AVAILABLE")
        count = db.execute(
            "SELECT COUNT(*) AS n,MIN(sequence) AS lo,MAX(sequence) AS hi FROM events "
            "WHERE server_id=? AND executor_id=? AND session_id=? AND stream_epoch=?",
            scope,
        ).fetchone()
        require(
            0 <= stream["watermark"] <= 50000
            and stream["compacted_sequence"] == 0
            and count["n"] == stream["watermark"]
            and (count["n"] == 0 or (count["lo"] == 1 and count["hi"] == count["n"])),
            "JOURNAL_COVERAGE_GAP",
        )
        rows = db.execute(
            """SELECT sequence, json_extract(body,'$.operation_id') AS operation,
          json_extract(body,'$.payload.delivery_phase') AS phase,
          json_extract(body,'$.payload.delivery_outcome') AS outcome,
          json_extract(body,'$.payload.thread_id') AS thread,
          json_extract(body,'$.payload.turn_id') AS turn,
          json_extract(body,'$.payload.session_id') AS native_session,
          json_extract(body,'$.payload.tokenUsage.total') AS codex_usage,
          json_extract(body,'$.payload.modelUsage') AS claude_models
          FROM events WHERE server_id=? AND executor_id=? AND session_id=? AND stream_epoch=?
          ORDER BY sequence LIMIT 50001""",
            scope,
        ).fetchall()
        return summarize(adapter, rows, selected_model=selected_model)

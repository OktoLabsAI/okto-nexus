"""Tests for M9: fail-closed config knobs + the consolidated base helpers.

Covers:

* the four knobs that used to be resolved ad hoc from ``os.environ`` by the
  inbound tool adapters with a SILENT int() fallback (inbox lease TTL, session
  stale TTL, shared.md events ceiling, event page ceiling) - now ``NexusConfig``
  fields parsed FAIL-CLOSED by ``load_config`` under the SAME env var names;
* the single time helpers (``iso_to_epoch`` tolerant to ``z``/``Z``,
  ``iso_plus`` fixed-width) that replaced the per-slice copies which had
  already diverged (lowercase ``z`` was handled by only one copy);
* the lease-WRITE boundary: an injected clock emitting a non-canonical (not
  lexicographically comparable) timestamp is rejected with a clear
  INTERNAL_ERROR by both the inbox pull and the handoff claim;
* the single ``check_inline_size`` (raw string vs JSON measurement unified)
  and the single cursor/limit pagination parsers.
"""

from __future__ import annotations

import pytest

from okto_nexus.config import (
    DEFAULT_INBOX_LEASE_TTL_SECONDS,
    DEFAULT_MAX_EVENT_LIMIT,
    DEFAULT_MAX_SHARED_MD_EVENTS,
    DEFAULT_SESSION_STALE_TTL_SECONDS,
    NexusConfig,
    load_config,
)
from okto_nexus.domain.base import (
    check_inline_size,
    clamp_limit,
    iso_plus,
    iso_to_epoch,
    normalize_cursor,
    utc_now_iso,
)
from okto_nexus.errors import ErrorCode, OktoNexusError

#: (env var, NexusConfig field, default) for the four migrated knobs.
KNOBS = [
    (
        "OKTO_NEXUS_INBOX_LEASE_TTL_SECONDS",
        "inbox_lease_ttl_seconds",
        DEFAULT_INBOX_LEASE_TTL_SECONDS,
    ),
    (
        "OKTO_NEXUS_SESSION_STALE_TTL_SECONDS",
        "session_stale_ttl_seconds",
        DEFAULT_SESSION_STALE_TTL_SECONDS,
    ),
    (
        "OKTO_NEXUS_MAX_SHARED_MD_EVENTS",
        "max_shared_md_events",
        DEFAULT_MAX_SHARED_MD_EVENTS,
    ),
    ("OKTO_NEXUS_MAX_EVENT_LIMIT", "max_event_limit", DEFAULT_MAX_EVENT_LIMIT),
]


# --------------------------------------------------------------------------- #
# Fail-closed knob parsing (env var names preserved)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("env_var,field,default", KNOBS)
def test_knob_defaults_when_env_unset(env_var, field, default):
    config = load_config({})
    assert getattr(config, field) == default
    assert getattr(NexusConfig(), field) == default


@pytest.mark.parametrize("env_var,field,default", KNOBS)
def test_knob_parses_valid_env_value(env_var, field, default):
    config = load_config({env_var: "42"})
    assert getattr(config, field) == 42


@pytest.mark.parametrize("env_var,field,default", KNOBS)
@pytest.mark.parametrize("bad", ["abc", "", "  ", "1.5", "0", "-5"])
def test_knob_invalid_env_value_is_a_startup_error(env_var, field, default, bad):
    """The old adapters silently fell back to the default on ANY bad value;
    now a bad value aborts the fail-closed bootstrap with CONFIG_ERROR."""
    with pytest.raises(OktoNexusError) as ei:
        load_config({env_var: bad})
    assert ei.value.code == ErrorCode.CONFIG_ERROR.value
    assert field in ei.value.message


@pytest.mark.parametrize(
    "flag,field",
    [
        ("--inbox-lease-ttl-seconds", "inbox_lease_ttl_seconds"),
        ("--session-stale-ttl-seconds", "session_stale_ttl_seconds"),
        ("--max-shared-md-events", "max_shared_md_events"),
        ("--max-event-limit", "max_event_limit"),
    ],
)
def test_knob_cli_flag_overrides_env(flag, field):
    env_var = next(e for e, f, _ in KNOBS if f == field)
    config = load_config({env_var: "10"}, [flag, "99"])
    assert getattr(config, field) == 99  # CLI > env precedence


# --------------------------------------------------------------------------- #
# iso_to_epoch: ONE parser, tolerant to z/Z/offset/naive
# --------------------------------------------------------------------------- #
def test_iso_to_epoch_tolerates_all_utc_spellings():
    base = iso_to_epoch("2026-06-07T00:00:00Z")
    # The triplicated copies had diverged: lowercase 'z' was handled by only
    # one of them. The single parser accepts every UTC spelling identically.
    assert iso_to_epoch("2026-06-07T00:00:00z") == base
    assert iso_to_epoch("2026-06-07T00:00:00+00:00") == base
    assert iso_to_epoch("2026-06-07T00:00:00") == base  # naive -> UTC
    assert iso_to_epoch("2026-06-07T01:00:00+01:00") == base


def test_iso_to_epoch_raises_stdlib_errors():
    with pytest.raises(ValueError):
        iso_to_epoch("not-a-date")
    with pytest.raises(TypeError):
        iso_to_epoch(None)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# iso_plus: the lease-write boundary
# --------------------------------------------------------------------------- #
def test_iso_plus_shifts_and_stays_fixed_width():
    assert iso_plus("2026-06-07T00:00:00.000000Z", 300) == "2026-06-07T00:05:00.000000Z"
    assert iso_plus("2026-06-07T23:59:30.500000Z", 30.5) == "2026-06-08T00:00:01.000000Z"
    assert iso_plus(utc_now_iso(), 0).endswith("Z")


@pytest.mark.parametrize(
    "bad_now",
    [
        "2026-06-07T00:00:00Z",  # no fractional part (mixed width)
        "2026-06-07T00:00:00.123Z",  # 3-digit fraction (mixed width)
        "2026-06-07T00:00:00.000000+00:00",  # offset spelling, not Z
        "2026-06-07 00:00:00.000000Z",  # space separator
        "",
        None,
    ],
)
def test_iso_plus_rejects_non_canonical_clock_value(bad_now):
    with pytest.raises(OktoNexusError) as ei:
        iso_plus(bad_now, 60)
    assert ei.value.code == ErrorCode.INTERNAL_ERROR.value
    assert "lexicographically" in ei.value.message


def test_inbox_pull_rejects_non_lexicographic_clock(migrated_factory):
    """Behavioural: the inbox lease write refuses a clock whose format would
    corrupt the SQL lexicographic expiry comparison, with a prescriptive error
    (instead of silently writing a mixed-width lease)."""
    from okto_nexus.application.inbox import InboxService

    class BadClock:
        def now_iso(self) -> str:
            return "2026-06-07T00:00:00Z"  # not fixed-width

    svc = InboxService(
        connection_factory=migrated_factory,
        deliveries=None,
        messages=None,
        clock=BadClock(),
    )
    with pytest.raises(OktoNexusError) as ei:
        svc.pull(agent_id="r")
    assert ei.value.code == ErrorCode.INTERNAL_ERROR.value
    assert "Clock" in ei.value.message


def test_handoff_claim_rejects_non_lexicographic_clock(
    migrated_factory, tmp_config, tmp_path
):
    """Behavioural: the handoff claim lease write enforces the same canonical
    clock contract as the inbox (one boundary, one error)."""
    from okto_nexus.application.handoff import HandoffService

    class BadClock:
        def now_iso(self) -> str:
            return "2026-06-07T00:00:00Z"  # not fixed-width

    proj = tmp_path / "P"
    proj.mkdir()
    svc = HandoffService(
        connection_factory=migrated_factory,
        handoffs=None,
        tasks=None,
        clock=BadClock(),
        config=tmp_config,
    )
    with pytest.raises(OktoNexusError) as ei:
        svc.handoff_claim(project_root=str(proj), handoff_id="h1", agent_id="a")
    assert ei.value.code == ErrorCode.INTERNAL_ERROR.value
    assert "lexicographically" in ei.value.message


# --------------------------------------------------------------------------- #
# check_inline_size: ONE measurement rule (str verbatim, else JSON)
# --------------------------------------------------------------------------- #
def test_check_inline_size_inclusive_boundary_for_strings():
    check_inline_size("payload", None, 10)  # None always passes
    check_inline_size("payload", "x" * 10, 10)  # inclusive boundary
    with pytest.raises(OktoNexusError) as ei:
        check_inline_size("payload", "x" * 11, 10)
    assert ei.value.code == ErrorCode.CONTENT_TOO_LARGE.value
    assert ei.value.details == {"field": "payload", "max_inline_bytes": 10}


def test_check_inline_size_measures_json_for_non_strings():
    # {"v": ""} serialises to 9 bytes; the dict form is measured as its JSON.
    check_inline_size("metadata", {"v": "x"}, 10)
    with pytest.raises(OktoNexusError) as ei:
        check_inline_size("metadata", {"v": "xx"}, 10)
    assert ei.value.code == ErrorCode.CONTENT_TOO_LARGE.value


def test_check_inline_size_rejects_unserialisable():
    with pytest.raises(OktoNexusError) as ei:
        check_inline_size("payload", object(), 100)
    assert ei.value.code == ErrorCode.VALIDATION_ERROR.value


# --------------------------------------------------------------------------- #
# normalize_cursor / clamp_limit: ONE pagination grammar
# --------------------------------------------------------------------------- #
def test_normalize_cursor_grammar():
    assert normalize_cursor(None) == 0
    assert normalize_cursor("") == 0
    assert normalize_cursor(7) == 7
    assert normalize_cursor("7") == 7  # opaque string cursors round-trip
    for bad in (-1, "-1", "abc", 1.5, True, [1]):
        with pytest.raises(OktoNexusError) as ei:
            normalize_cursor(bad)
        assert ei.value.code == ErrorCode.VALIDATION_ERROR.value


def test_clamp_limit_grammar():
    assert clamp_limit(None, default=50, maximum=200) == 50
    assert clamp_limit(None, default=500, maximum=200) == 200  # default clamped
    assert clamp_limit("  ", default=50, maximum=200) == 50
    assert clamp_limit(5, default=50, maximum=200) == 5
    assert clamp_limit("5", default=50, maximum=200) == 5
    assert clamp_limit(10_000, default=50, maximum=200) == 200  # clamped
    for bad in (0, -3, "0", "abc", 2.5, True):
        with pytest.raises(OktoNexusError) as ei:
            clamp_limit(bad, default=50, maximum=200)
        assert ei.value.code == ErrorCode.VALIDATION_ERROR.value

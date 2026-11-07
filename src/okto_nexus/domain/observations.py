"""Pure syntax, replay hashes and freshness for external activity reports.

An observation reports activity of an explicitly registered external instance.
It never establishes an identity, a canonical session, capacity or task success.
Callers own authentication, binding, sequence/generation fencing and persistence.

Parse and hash BEFORE checking freshness: an already accepted identical report
must remain recognizable after its validity expires, without renewing its TTL.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
from typing import Any

from ..errors import ErrorCode, OktoNexusError


SCHEMA_VERSION = 1
STATES = frozenset({"working", "idle", "blocked", "unknown"})
EVIDENCE_KINDS = frozenset({"reported", "inferred"})
REASON_CODES = frozenset({
    "external_input_required", "external_activity", "external_idle",
    "external_completion", "external_error", "source_unavailable", "unknown",
})
MAX_VALID_FOR_SECONDS = 3600
MAX_SEQUENCE = (1 << 63) - 1
MAX_REASON_TEXT_CHARS = 512
MAX_COMPLETION_REF_CHARS = 256
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,159}\Z")
_TIMESTAMP = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]{1,6})?(?:Z|[+-][0-9]{2}:[0-9]{2})\Z"
)
_REQUIRED_FIELDS = frozenset({
    "schema_version", "source_id", "observed_instance_id", "generation",
    "sequence", "state", "evidence", "observed_at",
})
_OPTIONAL_FIELDS = frozenset({
    "valid_for_seconds", "reason_code", "reason_text", "current_completion_ref",
})


def _invalid(field_name: str) -> OktoNexusError:
    # Never include caller-controlled values or field names in the error.
    return OktoNexusError(
        ErrorCode.VALIDATION_ERROR,
        f"Invalid observation {field_name}.",
        {"field": field_name},
    )


def _positive_int(value: Any, field_name: str, *, maximum: int | None = None) -> None:
    if type(value) is not int or value < 1 or maximum is not None and value > maximum:
        raise _invalid(field_name)


def _timestamp(value: Any, field_name: str) -> datetime:
    if type(value) is not str or not _TIMESTAMP.fullmatch(value):
        raise _invalid(field_name)
    try:
        # Reject offsets that datetime otherwise normalizes (e.g. +00:60).
        if not value.endswith("Z"):
            if int(value[-5:-3]) > 23 or int(value[-2:]) > 59:
                raise ValueError
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except (ValueError, OverflowError):
        raise _invalid(field_name) from None


def _iso(value: datetime) -> str:
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _unicode_text(value: Any, field_name: str, maximum: int) -> None:
    if type(value) is not str or len(value) > maximum:
        raise _invalid(field_name)
    try:
        value.encode("utf-8")
    except UnicodeError:
        raise _invalid(field_name) from None


@dataclass(frozen=True, slots=True)
class ObservationLimits:
    """Explicit policy supplied by the application; no global settings lookup.

    TTL is always bounded by one hour. Future clock tolerance defaults to 30s
    and is independently configurable as a non-negative integer. A smaller
    maximum also requires a default no greater than that maximum.
    """

    default_valid_for_seconds: int = 90
    max_valid_for_seconds: int = MAX_VALID_FOR_SECONDS
    future_tolerance_seconds: int = 30

    def __post_init__(self) -> None:
        _positive_int(self.max_valid_for_seconds, "max_valid_for_seconds",
                      maximum=MAX_VALID_FOR_SECONDS)
        _positive_int(self.default_valid_for_seconds, "default_valid_for_seconds",
                      maximum=self.max_valid_for_seconds)
        if (type(self.future_tolerance_seconds) is not int
                or self.future_tolerance_seconds < 0):
            raise _invalid("future_tolerance_seconds")


@dataclass(frozen=True, slots=True)
class ObservationReport:
    """Validated immutable report, with timestamps normalized to UTC microseconds.

    Generation and sequence are positive signed-64-bit integers, without bool
    coercion or wrap. Optional reason/completion fields accept absence or null equivalently; both
    are omitted from canonical data. A completion reference is opaque evidence,
    never a task result.
    Reason text is untrusted display data and must be escaped by any renderer.
    """

    schema_version: int
    source_id: str
    observed_instance_id: str
    generation: int
    sequence: int
    state: str
    evidence: str
    observed_at: str
    valid_for_seconds: int = 90
    reason_code: str | None = None
    reason_text: str | None = field(default=None, repr=False)
    current_completion_ref: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != SCHEMA_VERSION:
            raise _invalid("schema_version")
        for name in ("source_id", "observed_instance_id"):
            value = getattr(self, name)
            if type(value) is not str or not _IDENTIFIER.fullmatch(value):
                raise _invalid(name)
        _positive_int(self.generation, "generation", maximum=MAX_SEQUENCE)
        _positive_int(self.sequence, "sequence", maximum=MAX_SEQUENCE)
        _positive_int(self.valid_for_seconds, "valid_for_seconds",
                      maximum=MAX_VALID_FOR_SECONDS)
        if type(self.state) is not str or self.state not in STATES:
            raise _invalid("state")
        if type(self.evidence) is not str or self.evidence not in EVIDENCE_KINDS:
            raise _invalid("evidence")
        object.__setattr__(self, "observed_at", _iso(_timestamp(self.observed_at, "observed_at")))
        if (self.reason_code is not None and
                (type(self.reason_code) is not str or self.reason_code not in REASON_CODES)):
            raise _invalid("reason_code")
        if self.reason_text is not None:
            _unicode_text(self.reason_text, "reason_text", MAX_REASON_TEXT_CHARS)
        if self.current_completion_ref is not None:
            _unicode_text(self.current_completion_ref, "current_completion_ref", MAX_COMPLETION_REF_CHARS)
            if (not self.current_completion_ref or not self.current_completion_ref.isprintable()
                    or self.current_completion_ref.strip() != self.current_completion_ref):
                raise _invalid("current_completion_ref")

    def to_dict(self) -> dict[str, Any]:
        """Return canonical report data only, without derived times or authority."""
        result = {name: getattr(self, name) for name in sorted(_REQUIRED_FIELDS)}
        result["valid_for_seconds"] = self.valid_for_seconds
        for name in ("reason_code", "reason_text", "current_completion_ref"):
            value = getattr(self, name)
            if value is not None:
                result[name] = value
        return result


def parse_report(payload: Any, *, limits: ObservationLimits = ObservationLimits()) -> ObservationReport:
    """Validate exact JSON types and closed keys, without consulting the clock.

    The transport/application owns raw byte and batch limits. Equivalent timezone
    spellings and an omitted versus explicit default TTL have the same hash.
    """
    if type(limits) is not ObservationLimits:
        raise _invalid("limits")
    if (type(payload) is not dict or any(type(key) is not str for key in payload)
            or not _REQUIRED_FIELDS <= payload.keys()
            or payload.keys() - (_REQUIRED_FIELDS | _OPTIONAL_FIELDS)):
        raise _invalid("fields")
    values = dict(payload)
    values.setdefault("valid_for_seconds", limits.default_valid_for_seconds)
    _positive_int(values["valid_for_seconds"], "valid_for_seconds",
                  maximum=limits.max_valid_for_seconds)
    return ObservationReport(**values)


def report_hash(report: ObservationReport) -> str:
    """Hash canonical report intent, excluding receipt time and current policy."""
    if type(report) is not ObservationReport:
        raise _invalid("report")
    encoded = json.dumps(report.to_dict(), ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"), allow_nan=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class ObservationFreshness:
    """Server-derived times for a newly admitted report, not a presence lease."""

    received_at: str
    valid_until: str


def compute_freshness(report: ObservationReport, *, received_at: str,
                      limits: ObservationLimits = ObservationLimits()) -> ObservationFreshness:
    """Check a NEW report's age and derive bounded validity using Server time.

    Future reports beyond the configured tolerance fail. Small positive skew
    never grants more than the requested TTL from receipt. Past reports retain
    only their remaining observed lifetime. At valid_until, they are expired.
    Replays must use their stored receipt instead of calling this function again.
    """
    if type(report) is not ObservationReport or type(limits) is not ObservationLimits:
        raise _invalid("report" if type(report) is not ObservationReport else "limits")
    _positive_int(report.valid_for_seconds, "valid_for_seconds",
                  maximum=limits.max_valid_for_seconds)
    received = _timestamp(received_at, "received_at")
    observed = _timestamp(report.observed_at, "observed_at")
    if (observed - received).total_seconds() > limits.future_tolerance_seconds:
        raise _invalid("observed_at_future")
    try:
        ttl = timedelta(seconds=report.valid_for_seconds)
        valid_until = min(received + ttl, observed + ttl)
    except OverflowError:
        raise _invalid("valid_until") from None
    if valid_until <= received:
        raise _invalid("observed_at_expired")
    return ObservationFreshness(received_at=_iso(received), valid_until=_iso(valid_until))

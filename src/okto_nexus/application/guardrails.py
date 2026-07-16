"""Guardrail evaluator and enforcement service.

This slice evaluates table-owned communication guardrails before write paths
persist raw communication content. It mirrors the governance denial pattern:
the main unit of work rolls back, then ``guardrail.denied`` is emitted in a
separate best-effort unit of work with scrubbed metadata only.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Iterator, Optional

from ..domain.guardrails import (
    ENFORCEMENT_MODE_AUDIT,
    ENFORCEMENT_MODE_ENFORCE,
    ENFORCEMENT_MODE_WARN,
    EVALUATOR_KIND_DETERMINISTIC,
    EffectiveGuardrail,
    RESOLUTION_CONFIG_UNAVAILABLE,
)
from ..errors import ErrorCode, OktoNexusError
from .ports import (
    AgentRepo,
    Clock,
    ConnectionFactory,
    EventEmitter,
    GuardrailAssignmentRepo,
    Tokenizer,
    UnitOfWork,
)

GUARDRAIL_STREAM = "workspace"
GUARDRAIL_DENIED_EVENT = "guardrail.denied"
DENIED_VISIBILITY = "public"

REASON_REGEX_MATCH = "regex_match"
REASON_KEYWORD_HIT = "keyword_hit"
REASON_PII_DETECTED = "pii_detected"
REASON_TOKEN_OVER_LIMIT = "token_over_limit"
REASON_UNEVALUABLE_REFERENCE = "unevaluable_reference"
REASON_CONFIG_UNAVAILABLE = "config_unavailable"
REASON_CODES = frozenset(
    {
        REASON_REGEX_MATCH,
        REASON_KEYWORD_HIT,
        REASON_PII_DETECTED,
        REASON_TOKEN_OVER_LIMIT,
        REASON_UNEVALUABLE_REFERENCE,
        REASON_CONFIG_UNAVAILABLE,
    }
)

SURFACE_ALIASES = {
    "message_create": "message",
    "message": "message",
    "artifact_put": "artifact",
    "artifact": "artifact",
    "handoff_create": "handoff",
    "handoff": "handoff",
}

_MODE_RANK = {
    ENFORCEMENT_MODE_AUDIT: 0,
    ENFORCEMENT_MODE_WARN: 1,
    ENFORCEMENT_MODE_ENFORCE: 2,
}
_SUPPORTED_DETERMINISTIC_KINDS = frozenset(
    {"regex", "keyword_blocklist", "pii_detection", "token_limit"}
)
_HASH_PREFIX = b"okto-nexus.guardrail.v1\0"
_MAX_PATTERN_LENGTH = 1000

_PII_PATTERNS = (
    re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    re.compile(r"\b(?:\+?\d[\d .()-]{7,}\d)\b"),
)

_FORBIDDEN_AUDIT_KEYS = frozenset(
    {
        "subject",
        "body",
        "payload",
        "content",
        "acceptance_criteria",
        "excerpt",
        "excerpts",
        "keyword",
        "keywords",
        "capture",
        "captures",
        "pii",
    }
)


@dataclass(frozen=True)
class GuardrailDecision:
    """One scrubbed decision for a resolved guardrail."""

    guardrail_id: str | None
    guardrail_version: int | None
    assignment_id: str | None
    assignment_scope: str | None
    group_id: str | None
    surface: str
    actor_agent_id: str
    mode: str
    reason_code: str | None
    matched: bool
    denied: bool
    fingerprint: str | None = None
    byte_size: int | None = None
    token_count: int | None = None

    def to_scrubbed_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "guardrail_id": self.guardrail_id,
            "guardrail_version": self.guardrail_version,
            "assignment_id": self.assignment_id,
            "assignment_scope": self.assignment_scope,
            "group_id": self.group_id,
            "surface": self.surface,
            "actor_agent_id": self.actor_agent_id,
            "mode": self.mode,
            "reason_code": self.reason_code,
            "matched": self.matched,
            "denied": self.denied,
        }
        if self.fingerprint is not None:
            out["fingerprint"] = self.fingerprint
        if self.byte_size is not None:
            out["byte_size"] = self.byte_size
        if self.token_count is not None:
            out["token_count"] = self.token_count
        return out


@dataclass(frozen=True)
class GuardrailResult:
    """Scrubbed aggregate returned when no enforce-mode denial occurred."""

    surface: str
    actor_agent_id: str
    decisions: tuple[GuardrailDecision, ...]

    @property
    def denied(self) -> bool:
        return any(decision.denied for decision in self.decisions)

    def to_scrubbed_dict(self) -> dict[str, Any]:
        return {
            "surface": self.surface,
            "actor_agent_id": self.actor_agent_id,
            "denied": self.denied,
            "decisions": [decision.to_scrubbed_dict() for decision in self.decisions],
        }


class GuardrailService:
    """Resolve, evaluate and audit communication guardrails."""

    def __init__(
        self,
        *,
        connection_factory: ConnectionFactory,
        assignments: GuardrailAssignmentRepo,
        agents: AgentRepo,
        clock: Clock,
        tokenizer: Optional[Tokenizer] = None,
        event_emitter: Optional[EventEmitter] = None,
        max_evaluated_chars: int = 65_536,
    ) -> None:
        self._cf = connection_factory
        self._assignments = assignments
        self._agents = agents
        self._clock = clock
        self._tokenizer = tokenizer
        self._emitter = event_emitter
        self._max_evaluated_chars = int(max_evaluated_chars)

    @contextmanager
    def guard(
        self,
        *,
        workspace_id: str,
        actor_agent_id: Any,
        surface: Any,
        fields: Mapping[str, Any],
    ) -> Iterator[UnitOfWork]:
        """Open a guarded UoW and enforce before yielding it to the write path."""

        try:
            with self._cf.unit_of_work() as uow:
                self.enforce(
                    uow,
                    workspace_id=workspace_id,
                    actor_agent_id=actor_agent_id,
                    surface=surface,
                    fields=fields,
                )
                yield uow
        except OktoNexusError as exc:
            self.emit_denied(workspace_id=workspace_id, actor_agent_id=actor_agent_id, exc=exc)
            raise

    def enforce(
        self,
        uow: UnitOfWork,
        *,
        workspace_id: str,
        actor_agent_id: Any,
        surface: Any,
        fields: Mapping[str, Any],
    ) -> GuardrailResult:
        """Evaluate the actor's effective guardrails and raise on enforce denial."""

        del workspace_id  # reserved for future per-workspace policy partitioning
        normalised_surface = _surface(surface)
        actor = _actor_id(actor_agent_id)
        if actor is None or self._agents.get(uow, actor) is None:
            decision = _config_unavailable_decision(
                surface=normalised_surface,
                actor_agent_id=str(actor_agent_id) if actor_agent_id is not None else "",
                mode=ENFORCEMENT_MODE_ENFORCE,
                reason_code=REASON_CONFIG_UNAVAILABLE,
            )
            raise _denied_error(decision)

        decisions: list[GuardrailDecision] = []
        for effective in _collapse_strictest(self._assignments.effective_for_agent(uow, agent_id=actor)):
            decision = self._evaluate_effective(
                effective,
                surface=normalised_surface,
                actor_agent_id=actor,
                fields=fields,
            )
            if decision is not None:
                decisions.append(decision)

        enforce_denials = [decision for decision in decisions if decision.denied]
        if enforce_denials:
            raise _denied_error(enforce_denials[0])
        return GuardrailResult(
            surface=normalised_surface,
            actor_agent_id=actor,
            decisions=tuple(decisions),
        )

    def has_enabled_assignments(self, uow: UnitOfWork) -> bool:
        """Whether runtime enforcement has any enabled guardrail assignment."""

        return any(assignment.enabled for assignment in self._assignments.list(uow))

    def emit_denied(
        self,
        *,
        workspace_id: str,
        actor_agent_id: Any,
        exc: OktoNexusError,
    ) -> None:
        """Emit ``guardrail.denied`` after rollback, best-effort and scrubbed."""

        if exc.code != ErrorCode.GUARDRAIL_DENIED.value or self._emitter is None:
            return
        payload = _scrub_denial_payload(exc.details or {})
        payload["created_at"] = self._clock.now_iso()
        if payload.get("actor_agent_id") is None:
            payload["actor_agent_id"] = (
                str(actor_agent_id) if actor_agent_id is not None else None
            )
        try:
            with self._cf.unit_of_work() as uow:
                self._emitter.emit(
                    uow,
                    workspace_id=workspace_id,
                    stream=GUARDRAIL_STREAM,
                    type=GUARDRAIL_DENIED_EVENT,
                    payload=payload,
                    actor_agent_id=payload.get("actor_agent_id"),
                    visibility=DENIED_VISIBILITY,
                    target=None,
                )
        except Exception:  # noqa: BLE001 - audit failures never replace the caller error
            return

    def _evaluate_effective(
        self,
        effective: EffectiveGuardrail,
        *,
        surface: str,
        actor_agent_id: str,
        fields: Mapping[str, Any],
    ) -> GuardrailDecision | None:
        assignment = effective.assignment
        version = effective.version
        if version is not None and surface not in set(version.surfaces):
            return None
        mode = assignment.mode
        if (
            version is None
            or effective.resolution_status == RESOLUTION_CONFIG_UNAVAILABLE
        ):
            return _config_unavailable_decision(
                surface=surface,
                actor_agent_id=actor_agent_id,
                mode=mode,
                effective=effective,
            )
        if version.evaluator_kind != EVALUATOR_KIND_DETERMINISTIC:
            return _config_unavailable_decision(
                surface=surface,
                actor_agent_id=actor_agent_id,
                mode=mode,
                effective=effective,
            )

        config = version.evaluator_config
        kind = str(config.get("kind") or "").strip().lower()
        if kind not in _SUPPORTED_DETERMINISTIC_KINDS:
            return _config_unavailable_decision(
                surface=surface,
                actor_agent_id=actor_agent_id,
                mode=mode,
                effective=effective,
            )

        values = _field_values(
            fields,
            field_targets=version.field_targets,
            max_chars=self._max_evaluated_chars,
        )
        if not values:
            return _matched_decision(
                effective,
                surface=surface,
                actor_agent_id=actor_agent_id,
                mode=mode,
                reason_code=REASON_UNEVALUABLE_REFERENCE,
                matched=True,
            )
        text = "\n".join(value for _field, value in values)
        byte_size = len(text.encode("utf-8"))
        fingerprint = _fingerprint(
            guardrail_id=assignment.guardrail_id,
            version=version.version,
            surface=surface,
            text=text,
        )

        try:
            if kind == "regex":
                reason = _eval_regex(config, [value for _field, value in values])
                token_count = None
            elif kind == "keyword_blocklist":
                reason = _eval_keyword(config, [value for _field, value in values])
                token_count = None
            elif kind == "pii_detection":
                reason = _eval_pii([value for _field, value in values])
                token_count = None
            else:
                reason, token_count = self._eval_token_limit(config, text)
        except _ConfigUnavailable:
            return _config_unavailable_decision(
                surface=surface,
                actor_agent_id=actor_agent_id,
                mode=mode,
                effective=effective,
                byte_size=byte_size,
                fingerprint=fingerprint,
            )

        if reason is None:
            return _matched_decision(
                effective,
                surface=surface,
                actor_agent_id=actor_agent_id,
                mode=mode,
                reason_code=None,
                matched=False,
                byte_size=byte_size,
                token_count=token_count,
                fingerprint=None,
            )
        return _matched_decision(
            effective,
            surface=surface,
            actor_agent_id=actor_agent_id,
            mode=mode,
            reason_code=reason,
            matched=True,
            byte_size=byte_size,
            token_count=token_count,
            fingerprint=fingerprint,
        )

    def _eval_token_limit(
        self, config: Mapping[str, Any], text: str
    ) -> tuple[str | None, int | None]:
        raw_limit = config.get("max_tokens")
        if isinstance(raw_limit, bool) or not isinstance(raw_limit, int) or raw_limit < 0:
            raise _ConfigUnavailable
        if self._tokenizer is None or _tokenizer_is_degraded(self._tokenizer):
            raise _ConfigUnavailable
        try:
            count = int(self._tokenizer.count(text))
        except Exception as exc:  # noqa: BLE001 - tokenizer outage is config unavailable to callers
            raise _ConfigUnavailable from exc
        if count > raw_limit:
            return REASON_TOKEN_OVER_LIMIT, count
        return None, count


class _ConfigUnavailable(Exception):
    """Internal sentinel: evaluator cannot be trusted for fail-open decisions."""


def _surface(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text not in SURFACE_ALIASES:
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            "surface must be one of message, artifact, handoff or their write-path aliases.",
            {"surface": value, "supported": sorted(SURFACE_ALIASES)},
        )
    return SURFACE_ALIASES[text]


def _actor_id(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _collapse_strictest(items: Sequence[EffectiveGuardrail]) -> list[EffectiveGuardrail]:
    collapsed: dict[tuple[str, int | None], EffectiveGuardrail] = {}
    for item in items:
        version_key = item.version.version if item.version is not None else None
        key = (item.assignment.guardrail_id, version_key)
        current = collapsed.get(key)
        if current is None:
            collapsed[key] = item
            continue
        if _MODE_RANK[item.assignment.mode] > _MODE_RANK[current.assignment.mode]:
            collapsed[key] = item
    return sorted(
        collapsed.values(),
        key=lambda item: (
            item.assignment.priority,
            item.assignment.guardrail_id,
            item.assignment.assignment_id,
        ),
    )


def _field_values(
    fields: Mapping[str, Any],
    *,
    field_targets: Sequence[str],
    max_chars: int,
) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for target in field_targets:
        raw = _field_lookup(fields, target)
        if raw is None:
            continue
        text = _stringify_field(raw)
        if text is None:
            continue
        if len(text) > max_chars:
            raise _ConfigUnavailable
        if text:
            out.append((str(target), text))
    return out


def _field_lookup(fields: Mapping[str, Any], target: str) -> Any:
    if target in fields:
        return fields[target]
    current: Any = fields
    for part in str(target).split("."):
        if isinstance(current, Mapping) and part in current:
            current = current[part]
        else:
            return None
    return current


def _stringify_field(raw: Any) -> str | None:
    if raw is None:
        return None
    if isinstance(raw, str):
        return raw
    if isinstance(raw, (bytes, bytearray)):
        return None
    if isinstance(raw, Mapping) or (
        isinstance(raw, Sequence) and not isinstance(raw, (str, bytes, bytearray))
    ):
        return json.dumps(raw, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return str(raw)


@lru_cache(maxsize=512)
def _compile_regex(pattern: str, flags: int) -> re.Pattern[str]:
    return re.compile(pattern, flags)


def _eval_regex(config: Mapping[str, Any], texts: Sequence[str]) -> str | None:
    patterns = config.get("patterns")
    if not _nonempty_str_list(patterns):
        raise _ConfigUnavailable
    flags = re.IGNORECASE if bool(config.get("ignore_case", False)) else 0
    for pattern in patterns:
        if len(pattern) > _MAX_PATTERN_LENGTH:
            raise _ConfigUnavailable
        try:
            compiled = _compile_regex(pattern, flags)
        except re.error as exc:
            raise _ConfigUnavailable from exc
        if any(compiled.search(text) for text in texts):
            return REASON_REGEX_MATCH
    return None


def _eval_keyword(config: Mapping[str, Any], texts: Sequence[str]) -> str | None:
    keywords = config.get("keywords")
    if not _nonempty_str_list(keywords):
        raise _ConfigUnavailable
    case_sensitive = bool(config.get("case_sensitive", False))
    haystacks = list(texts) if case_sensitive else [text.casefold() for text in texts]
    needles = list(keywords) if case_sensitive else [word.casefold() for word in keywords]
    for needle in needles:
        if not needle:
            raise _ConfigUnavailable
        if any(needle in haystack for haystack in haystacks):
            return REASON_KEYWORD_HIT
    return None


def _eval_pii(texts: Sequence[str]) -> str | None:
    for text in texts:
        if any(pattern.search(text) for pattern in _PII_PATTERNS):
            return REASON_PII_DETECTED
    return None


def _nonempty_str_list(value: Any) -> bool:
    return (
        isinstance(value, Sequence)
        and not isinstance(value, (str, bytes, bytearray))
        and bool(value)
        and all(isinstance(item, str) and item for item in value)
    )


def _tokenizer_is_degraded(tokenizer: Tokenizer) -> bool:
    if bool(getattr(tokenizer, "degraded", False)):
        return True
    encoding = str(getattr(tokenizer, "encoding", "") or "")
    return encoding.startswith("approx")


def _fingerprint(
    *,
    guardrail_id: str,
    version: int,
    surface: str,
    text: str,
) -> str:
    h = hashlib.sha256()
    h.update(_HASH_PREFIX)
    h.update(guardrail_id.encode("utf-8"))
    h.update(b"\0")
    h.update(str(version).encode("ascii"))
    h.update(b"\0")
    h.update(surface.encode("utf-8"))
    h.update(b"\0")
    h.update(text.encode("utf-8"))
    return h.hexdigest()


def _config_unavailable_decision(
    *,
    surface: str,
    actor_agent_id: str,
    mode: str,
    reason_code: str = REASON_CONFIG_UNAVAILABLE,
    effective: EffectiveGuardrail | None = None,
    byte_size: int | None = None,
    fingerprint: str | None = None,
) -> GuardrailDecision:
    assignment = effective.assignment if effective is not None else None
    version = effective.version if effective is not None else None
    return GuardrailDecision(
        guardrail_id=assignment.guardrail_id if assignment is not None else None,
        guardrail_version=version.version if version is not None else None,
        assignment_id=assignment.assignment_id if assignment is not None else None,
        assignment_scope=assignment.scope_kind if assignment is not None else None,
        group_id=assignment.group_id if assignment is not None else None,
        surface=surface,
        actor_agent_id=actor_agent_id,
        mode=mode,
        reason_code=reason_code,
        matched=True,
        denied=mode == ENFORCEMENT_MODE_ENFORCE,
        byte_size=byte_size,
        fingerprint=fingerprint,
    )


def _matched_decision(
    effective: EffectiveGuardrail,
    *,
    surface: str,
    actor_agent_id: str,
    mode: str,
    reason_code: str | None,
    matched: bool,
    byte_size: int | None = None,
    token_count: int | None = None,
    fingerprint: str | None = None,
) -> GuardrailDecision:
    assignment = effective.assignment
    version = effective.version
    return GuardrailDecision(
        guardrail_id=assignment.guardrail_id,
        guardrail_version=version.version if version is not None else None,
        assignment_id=assignment.assignment_id,
        assignment_scope=assignment.scope_kind,
        group_id=assignment.group_id,
        surface=surface,
        actor_agent_id=actor_agent_id,
        mode=mode,
        reason_code=reason_code,
        matched=matched,
        denied=matched and mode == ENFORCEMENT_MODE_ENFORCE,
        fingerprint=fingerprint if matched else None,
        byte_size=byte_size,
        token_count=token_count,
    )


def _denied_error(decision: GuardrailDecision) -> OktoNexusError:
    details = decision.to_scrubbed_dict()
    return OktoNexusError(
        ErrorCode.GUARDRAIL_DENIED,
        "Communication denied by guardrail.",
        details,
    )


def _scrub_denial_payload(details: Mapping[str, Any]) -> dict[str, Any]:
    allowed = {
        "guardrail_id",
        "guardrail_version",
        "assignment_id",
        "assignment_scope",
        "group_id",
        "surface",
        "actor_agent_id",
        "mode",
        "reason_code",
        "fingerprint",
        "byte_size",
        "token_count",
    }
    payload = {key: details.get(key) for key in allowed if key in details}
    payload["reason_code"] = (
        payload.get("reason_code")
        if payload.get("reason_code") in REASON_CODES
        else REASON_CONFIG_UNAVAILABLE
    )
    for key in _FORBIDDEN_AUDIT_KEYS:
        payload.pop(key, None)
    return payload

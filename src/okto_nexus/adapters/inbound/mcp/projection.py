"""MCP response projection (Frente 2 - per-call token reduction).

The per-call cost lever: high-volume tool responses (inbox_pull/peek,
event_get/event_wait) recur on EVERY turn, so this helper trims their payloads
behind a ``profile`` knob - ALWAYS inside the canonical ``data`` envelope, never
touching it. It lives ONLY here, in the inbound MCP adapter's serialization
layer: domain/application return the COMPLETE item dicts (``event_to_dict`` /
``InboxService._item``) and this module projects them. The core stays pure and
profile-unaware (import boundary enforced).

Profiles (design lock - assertiveness > tokens):

* ``default`` (when omitted): SAFE-TRIM. Removes only proven-dead/duplicate -
  the always-null ``task_id``, empty collections, and the promoted scalars that
  duplicate ``payload`` (deduped out of the payload copy). KEEPS every
  contextual field. Zero assertiveness risk.
* ``summary`` (opt-in): aggressive. Drops the contextual non-load-bearing fields
  and OMITS the heavy body/payload (with a ``follow_up`` pointing at how to
  re-fetch it). ``message_id`` is ALWAYS present (``inbox_ack`` needs it).
* ``full`` (opt-in): the raw item, untouched - the debugging escape hatch.

Telemetry rides in ``data``: ``payload_bytes`` (deterministic size of the
projected items), ``omitted_count`` (top-level keys/heavy fields dropped vs
full, summed over the page), ``truncated`` (a heavy field hit the
``MAX_ITEM_BYTES`` safety ceiling). The canonical ``{ok,data}`` envelope and the
pagination defaults are untouched.
"""

from __future__ import annotations

import json
from typing import Any

from ....domain.handoff import (
    EVENT_DEPENDENCY_FAILED,
    EVENT_UNBLOCKED,
    EVENT_VERIFICATION_FAILED,
    EVENT_VERIFICATION_REQUESTED,
)
from ....domain.memory import MEMORY_CREATED_EVENT, MEMORY_SUPERSEDED_EVENT
from ....errors import ErrorCode, OktoNexusError

#: I4 verification events whose ``handoff_id`` correlator must survive EVERY
#: profile (the consumer's next step is always "act on that handoff").
_VERIFICATION_EVENT_TYPES = frozenset(
    {EVENT_VERIFICATION_REQUESTED, EVENT_VERIFICATION_FAILED}
)
#: I5 DAG events, same rationale: the consumer's next step is "act on THAT
#: handoff" (claim the freshly unblocked dependent; decide the dependent whose
#: edge terminally failed), so the correlator survives the summary too.
_DAG_EVENT_TYPES = frozenset({EVENT_UNBLOCKED, EVENT_DEPENDENCY_FAILED})
#: The union the summary profile promotes ``handoff_id`` for; scoped by event
#: type so every OTHER summary shape stays byte-identical (TR5 / the I1
#: projection-allowlist lesson).
_HANDOFF_CORRELATED_EVENT_TYPES = _VERIFICATION_EVENT_TYPES | _DAG_EVENT_TYPES
#: I6 memory events, same rationale: the consumer's next step is "act on THAT
#: memory" (memory_get it, or supersede it), so ``memory_id`` is promoted from
#: the payload on every profile - scoped by event type so every other shape
#: stays byte-identical.
_MEMORY_EVENT_TYPES = frozenset({MEMORY_CREATED_EVENT, MEMORY_SUPERSEDED_EVENT})

PROFILE_DEFAULT = "default"
PROFILE_SUMMARY = "summary"
PROFILE_FULL = "full"
#: Closed vocabulary; an unknown value fails loud (never a silent fallback).
PROFILES: tuple[str, ...] = (PROFILE_DEFAULT, PROFILE_SUMMARY, PROFILE_FULL)

#: Per-item safety ceiling (bytes) for a RETURNED heavy field. Only the event
#: ``payload`` is capped (it is re-fetchable via ``event_get profile=full``); the
#: inbox ``body`` is the consumer's payload and is never truncated (truncating it
#: would strand the message - "assertiveness > tokens").
MAX_ITEM_BYTES = 16384

FOLLOW_UP_REL = "read_full"

#: Event fields that are ALWAYS present (essence/triage).
_EVENT_ALWAYS = ("event_id", "type", "actor_agent_id", "created_at", "stream")
#: Scalars promoted from ``payload`` to top-level (duplicated inside payload).
#: ``approval_id`` (I3) is promoted AT PROJECTION TIME below: it only exists
#: inside approval.* payloads, and the blocked requester correlates its
#: pending action by it - so it must survive every profile.
_EVENT_PROMOTED = ("task_id", "handoff_id", "trace_id", "approval_id")

#: Inbox fields that are ALWAYS present.
_INBOX_ALWAYS = ("message_id", "from_agent_id", "subject", "created_at", "status")
#: Inbox contextual fields kept in default/full, dropped in summary.
_INBOX_CONTEXTUAL = (
    "target",
    "delivery_id",
    "workspace_id",
    "channel_id",
    "lease_expires_at",
    "read_at",
    "delivered_at",
)


def parse_profile(value: Any) -> str:
    """Resolve a ``profile`` argument to a supported value (default when absent).

    ``None``/blank -> ``default``. Anything outside :data:`PROFILES` raises a
    canonical ``VALIDATION_ERROR`` listing the supported profiles (BR9) - never
    a silent fallback.
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        return PROFILE_DEFAULT
    candidate = str(value).strip().lower()
    if candidate not in PROFILES:
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            f"Unsupported profile {value!r}. Supported: {', '.join(PROFILES)}.",
            {"profile": value, "supported": list(PROFILES)},
        )
    return candidate


def _json_bytes(obj: Any) -> int:
    """Deterministic UTF-8 byte length of ``obj`` serialized as compact JSON."""
    return len(
        json.dumps(obj, ensure_ascii=False, separators=(",", ":"), default=str).encode(
            "utf-8"
        )
    )


def _follow_up(target_ref: str) -> dict[str, str]:
    """The machine-readable affordance to re-fetch an omitted/truncated body."""
    return {"rel": FOLLOW_UP_REL, "target_ref": target_ref, "hint": "profile=full"}


def _is_empty(value: Any) -> bool:
    """Empty collection (``[]``/``{}``/``None``) - dropped by safe-trim."""
    return value is None or value == [] or value == {}


def project_event(
    raw: dict[str, Any], profile: str, *, target_ref: str = "event_get"
) -> tuple[dict[str, Any], int, bool]:
    """Project one ``event_to_dict`` item; return ``(projected, omitted, truncated)``.

    ``omitted`` counts top-level keys present in the raw item but absent in the
    projection (heavy-field omission included).
    """
    full_keys = set(raw)
    if profile == PROFILE_FULL:
        return dict(raw), 0, False

    out: dict[str, Any] = {k: raw[k] for k in _EVENT_ALWAYS if k in raw}
    truncated = False
    # trace_id (I1): the trajectory correlator is load-bearing - a consumer
    # filtering/stitching by trace must see it in EVERY profile, so it is kept
    # whenever non-null (assertiveness > tokens). Null stays omitted, which
    # keeps the flag-OFF shape byte-identical.
    if raw.get("trace_id") is not None:
        out["trace_id"] = raw["trace_id"]
    # approval_id (I3): the HITL correlator, same rationale. It lives ONLY
    # inside approval.* payloads (never top-level in event_to_dict), so it is
    # promoted here - the requester watching for approval.granted/denied must
    # see WHICH approval was decided even under the aggressive summary.
    raw_payload = raw.get("payload")
    if isinstance(raw_payload, dict) and raw_payload.get("approval_id") is not None:
        out["approval_id"] = raw_payload["approval_id"]
    # memory_id (I6): the memory correlator, same rationale - the consumer's
    # next step is "memory_get THAT id" (or supersede it). It lives only
    # inside memory.* payloads (never top-level in event_to_dict), so it is
    # promoted here - scoped by event type so every OTHER profile shape stays
    # byte-identical (TR5 / the I1 projection-allowlist lesson).
    if (
        raw.get("type") in _MEMORY_EVENT_TYPES
        and isinstance(raw_payload, dict)
        and raw_payload.get("memory_id") is not None
    ):
        out["memory_id"] = raw_payload["memory_id"]

    if profile == PROFILE_SUMMARY:
        # Aggressive: drop task_id/handoff_id/workspace_id and OMIT payload.
        # EXCEPT the I4 verification + I5 DAG events: their whole point is
        # "go act on THIS handoff" (verifier -> handoff_verify; claimant ->
        # rework; eligible agent -> claim the unblocked dependent; creator ->
        # decide the dependent with a failed edge), so the correlator
        # survives the aggressive profile too (TR4 - the approval_id
        # rationale). Scoped by event type so every pre-existing summary
        # shape stays byte-identical.
        if (
            raw.get("type") in _HANDOFF_CORRELATED_EVENT_TYPES
            and raw.get("handoff_id") is not None
        ):
            out["handoff_id"] = raw["handoff_id"]
        if raw.get("payload") not in (None, {}):
            out["follow_up"] = _follow_up(target_ref)
        return out, len(full_keys - set(out)), False

    # default (safe-trim): keep handoff_id (non-null) + workspace_id; dedup payload.
    if raw.get("handoff_id") is not None:
        out["handoff_id"] = raw["handoff_id"]
    if "workspace_id" in raw:
        out["workspace_id"] = raw["workspace_id"]
    # task_id is always-null dead weight (Tasks subsystem removed) -> never kept.
    payload = raw.get("payload")
    if isinstance(payload, dict):
        # DEDUP: drop the promoted scalars that are duplicated inside payload.
        # memory_id joins the promoted set ONLY for memory.* events (where it
        # was promoted above) - dropping it from any other event's payload
        # would LOSE it, since nothing promotes it there.
        promoted = set(_EVENT_PROMOTED)
        if raw.get("type") in _MEMORY_EVENT_TYPES:
            promoted.add("memory_id")
        deduped = {k: v for k, v in payload.items() if k not in promoted}
        if deduped:
            if _json_bytes(deduped) > MAX_ITEM_BYTES:
                # Oversized payload: omit it + follow_up (re-fetch via full).
                out["follow_up"] = _follow_up(target_ref)
                truncated = True
            else:
                out["payload"] = deduped
        # empty after dedup -> payload omitted
    elif payload not in (None, {}):
        out["payload"] = payload
    return out, len(full_keys - set(out)), truncated


def project_inbox_item(
    raw: dict[str, Any], profile: str, *, target_ref: str = "inbox_peek"
) -> tuple[dict[str, Any], int, bool]:
    """Project one ``InboxService._item``; return ``(projected, omitted, truncated)``."""
    full_keys = set(raw)
    if profile == PROFILE_FULL:
        return dict(raw), 0, False

    out: dict[str, Any] = {k: raw[k] for k in _INBOX_ALWAYS if k in raw}
    # body_preview/body_bytes (peek) are already bounded and triage-useful: keep.
    for k in ("body_preview", "body_bytes"):
        if k in raw:
            out[k] = raw[k]
    # artifacts: keep only when non-empty (drop [] in default and summary).
    if not _is_empty(raw.get("artifacts")):
        out["artifacts"] = raw["artifacts"]
    # trace_id (I1): the recipient must SEE the trace to carry it into its next
    # send - trajectory continuity is load-bearing, so the key survives EVERY
    # profile (assertiveness > tokens). It only exists when non-null (D4).
    if raw.get("trace_id") is not None:
        out["trace_id"] = raw["trace_id"]

    if profile == PROFILE_SUMMARY:
        # Drop contextual fields; OMIT the heavy body (with follow_up).
        if "body" in raw and raw.get("body"):
            out["follow_up"] = _follow_up(target_ref)
        return out, len(full_keys - set(out)), False

    # default (safe-trim): KEEP contextual fields + full body untouched.
    for k in _INBOX_CONTEXTUAL:
        if k in raw:
            out[k] = raw[k]
    if "body" in raw:
        out["body"] = raw["body"]
    return out, len(full_keys - set(out)), False


_PROJECTORS = {"event": project_event, "inbox": project_inbox_item}
_TARGETS = {"event": "event_get", "inbox": "inbox_peek"}


def project_page(
    items: list[dict[str, Any]],
    profile: str,
    *,
    kind: str,
    target_ref: str | None = None,
) -> dict[str, Any]:
    """Project a page of ``kind`` items and attach telemetry.

    Returns ``{items, payload_bytes, omitted_count, truncated}`` - the projected
    list plus the deterministic per-call telemetry (``payload_bytes`` measured
    over the projected ``items``, excluding the telemetry fields themselves).
    ``kind`` is ``"event"`` or ``"inbox"``; the projector and the ``follow_up``
    ``target_ref`` are chosen per kind unless ``target_ref`` is overridden.
    """
    projector = _PROJECTORS[kind]
    ref = target_ref or _TARGETS[kind]
    projected: list[dict[str, Any]] = []
    omitted_total = 0
    truncated_any = False
    for raw in items:
        item, omitted, truncated = projector(raw, profile, target_ref=ref)
        projected.append(item)
        omitted_total += omitted
        truncated_any = truncated_any or truncated
    return {
        "items": projected,
        "payload_bytes": _json_bytes(projected),
        "omitted_count": omitted_total,
        "truncated": truncated_any,
    }


def apply_to_response(
    result: dict[str, Any],
    items_key: str,
    profile: str,
    *,
    kind: str,
    target_ref: str | None = None,
) -> dict[str, Any]:
    """Project the ``items_key`` list of a tool's ``data`` in place + add telemetry.

    The single wiring seam the high-volume tools call: replaces
    ``result[items_key]`` with its projected form and merges
    ``payload_bytes``/``omitted_count``/``truncated`` into ``result`` - all
    INSIDE ``data`` (the canonical envelope is assembled elsewhere and never
    touched). Returns the same ``result`` for chaining.
    """
    page = project_page(
        result.get(items_key) or [], profile, kind=kind, target_ref=target_ref
    )
    result[items_key] = page["items"]
    result["payload_bytes"] = page["payload_bytes"]
    result["omitted_count"] = page["omitted_count"]
    result["truncated"] = page["truncated"]
    return result

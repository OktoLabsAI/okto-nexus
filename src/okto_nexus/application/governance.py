"""Policy enforcement slice application service (spec 80624c1a, unified policy).

The bus enforces the caller's ATTACHED policies PRE-persistence inside each
write path's own unit of work. A policy unifies audience + governance into one
versionable object attached to an agent via BINDINGS (spec 80624c1a); this
service composes the caller's effective sources (its resolved bindings) and
applies their union. Enforcement is ALWAYS-ON and binding-driven - there is no
feature flag (D-FLAG): an actor with NO bindings composes to nothing and passes,
byte-identical to the pre-policy bus (BR2 zero-regression). This module owns:

* :meth:`GovernanceService.enforce` - the single governance enforcement point
  the write paths call AFTER their permission gate / recipient resolution and
  BEFORE the ``.create()``. It resolves the caller's effective sources (its
  bindings), runs the union of their governance rules matching the action
  through :func:`domain.policy.combined_governance_verdict`, pre-fetching the
  caller's consumption ON-DEMAND in the same UoW (never a counter table) and
  raising ``POLICY_DENIED`` (categorical deny, REST 403) or ``QUOTA_EXCEEDED``
  (quota, REST 429) with normative details about the ONE rule that barred (BR5 -
  never other agents' state).
* :meth:`GovernanceService.audience_reachable` - policy-aware reachability
  between two agents (FR6/BR13), used to gate a declared ``handoff_create``
  target at creation.
* :meth:`GovernanceService.emit_denied` - the audit event
  ``governance.denied``, emitted in a SEPARATE short UoW after the main one
  rolled back (precedent: the best-effort embedding write in messages.py).
  Best-effort: any failure is swallowed and the caller's error is unchanged
  (BR6). The payload never carries subject/body.
* Operator CRUD (create/list/update/delete) over the legacy governance_policies
  table with fail-closed validation (kept until the /policies surface in B1
  supersedes it; migration 022 already mirrored these rows into detached global
  policies).
* :meth:`GovernanceService.policies_for_agent` - the caller-scoped view backing
  the conditional ``governance`` block of ``agent_whoami`` (FR11).

Application layer: ports + domain + errors only; never imports ``sqlite3`` nor
``mcp`` (enforced by the import-boundary test).
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator, Optional

from ..domain.base import iso_plus, new_id
from ..domain.governance import (
    ACTION_BROADCAST,
    ACTION_MESSAGE_CREATE,
    EVENT_DENIED,
    LIMIT_DENY,
    LIMIT_MAX_COUNT,
    LIMIT_MAX_OPEN_HANDOFFS,
    SUBJECT_AGENT,
    SUBJECT_CAPABILITY,
    WINDOW_SECONDS,
    ApprovalRequired,
    Policy,
    Violation,
    validate_policy_form,
)
from ..domain.policy import (
    BINDING_SOURCE_GLOBAL,
    EffectiveSource,
    combined_governance_verdict,
    effective_governance_policies,
    effective_policy_labels,
    outbound_snapshot,
    resolve_effective_sources,
)
from ..domain.policy import audience_reachable as policy_audience_reachable
from ..errors import ErrorCode, OktoNexusError
from .ports import (
    AgentPolicyBindingRepo,
    AgentRepo,
    CapabilityCatalogRepo,
    Clock,
    ConnectionFactory,
    EventEmitter,
    GovernanceRepo,
    PolicyRepo,
    UnitOfWork,
)

#: Stream + visibility of the audit event (BR6): workspace-wide and public so
#: the dashboard's Denials panel and any observer can read it.
GOVERNANCE_STREAM = "workspace"
DENIED_VISIBILITY = "public"

#: The codes this slice owns; ``emit_denied`` only reacts to these.
_DENIAL_CODES = frozenset(
    {ErrorCode.POLICY_DENIED.value, ErrorCode.QUOTA_EXCEEDED.value}
)


def message_action_for(target: Any, channel_id: Any = None) -> str:
    """Classify one message send as ``broadcast`` or plain ``message_create``.

    Broadcast is the EXPLICIT ``{"strategy": "broadcast"}`` target or the
    target-less, channel-less send (which fans out to every present agent -
    the same reach, so a broadcast deny must cover it; a broadcast nested in
    ``mixed`` is already rejected upstream by the deliverability gate). A
    channel post without a target is a plain ``message_create``.
    """
    if isinstance(target, dict):
        strategy = target.get("strategy")
        return ACTION_BROADCAST if strategy == "broadcast" else ACTION_MESSAGE_CREATE
    if target is None and channel_id is None:
        return ACTION_BROADCAST
    return ACTION_MESSAGE_CREATE


def policy_to_dict(policy: Policy) -> dict[str, Any]:
    """Serialise one policy for REST / whoami responses (full snapshot)."""
    return {
        "policy_id": policy.policy_id,
        "subject_kind": policy.subject_kind,
        "subject_value": policy.subject_value,
        "action": policy.action,
        "limit_kind": policy.limit_kind,
        "limit_value": policy.limit_value,
        "window": policy.window,
        "enabled": policy.enabled,
        "created_at": policy.created_at,
    }


class GovernanceService:
    """Enforcement + operator CRUD for governance policies."""

    def __init__(
        self,
        *,
        connection_factory: ConnectionFactory,
        governance: GovernanceRepo,
        clock: Clock,
        config: Any = None,
        agents: Optional[AgentRepo] = None,
        capability_catalog: Optional[CapabilityCatalogRepo] = None,
        event_emitter: Optional[EventEmitter] = None,
        policies: Optional[PolicyRepo] = None,
        policy_bindings: Optional[AgentPolicyBindingRepo] = None,
    ) -> None:
        self._cf = connection_factory
        self._governance = governance
        self._clock = clock
        self._config = config
        self._agents = agents
        self._capability_catalog = capability_catalog
        self._emitter = event_emitter
        # Unified-policy sources (spec 80624c1a): the actor's bindings + their
        # resolved versions are what enforcement now composes over. Optional so
        # partial wirings (and the many hand-rolled test Deps) degrade to "no
        # bindings = no governance" - the zero-regression default (BR2/BR9).
        self._policies = policies
        self._policy_bindings = policy_bindings

    def _feature_hitl_on(self) -> bool:
        # Same LIVE-read discipline for the HITL third stage (spec 2948b2a2
        # BR6): the flag gates ONLY whether an ApprovalRequired verdict is
        # promoted to an interception - pending rows stay decidable elsewhere.
        return bool(getattr(self._config, "feature_hitl", False))

    # ------------------------------------------------------------------ #
    # Write-path UoW wrapper
    # ------------------------------------------------------------------ #
    @contextmanager
    def guard(self, *, workspace_id: str, agent_id: Any) -> Iterator[UnitOfWork]:
        """Unit-of-work wrapper for a governed write path.

        Behaves exactly like ``connection_factory.unit_of_work()`` except that
        when the body raises one of this slice's denial errors, the
        ``governance.denied`` audit event is emitted in a SEPARATE UoW right
        AFTER the main one rolled back (BR6) and the error propagates
        unchanged. Non-denial errors pass straight through, event-free.
        """
        try:
            with self._cf.unit_of_work() as uow:
                yield uow
        except OktoNexusError as exc:
            self.emit_denied(workspace_id=workspace_id, agent_id=agent_id, exc=exc)
            raise

    # ------------------------------------------------------------------ #
    # Enforcement (called inside the write path's UoW)
    # ------------------------------------------------------------------ #
    def enforce(
        self,
        uow: UnitOfWork,
        *,
        agent_id: Any,
        action: str,
        size_bytes: int = 0,
    ) -> ApprovalRequired | None:
        """Deny-, intercept- or pass gate for one ``action`` by ``agent_id``.

        Always-on, binding-driven (spec 80624c1a, D-FLAG/BR9): there is no
        feature flag. The caller's effective sources (its resolved bindings) are
        composed and the union of their governance rules matching ``action`` is
        run through the same :func:`governance.decide`. An actor with NO bindings
        resolves to no sources -> no rules -> pass: byte-identical to today's
        flag-OFF flow, the zero-regression guarantee (BR2). Count-based quotas
        pre-fetch their consumption ON-DEMAND in the SAME UoW (never a counter
        table - the window COUNTs see exactly the pre-write state), keyed by the
        synthetic per-rule id :func:`effective_governance_policies` assigns.
        Callers WITHOUT an identity (cooperative stdio) can hold no bindings, so
        they pass (nothing is attached to a non-identity).

        HITL (spec 2948b2a2): when the action would have passed and a
        ``require_approval`` rule matches AND ``feature_hitl`` is ON (read
        live), the verdict is RETURNED so the write path intercepts into the
        approvals queue; ``None`` still means plain allow.
        """
        caller = str(agent_id) if agent_id is not None and str(agent_id) else ""
        sources = self._effective_sources(uow, caller)
        if not sources:
            return None
        applicable = effective_governance_policies(sources, action)
        if not applicable:
            return None
        now = self._clock.now_iso()
        usage: dict[str, int] = {}
        for policy in applicable:
            if policy.limit_kind == LIMIT_MAX_COUNT:
                if not caller:
                    usage[policy.policy_id] = 0
                    continue
                seconds = WINDOW_SECONDS[policy.window or "1h"]
                usage[policy.policy_id] = self._governance.actions_since(
                    uow,
                    agent_id=caller,
                    action=policy.action,
                    since=iso_plus(now, -float(seconds)),
                )
            elif policy.limit_kind == LIMIT_MAX_OPEN_HANDOFFS:
                usage[policy.policy_id] = (
                    self._governance.open_handoffs(uow, agent_id=caller)
                    if caller
                    else 0
                )
        verdict = combined_governance_verdict(
            sources, action=action, size_bytes=int(size_bytes), usage=usage
        )
        if isinstance(verdict, Violation):
            raise self._violation_error(verdict, action)
        if isinstance(verdict, ApprovalRequired) and self._feature_hitl_on():
            # HITL third stage (spec 2948b2a2): the action WOULD have passed
            # and a require_approval rule matched. Returned - never raised -
            # so the write path intercepts into the approvals queue. With
            # feature_hitl OFF the verdict is dropped here: accept-and-ignore
            # TOTAL, byte-identical to the no-rule flow (D4/BR6).
            return verdict
        return None

    def _effective_sources(
        self, uow: UnitOfWork, agent_id: str
    ) -> list[EffectiveSource]:
        """Resolve ``agent_id``'s bindings to its ordered effective sources (TR4).

        The single resolver the write paths share: read the agent's bindings,
        bulk-fetch the versions its GLOBAL bindings reference, and hand both to
        the pure :func:`resolve_effective_sources` (inline source first, globals
        by ``published_at``). Empty (no repo wired, no identity, or no bindings)
        means an unrestricted, ungoverned actor - the zero-regression default.
        """
        if self._policy_bindings is None or not agent_id:
            return []
        bindings = self._policy_bindings.list_for_agent(uow, agent_id=agent_id)
        if not bindings:
            return []
        policy_ids = sorted(
            {
                str(b.get("policy_id"))
                for b in bindings
                if b.get("source") == BINDING_SOURCE_GLOBAL and b.get("policy_id")
            }
        )
        versions_by_policy = (
            self._policies.versions_for(uow, policy_ids=policy_ids)
            if policy_ids and self._policies is not None
            else {}
        )
        return resolve_effective_sources(bindings, versions_by_policy)

    def outbound_snapshot_for(self, uow: UnitOfWork, *, agent_id: Any) -> list[Any]:
        """Freeze ``agent_id``'s EFFECTIVE OUTBOUND audience (D-ART snapshot).

        Resolves the publisher's effective sources in the caller's UoW and folds
        their outbound selectors into an ordered list
        (:func:`domain.policy.outbound_snapshot`), stamped IMMUTABLY onto
        ``artifacts.audience`` at ``artifact_put`` time (D11). An actor with no
        bindings - or no identity - yields ``[]``: an unrestricted, public
        artifact, byte-identical to the pre-policy bus (BR2). Read gating
        (:func:`domain.policy.snapshot_permits`) re-evaluates the frozen list
        against a reader's tags; the ``artifact.created`` event carries the same
        audience so the stream never leaks what the read-path hides (BR7).
        """
        caller = str(agent_id) if agent_id is not None and str(agent_id) else ""
        if not caller:
            return []
        return outbound_snapshot(self._effective_sources(uow, caller))

    def audience_reachable(
        self,
        uow: UnitOfWork,
        *,
        sender_id: Any,
        sender_tags: Any,
        recipient_id: Any,
        recipient_tags: Any,
    ) -> bool:
        """Policy-aware reachability between two agents (FR6/BR13 helper).

        Resolves both sides' effective sources and applies the domain AND
        fail-safe (:func:`domain.policy.audience_reachable`): the sender's
        OUTBOUND must permit the recipient's tags AND the recipient's INBOUND
        must permit the sender's tags, with the equal-id self carve-out. Used by
        ``handoff_create`` to gate a declared target at creation; both sides
        without bindings reduce to unrestricted (True).
        """
        sender_sources = self._effective_sources(
            uow, str(sender_id) if sender_id is not None else ""
        )
        recipient_sources = self._effective_sources(
            uow, str(recipient_id) if recipient_id is not None else ""
        )
        return policy_audience_reachable(
            sender_sources=sender_sources,
            sender_tags=sender_tags,
            sender_id=sender_id,
            recipient_sources=recipient_sources,
            recipient_tags=recipient_tags,
            recipient_id=recipient_id,
        )

    @staticmethod
    def _violation_error(violation: Violation, action: str) -> OktoNexusError:
        """Map the domain verdict to the canonical error (BR5 details)."""
        policy = violation.policy
        details: dict[str, Any] = {
            "policy_id": policy.policy_id,
            "action": action,
            "limit_kind": policy.limit_kind,
        }
        if policy.limit_kind == LIMIT_DENY:
            return OktoNexusError(
                ErrorCode.POLICY_DENIED,
                f"Denied by governance policy {policy.policy_id}: "
                f"{action} is not allowed for this agent.",
                details,
            )
        details["limit"] = policy.limit_value
        if policy.window is not None:
            details["window"] = policy.window
        if violation.current is not None:
            details["current"] = violation.current
        return OktoNexusError(
            ErrorCode.QUOTA_EXCEEDED,
            f"Governance quota exceeded (policy {policy.policy_id}): "
            f"{policy.limit_kind} limit of {policy.limit_value} for {action}.",
            details,
        )

    # ------------------------------------------------------------------ #
    # Audit event (separate UoW, best-effort - BR6)
    # ------------------------------------------------------------------ #
    def emit_denied(
        self,
        *,
        workspace_id: str,
        agent_id: Any,
        exc: OktoNexusError,
    ) -> None:
        """Emit ``governance.denied`` AFTER the main UoW rolled back.

        No-op unless ``exc`` is one of this slice's denial codes. Best-effort:
        every failure is swallowed so the caller's error is never replaced or
        masked (BR6). The payload carries the normative denial context and
        NEVER the action's subject/body.
        """
        if exc.code not in _DENIAL_CODES or self._emitter is None:
            return
        details = exc.details or {}
        payload: dict[str, Any] = {
            "policy_id": details.get("policy_id"),
            "action": details.get("action"),
            "agent_id": str(agent_id) if agent_id is not None else None,
            "error_code": exc.code,
            "limit_kind": details.get("limit_kind"),
        }
        for key in ("limit", "window", "current"):
            if key in details:
                payload[key] = details[key]
        try:
            with self._cf.unit_of_work() as uow:
                self._emitter.emit(
                    uow,
                    workspace_id=workspace_id,
                    stream=GOVERNANCE_STREAM,
                    type=EVENT_DENIED,
                    payload=payload,
                    actor_agent_id=payload["agent_id"],
                    visibility=DENIED_VISIBILITY,
                    target=None,
                )
        except Exception:  # noqa: BLE001 - best-effort: auditing never outranks the caller's error
            return

    # ------------------------------------------------------------------ #
    # Caller-scoped discovery (agent_whoami block - FR11)
    # ------------------------------------------------------------------ #
    def policies_for_agent(self, agent_id: str) -> list[dict[str, Any]]:
        """The caller's EFFECTIVE governance rules (from its bindings), compact.

        Backs the conditional ``governance`` block of ``agent_whoami`` (FR11):
        one compact dict per effective rule ({policy_id (the source label
        ``inline`` / ``<policy_id>@<version>``), action, limit_kind, limit?,
        window?}) in the deterministic source-then-rule order. Empty when the
        caller has no bindings (or none carry governance) - the tool then omits
        the block entirely, so the no-binding surface stays byte-identical to
        today's (BR2). Only the caller's OWN resolved rules are exposed and NEVER
        the audience selector contents (comm_scope stays operator-private, FR11).
        """
        with self._cf.unit_of_work(write=False) as uow:
            sources = self._effective_sources(uow, str(agent_id))
        out: list[dict[str, Any]] = []
        for source in sources:
            for rule in source.governance:
                if not isinstance(rule, dict):
                    continue
                item: dict[str, Any] = {
                    "policy_id": source.label,
                    "action": rule.get("action"),
                    "limit_kind": rule.get("limit_kind"),
                }
                if rule.get("limit_value") is not None:
                    item["limit"] = rule.get("limit_value")
                if rule.get("window") is not None:
                    item["window"] = rule.get("window")
                out.append(item)
        return out

    def effective_policy_labels_for(self, agent_id: str) -> list[str]:
        """The caller's EFFECTIVE policy labels, deterministic order (AC10/FR11).

        Backs the ``effective_policies`` field of ``agent_whoami``: names WHICH
        policies apply as ``<policy_id>@<version>`` (or ``inline`` for the inline
        source) - audience-only sources INCLUDED (unlike
        :meth:`policies_for_agent`, which lists only governance-bearing rules) -
        and NEVER the audience selector contents (comm_scope stays
        operator-private, FR11). Empty when the caller has no bindings, so the
        whoami field is then omitted (BR2 zero-regression).
        """
        with self._cf.unit_of_work(write=False) as uow:
            return effective_policy_labels(self._effective_sources(uow, str(agent_id)))

    # ------------------------------------------------------------------ #
    # Operator CRUD (REST; works with the flag OFF - BR4)
    # ------------------------------------------------------------------ #
    def create_policy(
        self,
        *,
        subject_kind: Any,
        subject_value: Any = None,
        action: Any,
        limit_kind: Any,
        limit_value: Any = None,
        window: Any = None,
        enabled: Any = True,
    ) -> dict[str, Any]:
        """Validate (form + existence) and persist one policy."""
        fields = validate_policy_form(
            subject_kind=subject_kind,
            subject_value=subject_value,
            action=action,
            limit_kind=limit_kind,
            limit_value=limit_value,
            window=window,
        )
        policy_id = new_id("pol")
        with self._cf.unit_of_work() as uow:
            self._ensure_subject_exists(
                uow, fields["subject_kind"], fields["subject_value"]
            )
            policy = self._governance.create(
                uow,
                policy_id=policy_id,
                subject_kind=fields["subject_kind"],
                subject_value=fields["subject_value"],
                action=fields["action"],
                limit_kind=fields["limit_kind"],
                limit_value=fields["limit_value"],
                window=fields["window"],
                enabled=bool(enabled),
            )
        return policy_to_dict(policy)

    def list_policies(self) -> list[dict[str, Any]]:
        """Every policy (enabled AND disabled), deterministic order."""
        with self._cf.unit_of_work(write=False) as uow:
            return [policy_to_dict(p) for p in self._governance.list(uow)]

    def update_policy(self, *, policy_id: Any, patch: dict[str, Any]) -> dict[str, Any]:
        """Patch a policy; the MERGED result must still be a valid form."""
        if not isinstance(policy_id, str) or not policy_id.strip():
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "policy_id is required.",
                {"policy_id": policy_id},
            )
        allowed = {
            "subject_kind",
            "subject_value",
            "action",
            "limit_kind",
            "limit_value",
            "window",
            "enabled",
        }
        unknown = sorted(set(patch) - allowed)
        if unknown:
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                f"Unknown policy field(s): {', '.join(unknown)}.",
                {"unknown": unknown, "supported": sorted(allowed)},
            )
        with self._cf.unit_of_work() as uow:
            existing = self._governance.get(uow, policy_id)
            if existing is None:
                raise OktoNexusError(
                    ErrorCode.NOT_FOUND,
                    f"Governance policy {policy_id!r} not found.",
                    {"policy_id": policy_id},
                )
            merged = {
                "subject_kind": patch.get("subject_kind", existing.subject_kind),
                "subject_value": patch.get("subject_value", existing.subject_value),
                "action": patch.get("action", existing.action),
                "limit_kind": patch.get("limit_kind", existing.limit_kind),
                "limit_value": patch.get("limit_value", existing.limit_value),
                "window": patch.get("window", existing.window),
            }
            fields = validate_policy_form(**merged)
            self._ensure_subject_exists(
                uow, fields["subject_kind"], fields["subject_value"]
            )
            if "enabled" in patch:
                fields["enabled"] = bool(patch["enabled"])
            updated = self._governance.update(uow, policy_id=policy_id, fields=fields)
        if updated is None:  # pragma: no cover - row deleted concurrently
            raise OktoNexusError(
                ErrorCode.NOT_FOUND,
                f"Governance policy {policy_id!r} not found.",
                {"policy_id": policy_id},
            )
        return policy_to_dict(updated)

    def delete_policy(self, *, policy_id: Any) -> dict[str, Any]:
        """Remove a policy; ``NOT_FOUND`` when it does not exist."""
        with self._cf.unit_of_work() as uow:
            deleted = self._governance.delete(uow, policy_id=str(policy_id))
        if not deleted:
            raise OktoNexusError(
                ErrorCode.NOT_FOUND,
                f"Governance policy {policy_id!r} not found.",
                {"policy_id": policy_id},
            )
        return {"policy_id": str(policy_id), "deleted": True}

    def _ensure_subject_exists(
        self, uow: UnitOfWork, subject_kind: str, subject_value: str | None
    ) -> None:
        """Existence checks that need IO (AC7): agent registered, capability
        in the catalogue. ``role`` is free-form (any non-empty string) and
        ``star`` has no value - both already covered by the form validation."""
        if subject_kind == SUBJECT_AGENT and self._agents is not None:
            if self._agents.get(uow, str(subject_value)) is None:
                raise OktoNexusError(
                    ErrorCode.VALIDATION_ERROR,
                    f"subject_value {subject_value!r} is not a registered agent.",
                    {"subject_kind": subject_kind, "subject_value": subject_value},
                )
        elif (
            subject_kind == SUBJECT_CAPABILITY and self._capability_catalog is not None
        ):
            if self._capability_catalog.get(uow, str(subject_value)) is None:
                raise OktoNexusError(
                    ErrorCode.VALIDATION_ERROR,
                    f"subject_value {subject_value!r} is not a registered "
                    "capability (see the capability catalog).",
                    {"subject_kind": subject_kind, "subject_value": subject_value},
                )

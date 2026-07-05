"""Operator use cases for the NAMED, versioned policy catalog (spec 80624c1a).

The application-layer owner of the ``/api/v1/policies`` surface (FR9): CRUD over
a policy's mutable HEADER (``name`` + ``description``) plus the append-only,
immutable VERSION stream (audience + governance). It is deliberately a STAGING
surface - creating, editing and publishing a policy attaches it to no one and
enforces nothing (BR4). Enforcement only begins once an agent BINDS the policy
(the B2 surface); this service never composes or evaluates policies.

Two invariants it owns:

* **Append-only versions (BR11/BR4).** Publishing an edit APPENDS the next
  ``(policy_id, version)`` via :meth:`PolicyRepo.add_version` (``MAX+1`` under
  the write lock); a version is never mutated or deleted.
* **Delete guard (BR5).** A policy still referenced by ANY agent binding
  (``latest`` or ``pinned``) cannot be deleted - :meth:`delete` raises
  ``POLICY_IN_USE`` listing the binder ids, so no pin is ever orphaned.

Like :class:`okto_nexus.application.governance.GovernanceService`'s operator
CRUD, every method opens its OWN unit of work (``self._cf``) so the HTTP handler
calls it straight through a worker thread (never nested inside ``_run``). Form
validation is the domain's job (:mod:`okto_nexus.domain.policy`); existence and
uniqueness (which need IO) are enforced here. Never imports ``sqlite3``/``mcp``
(import-boundary test).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..domain.base import new_id
from ..domain.policy import (
    validate_agent_bindings,
    validate_policy_header_form,
    validate_policy_version_form,
)
from ..errors import ErrorCode, OktoNexusError
from .ports import (
    AgentPolicyBindingRepo,
    AgentRepo,
    ConnectionFactory,
    PolicyRepo,
)


def _header(record: Any) -> dict[str, Any]:
    """The catalog header projection (metadata + the ``latest_version`` hint)."""
    return {
        "policy_id": record.policy_id,
        "name": record.name,
        "description": record.description,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
        "latest_version": record.latest_version,
    }


def _version(version: Any) -> dict[str, Any]:
    """The published-version projection (the immutable body + its stamp)."""
    return {
        "policy_id": version.policy_id,
        "version": version.version,
        "audience": version.audience,
        "governance": [dict(rule) for rule in version.governance],
        "published_at": version.published_at,
    }


class PolicyCatalogService:
    """Operator CRUD + version publishing for named global policies.

    Stateless over injected ports; each method runs in its own unit of work so
    the catalog mutation and its reads commit atomically. Works with no
    enforcement wired at all - it is pure staging.
    """

    def __init__(
        self,
        *,
        connection_factory: ConnectionFactory,
        policies: PolicyRepo,
        policy_bindings: AgentPolicyBindingRepo,
        agents: AgentRepo | None = None,
    ) -> None:
        self._cf = connection_factory
        self._policies = policies
        self._bindings = policy_bindings
        self._agents = agents

    # ------------------------------------------------------------------ #
    # Header CRUD
    # ------------------------------------------------------------------ #
    def create(self, *, name: Any, description: Any = None) -> dict[str, Any]:
        """Create a policy header (no version yet). Duplicate ``name`` -> 422."""
        fields = validate_policy_header_form(name=name, description=description)
        with self._cf.unit_of_work() as uow:
            self._reject_duplicate_name(uow, name=fields["name"], excluding=None)
            record = self._policies.create(
                uow,
                policy_id=new_id("pol"),
                name=fields["name"],
                description=fields["description"],
            )
        return {**_header(record), "versions": []}

    def list(self) -> list[dict[str, Any]]:
        """Every policy header, deterministic ``(created_at, policy_id)`` order."""
        with self._cf.unit_of_work(write=False) as uow:
            return [_header(record) for record in self._policies.list(uow)]

    def get(self, *, policy_id: Any) -> dict[str, Any]:
        """One policy header PLUS its full version history. ``NOT_FOUND`` if absent."""
        pid = str(policy_id)
        with self._cf.unit_of_work(write=False) as uow:
            record = self._require(uow, policy_id=pid)
            versions = self._policies.list_versions(uow, policy_id=pid)
        return {**_header(record), "versions": [_version(v) for v in versions]}

    def update(self, *, policy_id: Any, patch: dict[str, Any]) -> dict[str, Any]:
        """Patch the header (name/description). The MERGED result must be valid."""
        pid = str(policy_id)
        with self._cf.unit_of_work() as uow:
            existing = self._require(uow, policy_id=pid)
            fields = validate_policy_header_form(
                name=patch["name"] if "name" in patch else existing.name,
                description=(
                    patch["description"]
                    if "description" in patch
                    else existing.description
                ),
            )
            self._reject_duplicate_name(uow, name=fields["name"], excluding=pid)
            self._policies.update(
                uow,
                policy_id=pid,
                name=fields["name"],
                description=fields["description"],
            )
            record = self._require(uow, policy_id=pid)
            versions = self._policies.list_versions(uow, policy_id=pid)
        return {**_header(record), "versions": [_version(v) for v in versions]}

    def delete(self, *, policy_id: Any) -> dict[str, Any]:
        """Delete a policy. ``POLICY_IN_USE`` (409) while any agent binds it."""
        pid = str(policy_id)
        with self._cf.unit_of_work() as uow:
            self._require(uow, policy_id=pid)
            agents = self._bindings.agents_binding_policy(uow, policy_id=pid)
            if agents:
                raise OktoNexusError(
                    ErrorCode.POLICY_IN_USE,
                    f"Policy {pid!r} is bound by {len(agents)} agent(s) and "
                    "cannot be deleted. Detach it from the listed agents first "
                    "(deleting it would orphan their bindings).",
                    {"policy_id": pid, "agents": agents},
                )
            self._policies.delete(uow, policy_id=pid)
        return {"deleted": True, "policy_id": pid}

    # ------------------------------------------------------------------ #
    # Append-only versions
    # ------------------------------------------------------------------ #
    def publish_version(
        self, *, policy_id: Any, audience: Any = None, governance: Any = None
    ) -> dict[str, Any]:
        """Publish the next immutable version (``version = MAX+1``). ``NOT_FOUND``
        when the policy does not exist; ``VALIDATION_ERROR`` on a malformed body."""
        pid = str(policy_id)
        body = validate_policy_version_form(audience=audience, governance=governance)
        with self._cf.unit_of_work() as uow:
            self._require(uow, policy_id=pid)
            version = self._policies.add_version(
                uow,
                policy_id=pid,
                audience=body["audience"],
                governance=body["governance"],
            )
        return _version(version)

    def list_versions(self, *, policy_id: Any) -> list[dict[str, Any]]:
        """Every published version of a policy, ascending. ``NOT_FOUND`` if absent."""
        pid = str(policy_id)
        with self._cf.unit_of_work(write=False) as uow:
            self._require(uow, policy_id=pid)
            versions = self._policies.list_versions(uow, policy_id=pid)
        return [_version(v) for v in versions]

    # ------------------------------------------------------------------ #
    # Agent bindings (attach/detach) - FR10, contract api_101afea2
    # ------------------------------------------------------------------ #
    def set_agent_bindings(
        self, *, agent_id: Any, globals_: Any = None, inline: Any = None
    ) -> dict[str, Any]:
        """Replace an agent's FULL binding set (N globals + at most 1 inline).

        Fail-closed (FR10/BR5). FORM is the domain's job
        (:func:`validate_agent_bindings` - source/mode/pinned-int + inline
        grammar + the at-most-one-inline rule); EXISTENCE is checked here (it
        needs IO): an unknown ``agent_id`` or referenced ``policy_id`` ->
        ``NOT_FOUND``; a ``pinned_version`` never published -> ``VALIDATION_ERROR``
        (an orphan pin is forbidden, BR5). Persisted as ONE full overwrite;
        returns the resolved ``effective_policies`` labels
        (``<policy_id>@<version>`` per global in submission order, then
        ``inline@-`` when an inline is attached).
        """
        aid = str(agent_id)
        composed: list[dict[str, Any]] = []
        if globals_ is not None:
            if not isinstance(globals_, list):
                raise OktoNexusError(
                    ErrorCode.VALIDATION_ERROR,
                    "globals must be a list of global binding objects.",
                    {"globals": globals_, "type": type(globals_).__name__},
                )
            for entry in globals_:
                if not isinstance(entry, Mapping):
                    raise OktoNexusError(
                        ErrorCode.VALIDATION_ERROR,
                        "each global binding must be a JSON object.",
                        {"binding": entry, "type": type(entry).__name__},
                    )
                composed.append({**entry, "source": "global"})
        if inline is not None:
            if not isinstance(inline, Mapping):
                raise OktoNexusError(
                    ErrorCode.VALIDATION_ERROR,
                    "inline must be a JSON object with audience/governance.",
                    {"inline": inline, "type": type(inline).__name__},
                )
            composed.append({**inline, "source": "inline"})
        # Domain FORM validation runs FIRST (fail-closed, no IO): mode/pinned-int
        # + inline grammar + at-most-one-inline. Existence follows inside the UoW.
        validated = validate_agent_bindings(composed)
        with self._cf.unit_of_work() as uow:
            if self._agents is not None and self._agents.get(uow, aid) is None:
                raise OktoNexusError(
                    ErrorCode.NOT_FOUND,
                    f"Agent {aid!r} is not registered.",
                    {"agent_id": aid},
                )
            self._check_global_existence(uow, validated)
            self._bindings.replace(uow, agent_id=aid, bindings=validated)
            labels = self._effective_labels(uow, validated)
        return {"agent_id": aid, "effective_policies": labels}

    def get_agent_bindings(self, *, agent_id: Any) -> dict[str, Any]:
        """Read an agent's CURRENT binding set, reshaped for the editor (C2).

        The inverse of :meth:`set_agent_bindings`: reads the stored, ordered
        bindings and splits them back into the ``{globals, inline}`` contract
        shape the ``PUT`` accepts, so the operator dashboard can pre-populate its
        attach editor and round-trip the result straight back. ``globals`` is the
        ordered list of ``{policy_id, mode, pinned_version?}`` references
        (``pinned_version`` present only for ``pinned``); ``inline`` is the single
        ``{audience, governance}`` embedded policy or ``None``. An unknown
        ``agent_id`` -> ``NOT_FOUND``; an agent with no bindings ->
        ``{globals: [], inline: None}`` (unrestricted, ungoverned).
        """
        aid = str(agent_id)
        with self._cf.unit_of_work(write=False) as uow:
            if self._agents is not None and self._agents.get(uow, aid) is None:
                raise OktoNexusError(
                    ErrorCode.NOT_FOUND,
                    f"Agent {aid!r} is not registered.",
                    {"agent_id": aid},
                )
            stored = self._bindings.list_for_agent(uow, agent_id=aid)
        globals_: list[dict[str, Any]] = []
        inline: dict[str, Any] | None = None
        for binding in stored:
            if binding.get("source") == "global":
                ref: dict[str, Any] = {
                    "policy_id": binding.get("policy_id"),
                    "mode": binding.get("mode"),
                }
                if binding.get("mode") == "pinned":
                    ref["pinned_version"] = binding.get("pinned_version")
                globals_.append(ref)
            elif binding.get("source") == "inline" and inline is None:
                inline = {
                    "audience": binding.get("audience"),
                    "governance": list(binding.get("governance") or []),
                }
        return {"agent_id": aid, "globals": globals_, "inline": inline}

    def _check_global_existence(self, uow: Any, bindings: list[dict[str, Any]]) -> None:
        """Every referenced policy must exist; a pin must resolve (no orphans)."""
        for binding in bindings:
            if binding.get("source") != "global":
                continue
            policy_id = binding["policy_id"]
            if self._policies.get(uow, policy_id) is None:
                raise OktoNexusError(
                    ErrorCode.NOT_FOUND,
                    f"Policy {policy_id!r} referenced by the binding is not "
                    "registered.",
                    {"policy_id": policy_id},
                )
            if binding.get("mode") == "pinned":
                version = binding["pinned_version"]
                if (
                    self._policies.get_version(
                        uow, policy_id=policy_id, version=version
                    )
                    is None
                ):
                    raise OktoNexusError(
                        ErrorCode.VALIDATION_ERROR,
                        f"pinned_version {version} of policy {policy_id!r} does "
                        "not exist.",
                        {"policy_id": policy_id, "pinned_version": version},
                    )

    def _effective_labels(self, uow: Any, bindings: list[dict[str, Any]]) -> list[str]:
        """Resolved labels for the response: globals (``@version``) then inline.

        A ``latest`` global with no published version yet resolves to ``@-`` (it
        is bound but currently contributes nothing) - honest, and distinct from a
        concrete version number.
        """
        labels: list[str] = []
        for binding in bindings:
            if binding.get("source") != "global":
                continue
            policy_id = binding["policy_id"]
            if binding.get("mode") == "pinned":
                version: Any = binding["pinned_version"]
            else:
                latest = self._policies.latest_version(uow, policy_id=policy_id)
                version = latest.version if latest is not None else "-"
            labels.append(f"{policy_id}@{version}")
        if any(b.get("source") == "inline" for b in bindings):
            labels.append("inline@-")
        return labels

    # ------------------------------------------------------------------ #
    # Internal guards
    # ------------------------------------------------------------------ #
    def _require(self, uow: Any, *, policy_id: str) -> Any:
        record = self._policies.get(uow, policy_id)
        if record is None:
            raise OktoNexusError(
                ErrorCode.NOT_FOUND,
                f"Policy {policy_id!r} not found.",
                {"policy_id": policy_id},
            )
        return record

    def _reject_duplicate_name(
        self, uow: Any, *, name: str, excluding: str | None
    ) -> None:
        clash = self._policies.get_by_name(uow, name)
        if clash is not None and clash.policy_id != excluding:
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                f"a policy named {name!r} already exists.",
                {"name": name, "policy_id": clash.policy_id},
            )

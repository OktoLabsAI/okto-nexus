"""Central capability catalog use cases (migration 014).

The application-layer owner of capability EXISTENCE (FORM lives in
:func:`okto_nexus.domain.routing.normalize_capabilities`, which is untouched):

* :meth:`CapabilityCatalogService.ensure_registered` - the single fail-closed
  existence gate every write path runs BEFORE persisting a reference to a
  capability (agent ``capabilities`` via register/POST/PATCH and
  ``strategy: "capability"`` targets, including sub-rules inside ``mixed``).
  An unregistered name is a ``VALIDATION_ERROR`` listing every missing name;
  nothing unregistered ever persists.
* Registry CRUD for the operator surface, including the in-use deletion
  guard: deleting a name still OWNED by any agent (active or inactive)
  raises ``CAPABILITY_IN_USE`` with the exact owner list. Historic targets do
  not count as use (they are ephemeral; new sends are blocked by the gate).
* :func:`seed_capability_catalog` - the idempotent transition seed: every
  capability already announced by ANY persisted agent is absorbed
  (insert-or-ignore), so the invariant "owned => registered" holds before the
  first gate ever runs and no existing agent breaks.

Application layer: depends only on ports, domain helpers and the error
catalogue; never imports ``sqlite3``/``mcp`` (import-boundary test).
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

from ..domain.routing import normalize_capabilities
from ..errors import ErrorCode, OktoNexusError
from .ports import AgentRepo, CapabilityCatalogRepo, UnitOfWork

#: ``kind`` discriminator in a CAPABILITY_IN_USE ``uses`` entry: ownership via
#: the agent's announced ``capabilities`` (the only kind - targets are
#: ephemeral and never count).
USE_KIND_CAPABILITIES = "capabilities"


def _require_token(name: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            f"{name} is required and must be a non-empty string.",
            {name: value},
        )
    return value.strip()


class CapabilityCatalogService:
    """Use-case orchestration for the central capability catalog.

    Stateless over injected ports; every method runs inside the CALLER's unit
    of work so registry mutations commit atomically and the existence gate
    shares the writer's snapshot.
    """

    def __init__(
        self,
        *,
        catalog: CapabilityCatalogRepo,
        agents: Optional[AgentRepo] = None,
    ) -> None:
        self._catalog = catalog
        self._agents = agents

    # ------------------------------------------------------------------ #
    # Read model
    # ------------------------------------------------------------------ #
    def snapshot(self, uow: UnitOfWork) -> list[dict[str, Any]]:
        """The full catalog, sorted by name."""
        return [
            {
                "name": row.name,
                "description": row.description,
                "created_at": row.created_at,
            }
            for row in self._catalog.list(uow)
        ]

    # ------------------------------------------------------------------ #
    # Registry writes (operator surface)
    # ------------------------------------------------------------------ #
    def register(
        self, uow: UnitOfWork, *, name: Any, description: str | None = None
    ) -> dict[str, Any]:
        """Register a capability. ``VALIDATION_ERROR`` on blank or duplicate."""
        token = _require_token("name", name)
        row = self._catalog.create(uow, name=token, description=description)
        return {
            "name": row.name,
            "description": row.description,
            "created_at": row.created_at,
        }

    def delete(self, uow: UnitOfWork, *, name: Any) -> dict[str, Any]:
        """Delete a capability. ``CAPABILITY_IN_USE`` while owned by an agent."""
        token = _require_token("name", name)
        if self._catalog.get(uow, token) is None:
            raise OktoNexusError(
                ErrorCode.NOT_FOUND,
                f"Capability '{token}' is not registered.",
                {"name": token},
            )
        self._guard_not_in_use(uow, name=token)
        self._catalog.delete(uow, name=token)
        return {"name": token, "deleted": True}

    # ------------------------------------------------------------------ #
    # The fail-closed existence gate (every write path runs this)
    # ------------------------------------------------------------------ #
    def ensure_registered(
        self, uow: UnitOfWork, names: Iterable[str], *, field: str
    ) -> None:
        """Require every capability name in ``names`` to be registered.

        ``names`` are ALREADY-NORMALISED tokens (``normalize_capabilities`` or
        the domain target iterator ran first - form is the domain's job).
        Raises ``VALIDATION_ERROR`` listing every unregistered name at once -
        the caller aborts before persisting anything (fail-closed:
        capabilities are never created implicitly by use).
        """
        unregistered = sorted(
            name
            for name in dict.fromkeys(names)
            if self._catalog.get(uow, name) is None
        )
        if unregistered:
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                f"{field} references unregistered capability(ies): "
                f"{', '.join(unregistered)}. Capabilities are fail-closed: "
                "register the name in the capability catalog (dashboard "
                "Registry or POST /api/v1/capabilities) before use.",
                {"field": field, "unregistered": unregistered},
            )

    # ------------------------------------------------------------------ #
    # Usage scan (CAPABILITY_IN_USE)
    # ------------------------------------------------------------------ #
    def collect_uses(self, uow: UnitOfWork, *, name: str) -> list[dict[str, str]]:
        """Every agent OWNING ``name`` (active and inactive), one entry each.

        Ownership only: an inactive agent counts (it can reactivate and its
        announcement must stay valid). Historic message/handoff targets never
        count - they are ephemeral and already resolved. Sorted by agent_id.
        """
        if self._agents is None:
            return []
        uses = [
            {"agent_id": agent.agent_id, "kind": USE_KIND_CAPABILITIES}
            for agent in self._agents.list(uow)
            if name in normalize_capabilities(agent.capabilities)
        ]
        uses.sort(key=lambda u: u["agent_id"])
        return uses

    def _guard_not_in_use(self, uow: UnitOfWork, *, name: str) -> None:
        uses = self.collect_uses(uow, name=name)
        if not uses:
            return
        raise OktoNexusError(
            ErrorCode.CAPABILITY_IN_USE,
            f"Capability '{name}' is owned by {len(uses)} agent(s) and cannot "
            "be deleted. Remove it from the listed agents' capabilities first "
            "(deleting it would silently break their announcements).",
            {
                "capability": name,
                "total_uses": len(uses),
                "uses": uses,
            },
        )


def seed_capability_catalog(
    uow: UnitOfWork, *, catalog: CapabilityCatalogRepo, agents: AgentRepo
) -> int:
    """Absorb every announced capability into the catalog (insert-or-ignore).

    The transition seed (runs at every bootstrap, idempotently): each name
    ``normalize_capabilities`` yields for ANY persisted agent - active or
    inactive - is registered if absent, establishing the invariant
    "owned => registered" before the first fail-closed gate runs. Returns how
    many names were inserted by THIS pass (0 when already current).
    """
    inserted = 0
    for agent in agents.list(uow):
        for name in sorted(normalize_capabilities(agent.capabilities)):
            if catalog.ensure(uow, name=name):
                inserted += 1
    return inserted

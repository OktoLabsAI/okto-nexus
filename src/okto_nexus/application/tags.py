"""Central tag catalog use cases (migration 013, phase F1).

The application-layer owner of tag EXISTENCE (FORM lives in
:mod:`okto_nexus.domain.tag_selector`):

* :meth:`TagCatalogService.ensure_registered` - the single fail-closed
  existence gate every write path runs BEFORE persisting a reference to a
  tag pair (agent ``tags``, ``comm_scope`` selectors, ``strategy: "tag"``
  targets). An unregistered key or value is a ``VALIDATION_ERROR`` naming
  the offending pairs; nothing unregistered ever persists.
* Registry CRUD (keys/values) for the operator surface, including the
  in-use deletion guard: deleting a key/value still referenced by any agent
  raises ``TAG_IN_USE`` with the exact usage list (never a cascade - a
  cascade would silently empty selectors into default-allow).

Application layer: depends only on ports, domain helpers and the error
catalogue; never imports ``sqlite3``/``mcp`` (import-boundary test).
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

from ..domain.tag_selector import iter_selector_keys, iter_selector_pairs
from ..errors import ErrorCode, OktoNexusError
from .ports import AgentRepo, TagCatalogRepo, UnitOfWork

#: ``kind`` discriminators in a TAG_IN_USE ``uses`` entry (AC3 shape).
USE_KIND_AGENT_TAGS = "agent_tags"
USE_KIND_COMM_SCOPE = "comm_scope"


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _require_token(name: str, value: Any) -> str:
    if _is_blank(value) or not isinstance(value, str):
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            f"{name} is required and must be a non-empty string.",
            {name: value},
        )
    return value.strip()


def _selector_references(selector: Any, *, key: str, value: str | None) -> bool:
    """Whether a tags map or selector (either form) references ``key`` (or
    ``key=value``).

    A KEY is referenced by flat entries and by every rich expression naming
    it - including Exists/DoesNotExist, which carry no values. A PAIR is
    referenced by flat entries and by In/NotIn values only (F3, TR5).
    """
    if value is None:
        return any(k == key for k in iter_selector_keys(selector))
    return any(k == key and v == value for k, v in iter_selector_pairs(selector))


class TagCatalogService:
    """Use-case orchestration for the central tag catalog.

    Stateless over injected ports; every method runs inside the CALLER's unit
    of work so registry mutations commit atomically with their audit trail
    and the existence gate shares the writer's snapshot.
    """

    def __init__(
        self, *, catalog: TagCatalogRepo, agents: Optional[AgentRepo] = None
    ) -> None:
        self._catalog = catalog
        self._agents = agents

    # ------------------------------------------------------------------ #
    # Read model
    # ------------------------------------------------------------------ #
    def snapshot(self, uow: UnitOfWork) -> list[dict[str, Any]]:
        """The full catalog: every key with its registered values (sorted)."""
        values_by_key: dict[str, list[dict[str, Any]]] = {}
        for tv in self._catalog.list_values(uow):
            values_by_key.setdefault(tv.key, []).append(
                {
                    "value": tv.value,
                    "description": tv.description,
                    "created_at": tv.created_at,
                }
            )
        return [
            {
                "key": tk.key,
                "description": tk.description,
                "created_at": tk.created_at,
                "values": values_by_key.get(tk.key, []),
            }
            for tk in self._catalog.list_keys(uow)
        ]

    # ------------------------------------------------------------------ #
    # Registry writes (operator surface)
    # ------------------------------------------------------------------ #
    def register_key(
        self, uow: UnitOfWork, *, key: Any, description: str | None = None
    ) -> dict[str, Any]:
        """Register a tag key. ``VALIDATION_ERROR`` on blank or duplicate."""
        token = _require_token("key", key)
        row = self._catalog.create_key(uow, key=token, description=description)
        return {
            "key": row.key,
            "description": row.description,
            "created_at": row.created_at,
        }

    def register_value(
        self,
        uow: UnitOfWork,
        *,
        key: Any,
        value: Any,
        description: str | None = None,
    ) -> dict[str, Any]:
        """Register a value under a registered key (fail-closed on the key)."""
        key_token = _require_token("key", key)
        value_token = _require_token("value", value)
        row = self._catalog.create_value(
            uow, key=key_token, value=value_token, description=description
        )
        return {
            "key": row.key,
            "value": row.value,
            "description": row.description,
            "created_at": row.created_at,
        }

    def delete_key(self, uow: UnitOfWork, *, key: Any) -> dict[str, Any]:
        """Delete a key and its values. ``TAG_IN_USE`` while referenced."""
        token = _require_token("key", key)
        if self._catalog.get_key(uow, token) is None:
            raise OktoNexusError(
                ErrorCode.NOT_FOUND,
                f"Tag key '{token}' is not registered.",
                {"key": token},
            )
        self._guard_not_in_use(uow, key=token, value=None)
        self._catalog.delete_key(uow, key=token)
        return {"key": token, "deleted": True}

    def delete_value(self, uow: UnitOfWork, *, key: Any, value: Any) -> dict[str, Any]:
        """Delete one value. ``TAG_IN_USE`` while referenced."""
        key_token = _require_token("key", key)
        value_token = _require_token("value", value)
        if self._catalog.get_value(uow, key=key_token, value=value_token) is None:
            raise OktoNexusError(
                ErrorCode.NOT_FOUND,
                f"Tag value '{key_token}={value_token}' is not registered.",
                {"key": key_token, "value": value_token},
            )
        self._guard_not_in_use(uow, key=key_token, value=value_token)
        self._catalog.delete_value(uow, key=key_token, value=value_token)
        return {"key": key_token, "value": value_token, "deleted": True}

    # ------------------------------------------------------------------ #
    # The fail-closed existence gate (every write path runs this)
    # ------------------------------------------------------------------ #
    def ensure_registered(self, uow: UnitOfWork, mapping: Any, *, field: str) -> None:
        """Require every tag reference of ``mapping`` to be registered.

        ``mapping`` is a VALIDATED tags map or selector in EITHER form (or
        ``None`` = nothing to check). Flat entries and In/NotIn expressions
        check key AND values; Exists/DoesNotExist expressions carry no values
        and check only the key (F3). Raises ``VALIDATION_ERROR`` listing
        every unregistered reference - the caller aborts before persisting
        anything (fail-closed: tags are never created implicitly by use).
        """
        if mapping is None:
            return
        unknown: list[dict[str, Any]] = []
        seen_keys: dict[str, bool] = {}
        pairs = list(dict.fromkeys(iter_selector_pairs(mapping)))
        for key, value in pairs:
            if key not in seen_keys:
                seen_keys[key] = self._catalog.get_key(uow, key) is not None
            if not seen_keys[key]:
                unknown.append({"key": key, "value": value, "missing": "key"})
                continue
            if self._catalog.get_value(uow, key=key, value=value) is None:
                unknown.append({"key": key, "value": value, "missing": "value"})
        keys_with_pairs = {key for key, _ in pairs}
        for key in dict.fromkeys(iter_selector_keys(mapping)):
            # Presence-only keys (Exists/DoesNotExist): no pair walked them.
            if key in keys_with_pairs:
                continue
            if key not in seen_keys:
                seen_keys[key] = self._catalog.get_key(uow, key) is not None
            if not seen_keys[key]:
                unknown.append({"key": key, "value": None, "missing": "key"})
        if unknown:
            labels = ", ".join(
                u["key"] if u["value"] is None else f"{u['key']}={u['value']}"
                for u in unknown
            )
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                f"{field} references unregistered tag(s): {labels}. Tags are "
                "fail-closed: register the key and value in the tag catalog "
                "(dashboard Tag Registry or POST /api/v1/tags) before use.",
                {"field": field, "unregistered": unknown},
            )

    # ------------------------------------------------------------------ #
    # Usage scan (TAG_IN_USE)
    # ------------------------------------------------------------------ #
    def collect_uses(
        self, uow: UnitOfWork, *, key: str, value: str | None = None
    ) -> list[dict[str, str]]:
        """Every agent reference to ``key`` (or ``key=value``), AC3 shape.

        One entry per ``(agent, kind)``: ``kind`` is ``agent_tags`` when the
        agent's tag map references the pair, ``comm_scope`` when either of its
        outbound/inbound selectors does (once, even if both legs reference
        it). Selectors count in EITHER form: rich expressions reference their
        key (any operator) and their In/NotIn values (F3, TR5). Sorted by
        ``(agent_id, kind)`` for determinism.
        """
        if self._agents is None:
            return []
        uses: list[dict[str, str]] = []
        for agent in self._agents.list(uow):
            if _selector_references(agent.tags, key=key, value=value):
                uses.append({"agent_id": agent.agent_id, "kind": USE_KIND_AGENT_TAGS})
            scope = agent.comm_scope
            if isinstance(scope, Mapping) and any(
                _selector_references(scope.get(direction), key=key, value=value)
                for direction in ("outbound", "inbound")
            ):
                uses.append({"agent_id": agent.agent_id, "kind": USE_KIND_COMM_SCOPE})
        uses.sort(key=lambda u: (u["agent_id"], u["kind"]))
        return uses

    def _guard_not_in_use(
        self, uow: UnitOfWork, *, key: str, value: str | None
    ) -> None:
        uses = self.collect_uses(uow, key=key, value=value)
        if not uses:
            return
        label = key if value is None else f"{key}={value}"
        raise OktoNexusError(
            ErrorCode.TAG_IN_USE,
            f"Tag '{label}' is in use by {len(uses)} reference(s) and cannot "
            "be deleted. Remove it from the listed agents' tags/comm_scope "
            "first (a cascade would silently widen their communication "
            "scope).",
            {
                "key": key,
                "value": value,
                "total_uses": len(uses),
                "uses": uses,
            },
        )

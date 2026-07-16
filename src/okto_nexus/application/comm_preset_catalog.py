"""Operator use cases for the NAMED, versioned communication-preset catalog
(spec 6f961722).

The application-layer owner of the ``/api/v1/comm-presets`` surface: CRUD over a
preset's mutable HEADER (``name`` + ``description``) plus the append-only,
immutable VERSION stream (style ``content``), and the SINGLE-SOURCE per-agent
binding. It is the content-only, single-binding sibling of
:class:`okto_nexus.application.policy_catalog.PolicyCatalogService`.

Two invariants it owns:

* **Append-only versions.** Publishing an edit APPENDS the next
  ``(preset_id, version)`` via :meth:`CommPresetRepo.add_version` (``MAX+1``
  under the write lock); a version is never mutated or deleted.
* **Delete guard.** A preset still referenced by ANY agent binding (``latest``
  or ``pinned``) cannot be deleted - :meth:`delete` raises
  ``COMM_PRESET_IN_USE`` listing the binder ids, so no pin is ever orphaned.

Unlike policies, a communication binding is SINGLE-SOURCE (inline XOR one global
reference, D-CP-2): :meth:`set_agent_binding` composes exactly one side via
:func:`okto_nexus.domain.comm_preset.compose_comm_binding` and stores at most
one row. :meth:`resolve_communication` produces the SELF-ONLY ``whoami`` block
(BR11) and is the read the identity slice calls.

Like the policy catalog, every method opens its OWN unit of work (``self._cf``)
so the HTTP handler / whoami wrapper calls it straight through. Form validation
is the domain's job; existence and uniqueness (which need IO) are enforced here.
Never imports ``sqlite3``/``mcp`` (import-boundary test).
"""

from __future__ import annotations

from typing import Any

from ..domain.base import new_id
from ..domain.comm_preset import (
    compose_comm_binding,
    resolve_communication,
    validate_content_form,
    validate_preset_header_form,
    validate_preset_version_form,
)
from ..errors import ErrorCode, OktoNexusError
from .ports import (
    AgentCommBindingRepo,
    AgentRepo,
    CommPresetRepo,
    ConnectionFactory,
    UnitOfWork,
)

#: The built-in presets seeded at bootstrap (create-if-missing, idempotent). A
#: starter vocabulary so an operator has reusable styles out of the box; each is
#: a NAMED global preset with a single published v1. Values are English (the UI
#: convention) and stay within the closed content dimensions. Editing a built-in
#: publishes a new version like any other; the seed never overwrites an existing
#: name (so an operator's edits/renames survive a restart).
BUILTIN_COMM_PRESETS: tuple[tuple[str, str, dict[str, str]], ...] = (
    (
        "Concise",
        "Short, direct replies that lead with the answer.",
        {
            "tone": "concise",
            "verbosity": "low",
            "format": "short paragraphs",
            "additional_instructions": (
                "Lead with the answer. Omit preamble and do not restate the question."
            ),
        },
    ),
    (
        "Formal",
        "Professional register, complete sentences, no slang.",
        {
            "tone": "formal",
            "language": "en",
            "verbosity": "medium",
            "additional_instructions": (
                "Use complete sentences and a professional register. Avoid slang "
                "and emoji."
            ),
        },
    ),
    (
        "Code-first",
        "Runnable code before prose; explanations after.",
        {
            "format": "markdown",
            "structure": "code block first, prose after",
            "verbosity": "low",
            "additional_instructions": (
                "Prefer runnable code over description. Put the code block before "
                "the explanation."
            ),
        },
    ),
    (
        "Verbose",
        "Thorough, step-by-step answers with reasoning and context.",
        {
            "tone": "explanatory",
            "verbosity": "high",
            "structure": "step-by-step",
            "additional_instructions": (
                "Explain the reasoning and trade-offs. Include the context a "
                "newcomer would need."
            ),
        },
    ),
)


def _header(record: Any) -> dict[str, Any]:
    """The catalog header projection (metadata + the ``latest_version`` hint)."""
    return {
        "preset_id": record.preset_id,
        "name": record.name,
        "description": record.description,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
        "latest_version": record.latest_version,
    }


def _version(version: Any) -> dict[str, Any]:
    """The published-version projection (the immutable body + its stamp)."""
    return {
        "preset_id": version.preset_id,
        "version": version.version,
        "content": dict(version.content),
        "published_at": version.published_at,
    }


class CommPresetCatalogService:
    """Operator CRUD + version publishing + single-source binding for presets.

    Stateless over injected ports; each method runs in its own unit of work so
    the catalog mutation and its reads commit atomically. Works with no binding
    wired at all - it is pure staging until an agent binds a preset.
    """

    def __init__(
        self,
        *,
        connection_factory: ConnectionFactory,
        presets: CommPresetRepo,
        comm_bindings: AgentCommBindingRepo,
        agents: AgentRepo | None = None,
    ) -> None:
        self._cf = connection_factory
        self._presets = presets
        self._bindings = comm_bindings
        self._agents = agents

    # ------------------------------------------------------------------ #
    # Header CRUD
    # ------------------------------------------------------------------ #
    def create(self, *, name: Any, description: Any = None) -> dict[str, Any]:
        """Create a preset header (no version yet). Duplicate ``name`` -> 422."""
        fields = validate_preset_header_form(name=name, description=description)
        with self._cf.unit_of_work() as uow:
            self._reject_duplicate_name(uow, name=fields["name"], excluding=None)
            record = self._presets.create(
                uow,
                preset_id=new_id("cpr"),
                name=fields["name"],
                description=fields["description"],
            )
        return {**_header(record), "versions": []}

    def list(self) -> list[dict[str, Any]]:
        """Every preset header, deterministic ``(created_at, preset_id)`` order."""
        with self._cf.unit_of_work(write=False) as uow:
            return [_header(record) for record in self._presets.list(uow)]

    def get(self, *, preset_id: Any) -> dict[str, Any]:
        """One preset header PLUS its full version history. ``NOT_FOUND`` if absent."""
        pid = str(preset_id)
        with self._cf.unit_of_work(write=False) as uow:
            record = self._require(uow, preset_id=pid)
            versions = self._presets.list_versions(uow, preset_id=pid)
        return {**_header(record), "versions": [_version(v) for v in versions]}

    def update(self, *, preset_id: Any, patch: dict[str, Any]) -> dict[str, Any]:
        """Patch the header (name/description). The MERGED result must be valid."""
        pid = str(preset_id)
        with self._cf.unit_of_work() as uow:
            existing = self._require(uow, preset_id=pid)
            fields = validate_preset_header_form(
                name=patch["name"] if "name" in patch else existing.name,
                description=(
                    patch["description"]
                    if "description" in patch
                    else existing.description
                ),
            )
            self._reject_duplicate_name(uow, name=fields["name"], excluding=pid)
            self._presets.update(
                uow,
                preset_id=pid,
                name=fields["name"],
                description=fields["description"],
            )
            record = self._require(uow, preset_id=pid)
            versions = self._presets.list_versions(uow, preset_id=pid)
        return {**_header(record), "versions": [_version(v) for v in versions]}

    def delete(self, *, preset_id: Any) -> dict[str, Any]:
        """Delete a preset. ``COMM_PRESET_IN_USE`` (409) while any agent binds it."""
        pid = str(preset_id)
        with self._cf.unit_of_work() as uow:
            self._require(uow, preset_id=pid)
            agents = self._bindings.agents_binding_preset(uow, preset_id=pid)
            if agents:
                raise OktoNexusError(
                    ErrorCode.COMM_PRESET_IN_USE,
                    f"Communication preset {pid!r} is bound by {len(agents)} "
                    "agent(s) and cannot be deleted. Detach it from the listed "
                    "agents first (deleting it would orphan their bindings).",
                    {"preset_id": pid, "agents": agents},
                )
            self._presets.delete(uow, preset_id=pid)
        return {"deleted": True, "preset_id": pid}

    # ------------------------------------------------------------------ #
    # Append-only versions
    # ------------------------------------------------------------------ #
    def publish_version(self, *, preset_id: Any, content: Any = None) -> dict[str, Any]:
        """Publish the next immutable version (``version = MAX+1``). ``NOT_FOUND``
        when the preset does not exist; ``VALIDATION_ERROR`` on a malformed body."""
        pid = str(preset_id)
        body = validate_preset_version_form(content=content)
        with self._cf.unit_of_work() as uow:
            self._require(uow, preset_id=pid)
            version = self._presets.add_version(
                uow, preset_id=pid, content=body["content"]
            )
        return _version(version)

    def list_versions(self, *, preset_id: Any) -> list[dict[str, Any]]:
        """Every published version of a preset, ascending. ``NOT_FOUND`` if absent."""
        pid = str(preset_id)
        with self._cf.unit_of_work(write=False) as uow:
            self._require(uow, preset_id=pid)
            versions = self._presets.list_versions(uow, preset_id=pid)
        return [_version(v) for v in versions]

    # ------------------------------------------------------------------ #
    # Agent binding (SINGLE-SOURCE: inline XOR global)
    # ------------------------------------------------------------------ #
    def set_agent_binding(
        self, *, agent_id: Any, inline: Any = None, global_: Any = None
    ) -> dict[str, Any]:
        """Replace an agent's SINGLE communication binding (inline XOR global).

        Fail-closed. FORM (single-source + inline content grammar + mode/pinned)
        is the domain's job (:func:`compose_comm_binding`); EXISTENCE is checked
        here (it needs IO): an unknown ``agent_id`` or referenced ``preset_id``
        -> ``NOT_FOUND``; a ``pinned_version`` never published ->
        ``VALIDATION_ERROR`` (an orphan pin is forbidden). Passing NEITHER
        ``inline`` nor ``global_`` CLEARS the binding (back to no preset).
        Persisted as ONE row; returns the resolved ``communication`` block
        (BR11) or ``None`` when cleared / currently unresolvable.
        """
        aid = str(agent_id)
        binding = compose_comm_binding(inline=inline, global_ref=global_)
        with self._cf.unit_of_work() as uow:
            if self._agents is not None and self._agents.get(uow, aid) is None:
                raise OktoNexusError(
                    ErrorCode.NOT_FOUND,
                    f"Agent {aid!r} is not registered.",
                    {"agent_id": aid},
                )
            if binding is not None and binding.get("source") == "global":
                self._check_global_existence(uow, binding)
            self._bindings.set(uow, agent_id=aid, binding=binding)
            block = self._resolve(uow, binding)
        return {"agent_id": aid, "communication": block}

    def get_agent_binding(self, *, agent_id: Any) -> dict[str, Any]:
        """Read an agent's CURRENT binding, reshaped for the editor.

        The inverse of :meth:`set_agent_binding`: splits the stored binding back
        into the ``{inline, global}`` contract shape the ``PUT`` accepts, plus
        the RESOLVED ``communication`` block so the dashboard can preview what
        the agent sees. ``inline`` is the embedded content object (or ``None``);
        ``global`` is ``{preset_id, mode, pinned_version?}`` (or ``None``). An
        unknown ``agent_id`` -> ``NOT_FOUND``; an agent with no binding ->
        ``{inline: None, global: None, communication: None}``.
        """
        aid = str(agent_id)
        with self._cf.unit_of_work(write=False) as uow:
            if self._agents is not None and self._agents.get(uow, aid) is None:
                raise OktoNexusError(
                    ErrorCode.NOT_FOUND,
                    f"Agent {aid!r} is not registered.",
                    {"agent_id": aid},
                )
            stored = self._bindings.get(uow, agent_id=aid)
            block = self._resolve(uow, stored)
        inline: dict[str, Any] | None = None
        global_: dict[str, Any] | None = None
        if stored is not None:
            if stored.get("source") == "inline":
                inline = dict(stored.get("content") or {})
            elif stored.get("source") == "global":
                ref: dict[str, Any] = {
                    "preset_id": stored.get("preset_id"),
                    "mode": stored.get("mode"),
                }
                if stored.get("mode") == "pinned":
                    ref["pinned_version"] = stored.get("pinned_version")
                global_ = ref
        return {
            "agent_id": aid,
            "inline": inline,
            "global": global_,
            "communication": block,
        }

    def resolve_communication(self, agent_id: Any) -> dict[str, Any] | None:
        """The SELF-ONLY ``whoami`` communication block for an agent (BR11).

        ``None`` when the agent has no binding OR its global reference currently
        resolves to nothing (a ``latest`` with no published version, or a
        ``pinned`` whose version was removed) - the identity slice then OMITS the
        block, so an agent without a preset is byte-identical to the pre-feature
        whoami. Read-only; safe to call on the whoami hot path.
        """
        aid = str(agent_id)
        with self._cf.unit_of_work(write=False) as uow:
            stored = self._bindings.get(uow, agent_id=aid)
            return self._resolve(uow, stored)

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #
    def _resolve(self, uow: Any, binding: Any) -> dict[str, Any] | None:
        """Resolve a stored binding to its whoami block within an open UoW."""
        if binding is None:
            return None
        versions_by_preset: dict[str, Any] = {}
        preset_id = binding.get("preset_id") if isinstance(binding, dict) else None
        if preset_id:
            versions_by_preset[preset_id] = self._presets.list_versions(
                uow, preset_id=preset_id
            )
        return resolve_communication(binding, versions_by_preset)

    def _check_global_existence(self, uow: Any, binding: dict[str, Any]) -> None:
        """The referenced preset must exist; a pin must resolve (no orphans)."""
        preset_id = binding["preset_id"]
        if self._presets.get(uow, preset_id) is None:
            raise OktoNexusError(
                ErrorCode.NOT_FOUND,
                f"Communication preset {preset_id!r} referenced by the binding "
                "is not registered.",
                {"preset_id": preset_id},
            )
        if binding.get("mode") == "pinned":
            version = binding["pinned_version"]
            if (
                self._presets.get_version(uow, preset_id=preset_id, version=version)
                is None
            ):
                raise OktoNexusError(
                    ErrorCode.VALIDATION_ERROR,
                    f"pinned_version {version} of communication preset "
                    f"{preset_id!r} does not exist.",
                    {"preset_id": preset_id, "pinned_version": version},
                )

    def _require(self, uow: Any, *, preset_id: str) -> Any:
        record = self._presets.get(uow, preset_id)
        if record is None:
            raise OktoNexusError(
                ErrorCode.NOT_FOUND,
                f"Communication preset {preset_id!r} not found.",
                {"preset_id": preset_id},
            )
        return record

    def _reject_duplicate_name(
        self, uow: Any, *, name: str, excluding: str | None
    ) -> None:
        clash = self._presets.get_by_name(uow, name)
        if clash is not None and clash.preset_id != excluding:
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                f"a communication preset named {name!r} already exists.",
                {"name": name, "preset_id": clash.preset_id},
            )


def seed_comm_presets(uow: UnitOfWork, *, presets: CommPresetRepo) -> int:
    """Seed :data:`BUILTIN_COMM_PRESETS` (create-if-missing, idempotent).

    Runs at every bootstrap inside the caller's unit of work. For each built-in
    whose NAME is not already registered, creates the header + publishes its v1
    content. An existing name (including an operator's edit or rename) is never
    touched, so re-running never duplicates a preset or bumps a version. Returns
    how many presets were newly created. Mirrors
    :func:`okto_nexus.application.capabilities.seed_capability_catalog` /
    :func:`okto_nexus.application.approvals.seed_operator_agent`.
    """
    created = 0
    for name, description, content in BUILTIN_COMM_PRESETS:
        if presets.get_by_name(uow, name) is not None:
            continue
        preset_id = new_id("cpr")
        presets.create(uow, preset_id=preset_id, name=name, description=description)
        presets.add_version(
            uow, preset_id=preset_id, content=validate_content_form(content)
        )
        created += 1
    return created

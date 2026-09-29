"""Local Core catalog and installation evidence without runtime composition.

This adapter can run while no harness binary or provider credential exists.
The producing host retains complete candidates; HTTP receives only the
Core's path-free projection. No Connector application is imported here.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable

if TYPE_CHECKING:
    from nexus_connector_core import InstallationCandidate

R4_NXL_REVISION = "nxl-1-agent-centric-http-only-2026-09-29-r4"
MANAGEMENT_REVISION = "nexus-connections-2026-09-29-r4"
CORE_INVENTORY_VERSION = "0.2.21.dev0"
# Promoted only after admission, lease, dispatcher and Connector conformance.
SERVER_R4_EXECUTION_READY = False


def _core():
    import nexus_connector_core as core

    if core.__version__ != CORE_INVENTORY_VERSION:
        raise RuntimeError(
            f"Core {CORE_INVENTORY_VERSION} is required for R4 inventory; "
            f"installed {core.__version__}"
        )
    return core


def protocol_info() -> dict[str, Any]:
    """Advertise implemented facts; r3 never masquerades as r4 readiness."""
    core = _core()
    remote_ready = bool(
        SERVER_R4_EXECUTION_READY
        and getattr(core, "R4_BUNDLE_EXECUTABLE", False)
        and core.CONTRACT_REVISION == R4_NXL_REVISION
    )
    return {
        "management_revision": MANAGEMENT_REVISION,
        "protocol_major": 1,
        "nxl_accepted": [R4_NXL_REVISION] if remote_ready else [],
        "nxl_historical_revision": core.CONTRACT_REVISION,
        "core_version": core.__version__,
        "catalog_format": core.CATALOG_FORMAT_VERSION,
        "availability_format": core.AVAILABILITY_FORMAT_VERSION,
        "executor_snapshot_format": core.SNAPSHOT_FORMAT_VERSION,
        "limits": {"inventory_candidates": 128, "snapshot_age_ms": 300000},
        "remote_execution_ready": remote_ready,
    }


def local_catalog() -> dict[str, Any]:
    """Catalog from Core's static registry; never constructs a runtime."""
    catalog = _core().get_runtime_catalog()
    return {
        "core_version": catalog.core_version,
        "format_version": catalog.format_version,
        "runtimes": [
            {
                "adapter_id": item.adapter_id,
                "display_name": item.display_name,
                "harness_family": item.harness_family,
                "native_kind": item.native_kind,
                "connection_mode": item.connection_mode,
                "implementation_platforms": list(item.implementation_platforms),
                "support_status": item.support_status,
                "discoverable": item.discoverable,
            }
            for item in catalog.runtimes
        ],
    }


def discover_local_candidates(*, trusted_roots: tuple[Path, ...] = (),
                              path_env: str | None = None):
    """Retain complete candidates on the Nexus host without a dummy runtime."""
    return _core().discover_installations(
        trusted_roots=trusted_roots, path_env=path_env,
    )


def local_inventory_snapshot(
    candidates: Iterable[InstallationCandidate], *, server_id: str,
    executor_id: str, producer_instance_id: str, publication_sequence: int,
    observation_age_ms: int = 0,
) -> dict[str, Any]:
    """Project the complete local candidates through the same Core as Connector."""
    core = _core()
    snapshot = core.build_executor_inventory_snapshot(
        candidates, server_id=server_id, executor_id=executor_id,
        producer_instance_id=producer_instance_id,
        publication_sequence=publication_sequence,
        observation_age_ms=observation_age_ms,
    )
    core.verify_executor_inventory_snapshot(snapshot)
    return snapshot


def resolve_local_installation_selection(
    candidates: Iterable[InstallationCandidate], *, adapter_id: str,
    candidate_ref: str, expected_inventory_revision: str,
) -> InstallationCandidate:
    """Resolve a displayed local selection against fresh Core evidence.

    The caller supplies only candidates discovered on this Nexus host. Remote
    inventory rows are path-free and must be resolved by their own executor.
    No process, runtime or provider is composed here.
    """
    core = _core()
    items = tuple(candidates)
    current_revision = core.calculate_inventory_revision(items)
    if current_revision != expected_inventory_revision:
        raise core.CoreError("STALE_GENERATION", "inventory_selection",
                             retry_safe=True,
                             message="The selected inventory revision is stale.")
    return core.resolve_installation(items, adapter_id, candidate_ref)

"""Local Core catalog and installation evidence without runtime composition.

This adapter can run while no harness binary or provider credential exists.
The producing host retains complete candidates; HTTP receives only the
Core's path-free projection. No Connector application is imported here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Iterable

if TYPE_CHECKING:
    from nexus_connector_core import InstallationCandidate

R4_NXL_REVISION = "nxl-1-agent-centric-http-only-2026-09-29-r4"
MANAGEMENT_REVISION = "nexus-connections-2026-09-29-r4"
CORE_INVENTORY_VERSION = "0.2.11.dev0"


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
    return {
        "management_revision": MANAGEMENT_REVISION,
        "protocol_major": 1,
        "nxl_accepted": ([R4_NXL_REVISION]
                         if core.CONTRACT_REVISION == R4_NXL_REVISION else []),
        "nxl_historical_revision": core.CONTRACT_REVISION,
        "core_version": core.__version__,
        "catalog_format": core.CATALOG_FORMAT_VERSION,
        "availability_format": core.AVAILABILITY_FORMAT_VERSION,
        "executor_snapshot_format": core.SNAPSHOT_FORMAT_VERSION,
        "limits": {"inventory_candidates": 128, "snapshot_age_ms": 300000},
        "remote_execution_ready": core.CONTRACT_REVISION == R4_NXL_REVISION,
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

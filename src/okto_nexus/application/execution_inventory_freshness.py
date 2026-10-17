"""One per-harness inventory freshness policy for all Server consumers."""
import json
import time

from nexus_connector_core import CoreError, __version__, inventory_observation_fresh

INVENTORY_TTL_MS = 120_000


def inventory_is_fresh(current, receipt, adapter_id, *, monotonic_now=None):
    """Require current-process receipt and current Core evidence for ONE adapter.

    A retained snapshot has no freshness after process replacement. Heartbeats
    and publications for sibling adapters cannot renew this adapter's evidence.
    This proves observation only, never consent or permission to execute.
    """
    if current is None or receipt is None or receipt[0] != current['publication_sequence']:
        return False
    now = time.monotonic() if monotonic_now is None else monotonic_now
    elapsed = max(0, int((now - receipt[1]) * 1000))
    try:
        snapshot = json.loads(current['canonical_projection'])
        return (snapshot['core_version'] == __version__ and
                inventory_observation_fresh(snapshot, adapter_id, elapsed_ms=elapsed,
                                            ttl_ms=INVENTORY_TTL_MS))
    except (CoreError, KeyError, ValueError, TypeError):
        return False

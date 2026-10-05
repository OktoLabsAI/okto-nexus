"""Keep synthetic R4 campaigns independent of personal harness installations."""
from types import SimpleNamespace

import pytest


@pytest.fixture(autouse=True)
def isolated_embedded_inventory(monkeypatch):
    # These campaigns provide their own selected candidates/native peers.
    # Inventory tests can override this default explicitly; direct calls to
    # core_inventory.discover_local_candidates remain real and unchanged.
    from okto_nexus.bootstrap import embedded_inventory

    monkeypatch.setattr(
        embedded_inventory, "discover_local_candidates",
        lambda **_: SimpleNamespace(candidates=()),
    )

"""Disposable crash/restart process for the normative history scenario."""
import asyncio
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

sys.path.insert(0, sys.argv[1])
root = Path(sys.argv[2])
mode = sys.argv[3]

if mode == "produce":
    sys.path.insert(0, str(Path(__file__).parent))
    import pytest
    from test_local_realization import local_setup
    from test_embedded_dispatch import qualified_contract, connect_local, admit, wait_receipt
    patches = pytest.MonkeyPatch()
    qualified_contract.__wrapped__(patches)
    lifetime = local_setup.__wrapped__(root, patches, SimpleNamespace())
    setup = next(lifetime)
    connected = connect_local(setup)
    _, binding, native = connected
    opened = admit(setup, binding, "ns14-restart-open", "runtime.start", new_session=True)
    view = wait_receipt(setup, opened)
    assert native.opens == 1
    deps, app, client, headers, body, candidate, workspace = setup
    with deps.connection_factory.unit_of_work(write=False) as uow:
        owner_expiry = uow.connection.execute(
            "SELECT lease_expires_at FROM runtime_dispatcher_owner WHERE owner_key='dispatcher'"
        ).fetchone()[0]
    record = dict(owner_expiry=owner_expiry, opened=opened, view=view, binding=binding, headers=headers,
                  binary=candidate.executable, home=str(deps.config.home_dir), pid=os.getpid())
    (root / "restart-record.json").write_text(json.dumps(record), encoding="utf-8")
    # Deliberate abrupt application death after committed Core/Nexus receipts.
    # No graceful close/release or fixture teardown is allowed in this phase.
    os._exit(0)

from nexus_connector_core import OperationKey, SessionKey, SQLiteOwnedSlotLedger
from okto_nexus.adapters.inbound.cli.runtime_server import RuntimeServer
from okto_nexus.adapters.inbound.cli.serve import run_serve
from okto_nexus.bootstrap import runtime_host

record = json.loads((root / "restart-record.json").read_text(encoding="utf-8"))
scope = record["opened"]["scope"]
def forbidden_runtime(*args, **kwargs):
    (root / "unexpected-runtime").touch()
    raise AssertionError("Historical recovery must not construct a native runtime")
runtime_host.create_runtime = forbidden_runtime
original_startup = RuntimeServer.startup
async def startup(self, sockets=None):
    await original_startup(self, sockets=sockets)
    if not self.started:
        return
    host = self.config.app.state.embedded_core_host
    key = OperationKey(scope["server_id"], scope["executor_id"], record["opened"]["operation_id"])
    receipt = await host.historical_receipt(session_id=scope["session_id"], key=key)
    async def read(journal):
        page = await journal.claimed_sessions(scope["server_id"], scope["executor_id"], limit=1)
        lease = await journal.get_session_lease(SessionKey(scope["server_id"], scope["executor_id"], scope["session_id"]))
        return dict(claim_ids=[c.key.session_id for c in page.claims],
                    next_after_rowid=page.next_after_rowid,
                    connection_generation=lease.connection_generation,
                    owner_generation=lease.owner_generation)
    facts = await host.with_history(executor_id=scope["executor_id"], session_id=scope["session_id"], read=read)
    ledger = SQLiteOwnedSlotLedger(host.store_dir / "owned-slots.db", max_slots=host.max_owned_slots)
    try:
        page = await ledger.owned_slot_page(limit=1)
        slot = await ledger.owned_slot_state(SessionKey(scope["server_id"], scope["executor_id"], scope["session_id"]))
        facts.update(slot_released=slot.released,
                     reservations=[r.key.session_id for r in page.reservations])
    finally:
        await ledger.aclose()
    facts.update(operation_id=receipt.operation_id, stage=receipt.stage,
                 runtimes=len(host._runtime_tasks), pid=os.getpid())
    (root / "restart-probe.json").write_text(json.dumps(facts), encoding="utf-8")
RuntimeServer.startup = startup
raise SystemExit(run_serve(sys.argv[4:]))

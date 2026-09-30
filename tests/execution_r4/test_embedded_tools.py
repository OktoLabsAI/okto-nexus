"""Automatic local capability/configuration reaches real HTTP MCP handlers."""
import asyncio
import json
from pathlib import Path
import time
import tomllib

import pytest

from test_embedded_dispatch import qualified_contract, connected_local, admit, wait_receipt
from test_local_realization import local_setup
from test_mcp_session_capabilities import rpc,envelope,seed_work,args


class Vault:
    def __init__(self): self.values={}
    def store(self,key,value): self.values[key]=value
    def remove(self,key): del self.values[key]


def enable_tools(connected_local):
    setup,binding,native=connected_local
    deps,app,client,*_=setup
    deps.runtime_owner_api_url="http://127.0.0.1:8202"
    vault=Vault()
    owner=app.state.embedded_dispatch_owner
    owner.tools.vault=vault
    environments=[]
    original=native.open
    async def capture(prepared,session_id,context,**kwargs):
        environment=await owner.sessions[session_id]["executor"].environment(prepared)
        environments.append(environment)
        return await original(prepared,session_id,context,**kwargs)
    native.open=capture
    return setup,binding,native,vault,environments


def test_automatic_mcp_configuration_claims_work_and_cleans_secret(connected_local,monkeypatch):
    setup,binding,native,vault,environments=enable_tools(connected_local)
    deps,app,client,headers,*_=setup
    monkeypatch.setattr(app.state.embedded_dispatch_owner.leases,"max_duration_ms",2000)
    opened=admit(setup,binding,"tools-open","runtime.start",new_session=True)
    wait_receipt(setup,opened)
    assert len(vault.values)==1 and native.opens==1
    config_path=Path(environments[0]["HOME"])/".codex/config.toml"
    entry=tomllib.loads(config_path.read_text())["mcp_servers"]["nexus"]
    secret=environments[0][entry["bearer_token_env_var"]]
    assert secret in vault.values.values() and secret not in config_path.read_text()
    assert entry["url"]=="http://127.0.0.1:8202/mcp"
    who=envelope(rpc(setup,secret))
    assert who["ok"] and who["data"]["session_scope"]==opened["scope"]
    workspace=opened["scope"]["workspace_id"]
    seed_work(setup,workspace=workspace)
    parameters=args(project_root=workspace)
    claim=envelope(rpc(setup,secret,"handoff_claim",parameters))
    assert claim["ok"],claim
    done=envelope(rpc(setup,secret,"handoff_complete",parameters|dict(claim_epoch=claim["data"]["claim_epoch"],result="Reviewed.")))
    assert done["ok"],done
    until=time.monotonic()+5
    while True:
        with deps.connection_factory.unit_of_work(write=False) as uow:
            serial=uow.connection.execute("SELECT MAX(lease_serial) FROM execution_leases WHERE status='ACTIVE'").fetchone()[0]
        if serial>=2:
            break
        assert time.monotonic()<until
        time.sleep(.02)
    assert envelope(rpc(setup,secret))["ok"] and len(vault.values)==1
    with deps.connection_factory.unit_of_work(write=False) as uow:
        row=uow.connection.execute("SELECT status,metadata_json FROM execution_local_tool_credentials").fetchone()
        assert row["status"]=="STORED" and secret not in row["metadata_json"]
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_link_tickets").fetchone()[0]==0
    closed=admit(setup,binding,"tools-close","runtime.close",session_id=opened["scope"]["session_id"])
    wait_receipt(setup,closed,stages=("SUCCEEDED",))
    assert rpc(setup,secret).status_code in (401,403)
    until=time.monotonic()+5
    while vault.values:
        assert time.monotonic()<until
        time.sleep(.02)
    client.portal.call(app.state.embedded_dispatch_owner.close)
    assert not vault.values


def test_vault_failure_prevents_native_tool_launch(connected_local):
    setup,binding,native,vault,environments=enable_tools(connected_local)
    _,app,*_=setup
    def broken(*args): raise OSError("Technical vault write failure")
    vault.store=broken
    admit(setup,binding,"tools-vault-failure","runtime.start",new_session=True)
    until=time.monotonic()+5
    while app.state.embedded_dispatch_owner.failure is None:
        assert time.monotonic()<until
        time.sleep(.02)
    assert isinstance(app.state.embedded_dispatch_owner.failure,OSError)
    assert native.opens==0 and not environments


def test_cancelled_tool_waiter_keeps_issuance_owned(connected_local,monkeypatch):
    import threading
    setup,binding,native,vault,environments=enable_tools(connected_local)
    _,app,client,*_=setup
    entered,release=threading.Event(),threading.Event()
    original=vault.store
    def held(*args):
        entered.set()
        assert release.wait(10)
        original(*args)
    vault.store=held
    opened=admit(setup,binding,"tools-retained","runtime.start",new_session=True)
    assert entered.wait(5)
    owner=app.state.embedded_dispatch_owner
    async def cancel_observer():
        worker=next(iter(owner.workers))
        worker.cancel()
        await asyncio.gather(worker,return_exceptions=True)
        assert any(not task.done() for _,task in owner.tools.tasks.values())
    try:
        client.portal.call(cancel_observer)
    finally:
        release.set()
    client.portal.call(owner.close)
    assert native.opens==0 and not vault.values

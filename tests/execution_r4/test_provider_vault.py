"""Protected provider references, local owner CLI and approved launch wiring."""
import io
import json
import os
import time
from pathlib import Path

import pytest

from okto_nexus.adapters.outbound import provider_vault as vaults
from okto_nexus.adapters.inbound.cli.main import main
from test_embedded_dispatch import qualified_contract, connect_local, admit, wait_receipt
from test_local_realization import local_setup


class MemoryBackend:
    def __init__(self):
        self.values={}
    def get(self,service,name):
        return self.values.get((service,name))
    def set(self,service,name,value):
        self.values[service,name]=value
    def remove(self,service,name):
        del self.values[service,name]


@pytest.fixture
def backend(monkeypatch):
    value=MemoryBackend()
    monkeypatch.setattr(vaults,"open_backend",lambda:value)
    return value


def test_cli_store_scope_replace_and_remove(tmp_path,monkeypatch,capsys,backend):
    args=["provider-credentials","set","--home",str(tmp_path),"--agent-id","subject","--reference","vault:provider","--secret-stdin"]
    for secret in ("technical-provider-one","technical-provider-two"):
        monkeypatch.setattr("sys.stdin",io.StringIO(secret+"\n"))
        assert main(args)==0
        output=capsys.readouterr()
        assert secret not in output.out+output.err
        assert json.loads(output.out)["reference"]=="vault:provider"
        assert vaults.ProviderVault(tmp_path,"subject").resolve("vault:provider")==secret
    for home,agent in ((tmp_path,"another"),(tmp_path/"other","subject")):
        with pytest.raises(vaults.ProviderVaultError):
            vaults.ProviderVault(home,agent).resolve("vault:provider")
    assert main([*args[:1],"remove",*args[2:-1]])==0
    with pytest.raises(vaults.ProviderVaultError):
        vaults.ProviderVault(tmp_path,"subject").resolve("vault:provider")
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("secret",["", "nxc4_not-a-provider", "value\nmore", "x"*4097])
def test_invalid_secret_is_not_stored(tmp_path,secret,backend):
    with pytest.raises(vaults.ProviderVaultError):
        vaults.ProviderVault(tmp_path,"subject").store("vault:key",secret)
    assert not backend.values


def test_backend_error_never_exposes_material(tmp_path,monkeypatch,capsys):
    class Broken(MemoryBackend):
        def set(self,*args):
            raise RuntimeError("technical-secret-must-not-escape")
    monkeypatch.setattr(vaults,"open_backend",lambda:Broken())
    monkeypatch.setattr("sys.stdin",io.StringIO("technical-secret-must-not-escape"))
    assert main(["provider-credentials","set","--home",str(tmp_path),"--agent-id","subject",
                 "--reference","vault:key","--secret-stdin"])==1
    assert "technical-secret-must-not-escape" not in str(capsys.readouterr())


@pytest.mark.parametrize("present",[True,False])
def test_public_local_launch_resolves_only_approved_agent_vault(local_setup,backend,present):
    setup,binding,native=connect_local(local_setup,secret_bindings={"OPENAI_API_KEY":"vault:provider"})
    deps,app,client,*_=setup
    vaults.ProviderVault(deps.config.home_dir,"other-agent").store("vault:provider","other-agent-secret")
    if present:
        vaults.ProviderVault(deps.config.home_dir,"subject").store("vault:provider","technical-provider-secret")
    observed=[]
    original=native.open
    async def open_with_environment(prepared,session_id,context,**kwargs):
        executor=app.state.embedded_dispatch_owner.sessions[session_id]["executor"]
        observed.append(await executor.environment(prepared))
        return await original(prepared,session_id,context,**kwargs)
    native.open=open_with_environment
    opened=admit(setup,binding,"vault-open","runtime.start",new_session=True)
    if present:
        receipt=wait_receipt(setup,opened)
        assert native.opens==1 and observed[0]["OPENAI_API_KEY"]=="technical-provider-secret"
        assert "other-agent-secret" not in str(observed)
    else:
        owner=app.state.embedded_dispatch_owner
        until=time.monotonic()+5
        while owner.failure is None:
            assert time.monotonic()<until
            time.sleep(.02)
        assert owner.failure.code=="PROVIDER_AUTH_REQUIRED"
        receipt={"code":owner.failure.code}
        assert native.opens==0 and not observed
    assert "technical-provider-secret" not in json.dumps(receipt)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        raw=uow.connection.execute("SELECT local_record_json FROM execution_local_realizations").fetchone()[0]
        assert "vault:provider" in raw and "technical-provider-secret" not in raw


@pytest.mark.skipif(os.name!="nt",reason="Windows Credential Manager integration")
def test_windows_os_vault_roundtrip_and_cleanup(tmp_path):
    vault=vaults.ProviderVault(tmp_path,"technical-agent")
    try:
        assert vault.store("vault:roundtrip","technical-os-provider")=="vault:roundtrip"
        assert vault.resolve("vault:roundtrip")=="technical-os-provider"
        with pytest.raises(vaults.ProviderVaultError):
            vaults.ProviderVault(tmp_path,"another-agent").resolve("vault:roundtrip")
        assert not list(tmp_path.iterdir())
    finally:
        vault.remove("vault:roundtrip")
    with pytest.raises(vaults.ProviderVaultError):
        vault.resolve("vault:roundtrip")

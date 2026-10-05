"""Installed Windows CLI/OS-vault roundtrip; disposable synthetic credential."""
import json
from pathlib import Path
import platform
import subprocess
import sys
import tempfile

from okto_nexus.adapters.outbound.provider_vault import ProviderVault, ProviderVaultError

home=Path(tempfile.mkdtemp(prefix="okto-provider-vault-cli-"))
secret="synthetic-cli-provider-credential"
reference="vault:probe"
vault=ProviderVault(home,"probe-agent")
base=[sys.executable,"-I","-m","okto_nexus.adapters.inbound.cli.main","provider-credentials"]
options=["--home",str(home),"--agent-id","probe-agent","--reference",reference]
records=[]
stored=False
try:
    command=base+["set",*options,"--secret-stdin"]
    result=subprocess.run(command,input=secret+"\n",capture_output=True,text=True)
    assert result.returncode==0 and secret not in result.stdout+result.stderr
    stored=True
    assert json.loads(result.stdout)["reference"]==reference
    assert vault.resolve(reference)==secret
    records.append({"command":command,"exit_code":result.returncode,"secret_absent_from_output":True})
    command=base+["remove",*options]
    result=subprocess.run(command,capture_output=True,text=True)
    assert result.returncode==0 and secret not in result.stdout+result.stderr
    stored=False
    records.append({"command":command,"exit_code":result.returncode,"secret_absent_from_output":True})
    try:
        vault.resolve(reference)
    except ProviderVaultError:
        pass
    else:
        raise AssertionError("Credential removal was not observed.")
    assert not list(home.iterdir())
    output=Path(__file__).parent/"evidence/provider-vault-cli-installed.json"
    output.write_text(json.dumps({"platform":platform.platform(),"executable":sys.executable,
        "commands":records,"roundtrip":True,"removed":True,"plaintext_files_created":False},indent=2)+"\n")
    print("Installed CLI and Windows OS credential roundtrip passed; credential removed.")
finally:
    if stored:
        vault.remove(reference)

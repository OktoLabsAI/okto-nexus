"""Provider secrets scoped to a Nexus installation and agent in the OS vault."""
import hashlib
import os
from pathlib import Path
import re


class ProviderVaultError(ValueError):
    pass


class WindowsCredentials:
    name = "windows-credential-manager"

    def __init__(self):
        import win32cred
        self.api = win32cred

    def get(self, service, name):
        try:
            return self.api.CredRead(service+"/"+name,self.api.CRED_TYPE_GENERIC)["CredentialBlob"].decode("utf-16-le")
        except Exception:
            raise ProviderVaultError("The provider credential is unavailable.") from None

    def set(self, service, name, value):
        self.api.CredWrite(dict(Type=self.api.CRED_TYPE_GENERIC,TargetName=service+"/"+name,
            UserName="okto-nexus",CredentialBlob=value,Persist=self.api.CRED_PERSIST_LOCAL_MACHINE),0)

    def remove(self, service, name):
        self.api.CredDelete(service+"/"+name,self.api.CRED_TYPE_GENERIC,0)


class SystemKeyring:
    name = "os-keyring"

    def __init__(self):
        import keyring
        backend = keyring.get_keyring()
        # Only protected system backends may store application credentials.
        if type(backend).__module__ not in ("keyring.backends.SecretService", "keyring.backends.macOS"):
            raise ProviderVaultError("A protected OS keyring backend is required.")
        self.api = backend

    def get(self, service, name):
        return self.api.get_password(service,name)

    def set(self, service, name, value):
        self.api.set_password(service,name,value)

    def remove(self, service, name):
        self.api.delete_password(service,name)


def open_backend():
    try:
        return WindowsCredentials() if os.name=="nt" else SystemKeyring()
    except Exception:
        raise ProviderVaultError("The protected OS credential store is unavailable.") from None


def validate_provider_secret(value):
    if (not isinstance(value,str) or not value or len(value.encode("utf-8"))>4096
            or any(c in value for c in ("\r","\n","\0"))
            or any(prefix in value for prefix in ("nxs_","nxsept_","nxc4_","nxt4_"))):
        raise ProviderVaultError("A valid provider credential is required.")
    return value


class ProviderVault:
    def __init__(self, home, agent_id, *, backend=None):
        if not isinstance(agent_id,str) or not 1<=len(agent_id)<=160 or any(c in agent_id for c in "\r\n\0"):
            raise ProviderVaultError("A valid agent ID is required.")
        root = str(Path(home).resolve())
        if os.name=="nt":
            root = os.path.normcase(root)
        digest = hashlib.sha256((root+"\0"+agent_id).encode("utf-8")).hexdigest()
        self.service = "okto-nexus/provider/"+digest
        self.backend = backend

    def _name(self, reference):
        if not isinstance(reference,str) or not re.fullmatch(r"vault:[A-Za-z0-9_.-]{1,128}",reference):
            raise ProviderVaultError("A provider reference must use vault:<name>.")
        return reference[6:]

    def _call(self, operation, reference, value=None):
        name = self._name(reference)
        backend = self.backend or open_backend()
        try:
            if operation=="set":
                backend.set(self.service,name,validate_provider_secret(value))
                return reference
            if operation=="remove":
                backend.remove(self.service,name)
                return reference
            return validate_provider_secret(backend.get(self.service,name))
        except Exception:
            raise ProviderVaultError("The provider credential operation failed.") from None

    def store(self, reference, value):
        return self._call("set",reference,value)

    def resolve(self, reference):
        return self._call("get",reference)

    def remove(self, reference):
        return self._call("remove",reference)

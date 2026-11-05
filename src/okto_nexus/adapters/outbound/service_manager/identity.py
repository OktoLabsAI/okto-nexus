"""Host-resolved instance identity; no credential or environment impersonation."""
from __future__ import annotations

import os
from pathlib import Path

from ....domain.service_lifecycle import instance_id


def effective_principal() -> str:
    if os.name != 'nt':
        return f'uid:{os.geteuid()}'
    # pywin32 is part of both Windows serve extras. Use the process token, not
    # USERNAME/USERPROFILE environment variables or an agent's identity.
    import win32api
    import win32security
    token = win32security.OpenProcessToken(win32api.GetCurrentProcess(), win32security.TOKEN_QUERY)
    try:
        sid, _ = win32security.GetTokenInformation(token, win32security.TokenUser)
        return win32security.ConvertSidToStringSid(sid)
    finally:
        token.Close()


def server_instance_id(home: Path, database: Path) -> str:
    return instance_id(component='server', home=os.path.normcase(str(home.resolve())),
                       database=os.path.normcase(str(database.resolve())), principal=effective_principal())


def windows_logon_session() -> str:
    """Effective token logon LUID, not a username or environment assertion.

    Explicit stop suppresses crash retries in this logon session. A later user
    login is a new authorized logon trigger, distinct from crash recovery.
    """
    import win32api
    import win32security
    token = win32security.OpenProcessToken(win32api.GetCurrentProcess(), win32security.TOKEN_QUERY)
    try:
        statistics = win32security.GetTokenInformation(token, win32security.TokenStatistics)
        authentication = statistics['AuthenticationId']
        # LUIDs are unique only until reboot. Include the actual logon time so
        # a reused numeric LUID cannot suppress a later authorized login.
        session = win32security.LsaGetLogonSessionData(authentication)
        return f"{authentication}:{int(session['LogonTime'].timestamp() * 1000000)}"
    finally:
        token.Close()

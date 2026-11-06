"""Host-owned participant file effects using Core's reviewed CAS editor."""
import hashlib
import os
from pathlib import Path
import stat

from nexus_connector_core import CoreError
from nexus_connector_core.config_persistence import _read_document, apply_json_plan_file, apply_toml_plan_file
from nexus_connector_core.participant_config import plan_participant_config, plan_participant_removal

from ...application.terminal_connection import ConnectionError


def digest(raw):
    return hashlib.sha256(raw).hexdigest() if raw is not None else None


def _windows_security():
    import win32api
    import win32con
    import win32security
    token = win32security.OpenProcessToken(win32api.GetCurrentProcess(), win32con.TOKEN_QUERY)
    try:
        owner = win32security.GetTokenInformation(token, win32security.TokenUser)[0]
    finally:
        token.Close()
    return win32security, owner


def _restrict(path, *, directory=False):
    if os.name != 'nt':
        os.chmod(path, 0o700 if directory else 0o600)
        return
    api, owner = _windows_security()
    acl = api.ACL()
    flags = 3 if directory else 0  # Container/object inheritance for new children.
    for sid in (owner, api.CreateWellKnownSid(api.WinLocalSystemSid),
                api.CreateWellKnownSid(api.WinBuiltinAdministratorsSid)):
        acl.AddAccessAllowedAceEx(api.ACL_REVISION, flags, 0x1F01FF, sid)
    api.SetNamedSecurityInfo(str(path), api.SE_FILE_OBJECT,
        api.DACL_SECURITY_INFORMATION | api.PROTECTED_DACL_SECURITY_INFORMATION, None, None, acl, None)


def private_directory(path):
    path = Path(path)
    created = not path.exists()
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink() or getattr(path, 'is_junction', lambda: False)():
        raise ConnectionError('PROFILE_PATH_UNSAFE', 'Select a regular private participant profile directory.')
    if created:
        _restrict(path, directory=True)
    _check_private(path)


def _check_private(path):
    if os.name != 'nt':
        if path.stat().st_uid != os.getuid() or stat.S_IMODE(path.stat().st_mode) & 0o077:
            raise ConnectionError('PROFILE_PATH_UNSAFE', 'Restrict the participant profile directory to its owner before continuing.')
    else:
        api, owner = _windows_security()
        allowed = {str(owner), str(api.CreateWellKnownSid(api.WinLocalSystemSid)),
                   str(api.CreateWellKnownSid(api.WinBuiltinAdministratorsSid))}
        descriptor = api.GetFileSecurity(str(path), api.DACL_SECURITY_INFORMATION)
        acl = descriptor.GetSecurityDescriptorDacl()
        if acl is None or any(acl.GetAce(i)[0][0] != 0 or str(acl.GetAce(i)[-1]) not in allowed
                              for i in range(acl.GetAceCount())):
            raise ConnectionError('PROFILE_PATH_UNSAFE', 'Restrict the participant profile directory ACL to its owner, SYSTEM and administrators.')


def access_revision(path):
    if not path.exists():
        return None
    if os.name != 'nt':
        value = path.stat()
        return digest(str((value.st_uid, value.st_gid, stat.S_IMODE(value.st_mode))).encode())
    api, _ = _windows_security()
    flags = api.OWNER_SECURITY_INFORMATION | api.DACL_SECURITY_INFORMATION
    descriptor = api.GetFileSecurity(str(path), flags)
    return digest(api.ConvertSecurityDescriptorToStringSecurityDescriptor(descriptor, 1, flags).encode())


def _anchor(path):
    current = path.parent
    while not current.exists():
        current = current.parent
    if not current.is_dir():
        raise ConnectionError('CONFIG_PATH_INVALID', 'The selected configuration needs a directory parent.')
    resolved = current.resolve(strict=True)
    info = resolved.stat()
    return dict(path=str(resolved), device=info.st_dev, inode=info.st_ino), path.relative_to(current)


def file_plan(selected_path, config):
    path = Path(selected_path).expanduser().absolute()
    if path.is_symlink() or getattr(path, 'is_junction', lambda: False)():
        raise ConnectionError('CONFIG_PATH_INVALID', 'Select the actual client file rather than a link.')
    anchor, relative = _anchor(path)
    path = Path(anchor['path']) / relative
    raw, _ = _read_document(path)
    plan = plan_participant_config(raw, config)
    return dict(path=str(path), anchor=anchor, expected_sha256=plan.expected_sha256,
        replacement_sha256=digest(plan._replacement), access_revision=access_revision(path),
        changed=plan.changed, changed_fields=list(plan.changed_fields))


def _validate_path(review):
    path, anchor = Path(review['path']), review['anchor']
    parent = Path(anchor['path'])
    info = parent.stat()
    if (str(parent.resolve(strict=True)) != anchor['path'] or
            (info.st_dev, info.st_ino) != (anchor['device'], anchor['inode']) or not path.is_relative_to(parent)):
        raise ConnectionError('CONFIG_PATH_CHANGED', 'The selected configuration directory changed after review.')
    for child in (path, *path.parents):
        if child == parent:
            break
        if child.is_symlink() or getattr(child, 'is_junction', lambda: False)():
            raise ConnectionError('CONFIG_PATH_CHANGED', 'A link replaced part of the reviewed configuration path.')
    return path


def inspect_file(review, config):
    path = _validate_path(review)
    raw, _ = _read_document(path)
    current = digest(raw)
    if current == review['replacement_sha256']:
        if review['access_revision'] is not None:
            if access_revision(path) != review['access_revision']:
                raise ConnectionError('CONFIG_ACCESS_CHANGED', 'The applied file access policy changed; inspect it before resuming.')
        else:
            _check_private(path)
        return 'applied'
    if current == review['expected_sha256'] and access_revision(path) == review['access_revision']:
        return 'original'
    # Do not infer ownership from a matching name after an uncertain write.
    raise ConnectionError('CONFIG_CHANGED', 'The selected file or access policy changed. Preserve it and inspect the retained setup before a new review.')


def apply_file(review, config):
    path = _validate_path(review)
    if inspect_file(review, config) == 'applied':
        return dict(recovered=True, backup_path=None)
    raw, _ = _read_document(path)
    plan = plan_participant_config(raw, config)
    return _apply_plan(review, config, path, plan)


def _apply_plan(review, config, path, plan):
    if digest(plan._replacement) != review['replacement_sha256']:
        raise ConnectionError('CONFIG_PLAN_CHANGED', 'The participant renderer changed; review the file again.')
    original_security = None
    original_exists = path.exists()
    if os.name == 'nt' and original_exists:
        api, _ = _windows_security()
        original_security = api.GetFileSecurity(str(path), api.DACL_SECURITY_INFORMATION)
    def prepare_file(created, kind):
        if access_revision(path) != review['access_revision']:
            raise ConnectionError('CONFIG_ACCESS_CHANGED', 'File access policy changed during application; original preserved.')
        if kind == 'backup' or not original_exists:
            _restrict(created)
        elif os.name == 'nt':
            control = original_security.GetSecurityDescriptorControl()[0]
            inheritance = api.PROTECTED_DACL_SECURITY_INFORMATION if control & 0x1000 else api.UNPROTECTED_DACL_SECURITY_INFORMATION
            # SetNamedSecurityInfo merges inherited parent ACEs into an
            # unprotected DACL. Preserve the exact reviewed descriptor instead.
            if control & 0x1000 and control & 0x0400:
                # SetFileSecurity clears AUTO_INHERITED on a protected DACL.
                # The named API preserves that flag without adding parent ACEs
                # when PROTECTED is explicit. Unprotected ACLs still use the
                # descriptor API above to avoid inherited-ACE merging.
                api.SetNamedSecurityInfo(str(created), api.SE_FILE_OBJECT,
                    api.DACL_SECURITY_INFORMATION | inheritance, None, None,
                    original_security.GetSecurityDescriptorDacl(), None)
            else:
                api.SetFileSecurity(str(created), api.DACL_SECURITY_INFORMATION | inheritance, original_security)
            if access_revision(created) != review['access_revision']:
                raise ConnectionError('CONFIG_ACCESS_CHANGED', 'The reviewed file access policy cannot be preserved; original remains unchanged.')
    path.parent.mkdir(parents=True, exist_ok=True)
    apply = apply_toml_plan_file if config.client == 'codex' else apply_json_plan_file
    result = apply(plan, path, prepare_file=prepare_file)
    return dict(recovered=False, backup_path=str(result.backup_path) if result.backup_path else None)


def removal_plan(review, config, *, setup_state):
    if review is None or setup_state not in ('file_pending', 'done'):
        return None  # The setup never reached its file-effect intent.
    path = _validate_path(review)
    if setup_state == 'file_pending' and inspect_file(review, config) == 'original':
        return None  # No uncertain file effect is being claimed as owned.
    raw, _ = _read_document(path)
    try:
        plan = plan_participant_removal(raw, config, previously_owned=config.entry())
    except CoreError:
        raise ConnectionError('PARTICIPANT_ENTRY_NOT_OWNED',
            'The client entry is absent, changed or cannot be safely removed. Inspect it, then use --keep-config to retire only this profile and its credential if appropriate.') from None
    return dict(path=str(path), anchor=review['anchor'], expected_sha256=plan.expected_sha256,
        replacement_sha256=digest(plan._replacement), access_revision=access_revision(path),
        changed=plan.changed, changed_fields=list(plan.changed_fields))


def apply_removal(review, config):
    path = _validate_path(review)
    if inspect_file(review, config) == 'applied':
        return dict(recovered=True, backup_path=None)
    raw, _ = _read_document(path)
    plan = plan_participant_removal(raw, config, previously_owned=config.entry())
    return _apply_plan(review, config, path, plan)


def current_owned_entry(review, config):
    path = _validate_path(review)
    raw, _ = _read_document(path)
    # A confirmed completed receipt owns this exact entry; unrelated later
    # edits remain valid and are never rewritten by reconnect.
    plan = plan_participant_config(raw, config, previously_owned=config.entry())
    if plan.changed:
        raise ConnectionError('CONFIG_CHANGED', 'The saved participant entry was changed; inspect the client configuration.')
    return dict(path=str(path), state='entry_present', client_reload='not_proven')

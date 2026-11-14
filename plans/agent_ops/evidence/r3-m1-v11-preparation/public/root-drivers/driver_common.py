"""Finite v11 root drivers. Importing this module has no external effects."""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import os
import re
import sys

HERE = Path(__file__).resolve().parent
DRIVERS = {
    'root_driver_operator_bootstrap': 'operator_bootstrap.py',
    'root_driver_common': 'driver_common.py',
    'root_driver_invoke': 'invoke.py',
    'root_driver_prepare_observation': 'prepare_observation.py',
    'root_driver_observation': 'm1_v11_observation.py',
    'root_driver_confirm_cleanup': 'm1_v11_confirm_cleanup.py',
    'root_driver_confirm_final_presence': 'confirm_final_presence.py',
    'root_driver_close_campaign': 'close_campaign.py',
}
FINITE_CHOICES = {
    'operator_bootstrap': [('once',)],
    'lifecycle': [('initialize',)] + [(c, a) for c in ('nexus', 'connector') for a in ('install', 'start', 'stop', 'uninstall')],
    'setup': [('local',)],
    'work': [(c, a) for c in ('local', 'connector') for a in ('useful', 'continuation')],
    'remote_setup': [('transfer',)],
    'plan': [('local_plan',), ('connector_host_draft',), ('remote_plan',)],
}


class Refused(RuntimeError):
    pass


def require(value, code):
    if not value:
        raise Refused(code)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_bytes())


def reserve(path, value):
    with Path(path).open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def owned_path(path, root):
    root, path = Path(root).resolve(), Path(path)
    require(path.is_absolute() and path.resolve().is_relative_to(root), 'PATH_OUTSIDE_OWN_ROOT')
    # Refuse junction/reparse redirection even when it resolves back into root.
    for item in [path, *path.parents]:
        if item.exists():
            flags = getattr(item.lstat(), 'st_file_attributes', 0)
            require(not flags & 0x400, 'REPARSE_PATH_REFUSED')
        if item == root:
            break
    return path.resolve()


def validate_documents(proposal, receipt, proposal_hash, approval_hash):
    require(re.fullmatch('[0-9a-f]{64}', proposal_hash or '') is not None, 'PROPOSAL_HASH_REQUIRED')
    require(re.fullmatch('[0-9a-f]{64}', approval_hash or '') is not None, 'APPROVAL_HASH_REQUIRED')
    require(proposal.get('revision') == 11, 'V11_ONLY')
    require(proposal['execution_bundle'].get('status') == 'FROZEN_QUALIFIED', 'FINAL_FROZEN_BUNDLE_REQUIRED')
    contract = proposal['controller_preparation']
    require(receipt.get('status') == 'USER_APPROVED' and receipt.get('proposal_revision') == 11
        and receipt.get('proposal_sha256') == proposal_hash
        and receipt.get('campaign_root') == str(Path(proposal['paths']['campaign_root']).resolve())
        and receipt.get('policy') == contract['policy'] and receipt.get('ancestry') == contract['ancestry']
        and isinstance(receipt.get('user_quote'), str) and bool(receipt['user_quote'].strip()),
        'FRESH_APPROVAL_SCOPE_REQUIRED')


def parser():
    value = argparse.ArgumentParser()
    value.add_argument('--proposal', required=True)
    value.add_argument('--expected-proposal-sha256', required=True)
    value.add_argument('--approval-path', required=True)
    value.add_argument('--approval-sha256', required=True)
    return value


def gate(args):
    """No controller construction, DB, HTTP, Scheduler or process effect."""
    require(sha(args.proposal) == args.expected_proposal_sha256, 'PROPOSAL_CHANGED')
    require(sha(args.approval_path) == args.approval_sha256, 'APPROVAL_CHANGED')
    proposal, receipt = read_json(args.proposal), read_json(args.approval_path)
    validate_documents(proposal, receipt, args.expected_proposal_sha256, args.approval_sha256)
    for key, filename in DRIVERS.items():
        entry = proposal['execution_bundle']['files'].get(key, {})
        require(Path(entry.get('path', '')).resolve() == HERE / filename
            and sha(HERE / filename) == entry.get('sha256'), 'ROOT_DRIVER_PIN_CHANGED')
    entry = proposal['execution_bundle']['files']['context']
    require(sha(entry['path']) == entry['sha256'], 'CONTEXT_CHANGED')
    module_spec = importlib.util.spec_from_file_location('campaign_context', entry['path'])
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    previous = sys.argv
    try:
        sys.argv = ['root-driver', '--proposal', args.proposal,
            '--expected-proposal-sha256', args.expected_proposal_sha256,
            '--approval-path', args.approval_path, '--approval-sha256', args.approval_sha256]
        context = module.load()  # exact prefix/install/product/native/module pins
    finally:
        sys.argv = previous
    require(not (context.ROOT / 'public/closure.json').exists(), 'CAMPAIGN_ALREADY_CLOSED')
    for path in proposal['paths'].values():
        if path != proposal['paths']['codex_executable']:
            owned_path(path, context.ROOT)
    return context


def tags(context):
    return {'proposal_sha256': context.args.expected_proposal_sha256,
        'approval_sha256': context.args.approval_sha256, 'campaign_revision': 11}


def require_tags(value, context):
    require(all(value.get(k) == v for k, v in tags(context).items()), 'EVIDENCE_SCOPE_CHANGED')


def secure_directory(path, root):
    """Protect only this campaign/driver-owned directory, never a personal home."""
    path = owned_path(path, root)
    path.mkdir(exist_ok=True)
    import ntsecuritycon
    import win32api
    import win32con
    import win32security
    token = win32security.OpenProcessToken(win32api.GetCurrentProcess(), win32con.TOKEN_QUERY)
    try:
        user = win32security.GetTokenInformation(token, win32security.TokenUser)[0]
    finally:
        token.Close()
    system = win32security.CreateWellKnownSid(win32security.WinLocalSystemSid, None)
    acl = win32security.ACL()
    inherit = win32con.OBJECT_INHERIT_ACE | win32con.CONTAINER_INHERIT_ACE
    for sid in (user, system):
        acl.AddAccessAllowedAceEx(win32security.ACL_REVISION, inherit, ntsecuritycon.FILE_ALL_ACCESS, sid)
    win32security.SetNamedSecurityInfo(str(path), win32security.SE_FILE_OBJECT,
        win32security.DACL_SECURITY_INFORMATION | win32security.PROTECTED_DACL_SECURITY_INFORMATION,
        None, None, acl, None)
    descriptor = win32security.GetNamedSecurityInfo(str(path), win32security.SE_FILE_OBJECT,
        win32security.DACL_SECURITY_INFORMATION)
    require(descriptor.GetSecurityDescriptorControl()[0] & 0x1000, 'PRIVATE_ACL_UNCONFIRMED')
    actual = descriptor.GetSecurityDescriptorDacl()
    require(actual is not None and actual.GetAceCount() == 2, 'PRIVATE_ACL_UNCONFIRMED')
    expected = {win32security.ConvertSidToStringSid(s) for s in (user, system)}
    seen = set()
    for index in range(actual.GetAceCount()):
        header, mask, sid = actual.GetAce(index)
        require(header[0] == win32security.ACCESS_ALLOWED_ACE_TYPE
            and header[1] & inherit == inherit and not header[1] & 0x10
            and mask == ntsecuritycon.FILE_ALL_ACCESS, 'PRIVATE_ACL_UNCONFIRMED')
        seen.add(win32security.ConvertSidToStringSid(sid))
    require(seen == expected, 'PRIVATE_ACL_UNCONFIRMED')
    return path


def public_save(context, name, value):
    require(re.fullmatch('[a-zA-Z0-9_.-]+[.]json', name) is not None, 'EVIDENCE_NAME_INVALID')
    path = owned_path(context.ROOT / 'public' / name, context.ROOT)
    reserve(path, {**value, **tags(context)})
    return path


def private_outputs():
    return secure_directory(HERE / 'runtime-private', HERE)


def invocation_inventory(context, directory=None, *, allow_pending_uninstall=None):
    directory = Path(directory) if directory is not None else HERE / 'runtime-private'
    require(directory.is_dir(), 'INVOCATION_LEDGER_MISSING')
    inventory = {}
    for path in sorted(directory.glob('*.reserved.json')):
        value = read_json(path)
        require_tags(value, context)
        mode, selection = value.get('mode'), value.get('selection')
        require(isinstance(mode, str) and isinstance(selection, list)
            and all(isinstance(v, str) for v in selection)
            and mode in FINITE_CHOICES and tuple(selection) in FINITE_CHOICES[mode]
            and path.name == '-'.join([mode, *selection]) + '.reserved.json', 'INVOCATION_RECORD_INVALID')
        returned_path = path.with_name(path.name.replace('.reserved.json', '.returned.json'))
        entry = {'mode': mode, 'selection': selection, 'reservation_sha256': sha(path), 'returned_sha256': None}
        if returned_path.exists():
            returned = read_json(returned_path)
            require_tags(returned, context)
            require(returned.get('mode') == mode and returned.get('selection') == selection
                and returned.get('wrapper_exit_confirmed') is True, 'WRAPPER_EXIT_UNCONFIRMED')
            entry.update(returned_sha256=sha(returned_path), returncode=returned['returncode'])
        else:
            require(mode == 'lifecycle' and selection == [allow_pending_uninstall, 'uninstall']
                and allow_pending_uninstall in ('nexus', 'connector'), 'INCOMPLETE_INVOCATION_REQUIRES_RECONCILIATION')
        inventory[path.name] = entry
    require(bool(inventory), 'INVOCATION_LEDGER_EMPTY')
    return inventory


def selection_can_start(entry, component):
    mode, selection = entry['mode'], entry['selection']
    if mode == 'lifecycle':
        return selection == [component, 'start']
    # Planning/connect and remote transfer may start services before publishing
    # their success marker. A lost response never proves no effect.
    return mode in ('plan', 'setup', 'work', 'remote_setup')


def main_guard(main):
    try:
        return main()
    except (Refused, OSError, ValueError, KeyError, TypeError) as error:
        print(json.dumps({'status': 'REFUSED_OR_UNCONFIRMED',
            'code': str(error) if isinstance(error, Refused) else type(error).__name__}), flush=True)
        return 2

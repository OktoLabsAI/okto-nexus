"""Explicit customization creates a fresh review; no earlier hash is reused."""
from copy import copy
from pathlib import Path
import uuid

from ....application.terminal_connection import ConnectionError
from ....domain.quick_connect import normalize_connect_id


class ReviewRestart(Exception):
    def __init__(self, argv, invocation_cwd, frozen_name=None):
        self.argv, self.invocation_cwd, self.frozen_name = argv, invocation_cwd, frozen_name


def customize(args, service_args, document, *, invocation_cwd, read=input, write=print):
    """Return a fresh argv/shortcut proposal, never mutate the reviewed request."""
    write('Customize the next review:\n1. ID do Harness\n2. Project name\n3. Harness\n4. Execution folder\nc. Cancel')
    try:
        choice = read('Customize: ').strip().lower()
    except EOFError:
        return None
    if choice in ('', 'c'):
        return None
    if choice not in ('1', '2', '3', '4'):
        raise ConnectionError('CUSTOMIZATION_REQUIRED', 'Select one of the displayed customization fields.')
    selected = document['selection']
    updated = copy(args)
    updated.client = selected['client']
    updated.project_name = args.project_name
    updated.project = Path(selected['project'])  # A previously chosen root may differ from invocation CWD.
    updated.workspace_id = selected.get('workspace_id')
    updated.connect_id = selected['public_connection']['connect_id']
    try:
        raw = read({'1': 'New ID do Harness: ', '2': 'New project name: ',
            '3': 'New harness (codex/claude/pi): ', '4': 'Existing execution folder: '}[choice])
    except EOFError:
        return None
    if choice == '1':
        updated.connect_id = normalize_connect_id(raw)
    elif choice == '2':
        if args.workspace_id or args.binding_id or args.agent:
            raise ConnectionError('CONNECTION_SELECTOR_CONFLICT', 'Change exact workspace/binding selectors explicitly in a new command.')
        if not raw.strip() or not raw.isprintable() or len(raw) > 160:
            raise ConnectionError('PROJECT_NAME_INVALID', 'Choose a printable project name of at most 160 characters.')
        updated.project_name, updated.workspace_id = raw, None
    elif choice == '3':
        if args.binding_id or args.agent or document.get('kind') == 'public_id_association':
            raise ConnectionError('CONNECTION_SELECTOR_CONFLICT', 'An exact existing binding cannot change harness through customization.')
        updated.client, updated.candidate_ref = raw.lower(), None
        updated.connect_id = None  # Proposed from the newly requested family in a new review.
    else:
        if args.workspace_id or args.binding_id or args.agent or args.operator_profile:
            raise ConnectionError('CONNECTION_SELECTOR_CONFLICT', 'Change exact host/project selectors explicitly in a new command.')
        root = Path(raw).expanduser().resolve(strict=True)
        if not root.is_dir():
            raise ConnectionError('PROJECT_REQUIRED', 'Choose an existing execution directory.')
        updated.project, updated.workspace_id = root, None
    updated.profile = 'connection-' + uuid.uuid4().hex[:24]
    updated.approve = None
    updated.new_connection = document.get('kind') != 'public_id_association'
    if document.get('kind') == 'public_id_association':
        updated.agent, updated.binding_id = selected['agent'], selected['binding_id']
    frozen_name = None
    if choice in ('1', '3'):
        metadata = selected['quick_connect']
        frozen_name = dict(name=selected['label'], source=metadata['project_name_source'],
            status='saved', reason='saved_selection', cwd_resolution=metadata['cwd_resolution'],
            workspace_id=selected.get('workspace_id'))
    argv = [updated.client] if updated.client else []
    if argv and updated.project_name is not None:
        argv.append(updated.project_name)
    for name in ('profile', 'operator_profile', 'remote_draft', 'setup_receipt_output', 'agent', 'new_agent',
                 'name', 'project', 'workspace_id', 'binding_id', 'candidate_ref', 'provider_home', 'timeout', 'connect_id'):
        value = getattr(updated, name)
        if value is not None:
            argv.extend(('--id' if name == 'connect_id' else '--' + name.replace('_', '-'), str(value)))
    for name in ('new_connection', 'no_chat', 'interactive', 'no_interactive'):
        if getattr(updated, name):
            argv.append('--' + name.replace('_', '-'))
    if updated.start_at_login is not None:
        argv.append('--start-at-login' if updated.start_at_login else '--no-start-at-login')
    return ReviewRestart([*argv, *service_args], invocation_cwd, frozen_name)

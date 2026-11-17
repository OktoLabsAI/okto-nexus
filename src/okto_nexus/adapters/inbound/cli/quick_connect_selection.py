"""Prepare Quick Connect choices on existing setup/catalog authorities."""
from dataclasses import asdict
from copy import copy
from urllib.parse import quote, urlencode
import re
import uuid

from ....application.project_preset import CLIENTS
from ....application.terminal_connection import ConnectionError, PREFIX
from .connection_choices import ConnectionChoiceCatalog
from .canonical_connections import merge_canonical_connections, IDENTITY
from .quick_connect_ids import public_ids, require_public_ids, select_id
from .quick_connect_project import local_executor, resolve_project


def choose_harness(call, *, agent_id, executor_id, workspace_id, client=None,
        candidate_ref=None, interactive=False, read=input, write=print):
    inventory = call('GET', PREFIX + '/agents/' + quote(agent_id, safe='') + '/runtime-options?' +
        urlencode(dict(executor_id=executor_id, **({'workspace_id': workspace_id} if workspace_id else {}))))
    if (type(inventory) is not dict or type(inventory.get('options')) is not list
            or type(inventory.get('adapter_freshness')) is not dict
            or inventory.get('agent_id') != agent_id or inventory.get('executor_id') != executor_id
            or any(type(row) is not dict for row in inventory['options'])):
        raise ConnectionError('INVENTORY_UNCONFIRMED', 'The passive harness inventory is unconfirmed.')
    observed = {name: [row for row in inventory['options'] if row.get('adapter_id') == adapter
        and row.get('candidate_ref')] for name, adapter in CLIENTS.items()}
    alternatives = [dict(harness=name, observed=bool(rows),
        freshness=inventory['adapter_freshness'].get(CLIENTS[name], 'UNKNOWN'),
        candidates=[dict(candidate_ref=row['candidate_ref'], can_configure=row.get('can_configure') is True,
            technical_state=row.get('technical_state')) for row in rows]) for name, rows in observed.items()]
    while True:
        if client not in CLIENTS:
            detected = [name for name, rows in observed.items() if rows]
            if client is None and len(detected) == 1:
                client = detected[0]
            elif not interactive:
                raise ConnectionError('CLIENT_SELECTION_REQUIRED', 'Select a supported harness from the passive inventory.', choices=alternatives)
            else:
                write('Choose a supported harness (listing does not test login or run a version command):')
                for index, choice in enumerate(alternatives, 1):
                    state = 'observed' if choice['observed'] else 'not confirmed in inventory'
                    write(f"{index}. {choice['harness']} — {state}; {choice['freshness']}")
                write('c. Cancel')
                while True:
                    try:
                        answer = read('Harness: ').strip().lower()
                    except EOFError:
                        answer = 'c'
                    if answer in ('', 'c'):
                        raise ConnectionError('CONNECT_CANCELLED', 'Harness selection cancelled.')
                    if answer.isdecimal() and 1 <= int(answer) <= len(alternatives):
                        client = alternatives[int(answer) - 1]['harness']
                        break
                    write('Choose a displayed harness or c.')
        rows = observed[client]
        if inventory['adapter_freshness'].get(CLIENTS[client]) != 'FRESH':
            raise ConnectionError('INVENTORY_UNCONFIRMED', 'The selected harness inventory is not fresh; absence and readiness are unconfirmed.', choices=alternatives)
        if candidate_ref:
            rows = [row for row in rows if row['candidate_ref'] == candidate_ref]
        if not rows:
            if not interactive or candidate_ref is not None:
                raise ConnectionError('INSTALLATION_UNAVAILABLE', 'This supported harness has no confirmed installation. No installation was attempted.', choices=alternatives)
            write(f'{client}: no confirmed installation. Choose another or cancel; nothing will be installed.')
            client = ''  # Force an explicit choice, even when only one other family is observed.
            continue
        if len(rows) != 1:
            choices = [dict(candidate_ref=row['candidate_ref'], adapter_id=row['adapter_id'],
                technical_state=row.get('technical_state'), can_configure=row.get('can_configure') is True) for row in rows]
            if not interactive:
                raise ConnectionError('INSTALLATION_SELECTION_REQUIRED', 'Select an exact installation candidate.', choices=choices)
            write('Choose the approved installation candidate:')
            for index, row in enumerate(choices, 1):
                write(f"{index}. {row['candidate_ref']} — {row['technical_state']}")
            write('c. Cancel')
            try:
                answer = read('Installation: ').strip().lower()
            except EOFError:
                answer = 'c'
            if not answer.isdecimal() or not 1 <= int(answer) <= len(rows):
                raise ConnectionError('CONNECT_CANCELLED', 'Installation selection cancelled.')
            rows = [rows[int(answer) - 1]]
        if rows[0].get('can_configure') is not True:
            if not interactive or candidate_ref is not None:
                raise ConnectionError('CONFIGURATION_NOT_AUTHORIZED', 'The canonical policy does not allow configuring this installation.', choices=alternatives)
            write(f'{client}: canonical policy does not allow configuring this installation. Choose another harness or cancel.')
            client = ''
            continue
        return client, rows[0]['candidate_ref']


def _metadata(project, *, operation):
    return dict(version=1, operation=operation,
        project_name_source=project['project_name_source'], name_discovery=project['name_discovery'],
        cwd_resolution=project['cwd_resolution'])


def prepare(call, args, *, root, invocation_cwd, saved=None, interactive=False, read=input, write=print, frozen_name=None):
    """Return canonical new/resume/associate selection; no Test/reserve/Finish."""
    me = call('GET', PREFIX + '/connections/me')
    require_public_ids(call, me['server_id'])
    if args.new_connection and args.binding_id:
        raise ConnectionError('ADDITION_CONFLICT', 'A new connection cannot adopt an existing binding selector.')
    if saved and saved.get('selection', {}).get('quick_connect'):
        if saved.get('state') == 'superseded':
            raise ConnectionError('REVIEW_SUPERSEDED', 'This unapproved review was superseded by customization; use its new shortcut.')
        if saved.get('server_id') != me['server_id']:
            raise ConnectionError('PROFILE_CONFLICT', 'The retained public connection belongs to another Server.')
        selection = dict(saved['selection'])
        if (args.connect_id is not None and selection.get('public_connection', {}).get('connect_id') != args.connect_id
                or args.project_name is not None and selection.get('label') != args.project_name
                or args.client is not None and selection.get('client') != args.client
                or args.new_agent is not None and selection.get('agent') != args.new_agent):
            raise ConnectionError('PROFILE_CONFLICT', 'The explicit Quick Connect choices differ from the retained intent.')
        from .connect import saved_selection
        saved_selection(saved, args, root)
        # Recovery deliberately does not discover Git or probe the namespace.
        return dict(action='retained', selection=selection, server_id=me['server_id'])
    if saved and saved.get('state') != 'done':
        raise ConnectionError('PROFILE_CONFLICT', 'Recover the existing legacy setup before adding a public Harness ID.')
    executor_id = local_executor(call, me['agent_id'])
    discover = None
    if frozen_name is not None:
        from types import SimpleNamespace
        def discover(*args, **kwargs):
            return SimpleNamespace(**frozen_name)
    project = resolve_project(call, server_id=me['server_id'], executor_id=executor_id,
        invocation_cwd=invocation_cwd, root=root, explicit_root=args.project is not None,
        workspace_id=args.workspace_id, project_name=args.project_name, plan=args.plan,
        interactive=interactive, read=read, write=write, discover=discover)
    if frozen_name is not None:
        if (project['label'] != frozen_name['name'] or project['workspace_id'] != frozen_name.get('workspace_id')
                or project['project'] != frozen_name['cwd_resolution']['project_root']):
            raise ConnectionError('PROJECT_SELECTION_CHANGED', 'The previously selected project changed during customization. Resolve it again.')
        project.update(project_name_source=frozen_name['source'],
            name_discovery=dict(status='saved', reason='saved_selection'),
            cwd_resolution=dict(frozen_name['cwd_resolution']))
    rows = public_ids(call, server_id=me['server_id'], workspace_id=project['workspace_id']) if project['workspace_id'] else ()
    client = args.client
    # Canonical public ID selection can resume a binding without testing a new
    # installation. Listing hardware is unnecessary when the exact ID suffices.
    occupant = next((row for row in rows if row['connect_id'] == args.connect_id), None) if args.connect_id else None
    if client is None and occupant and occupant.get('adapter_id') in CLIENTS.values():
        client = next(name for name, adapter in CLIENTS.items() if adapter == occupant['adapter_id'])
    if client is None:
        existing_clients = {name for name, adapter in CLIENTS.items() for row in rows
            if row.get('state') == 'bound' and row.get('adapter_id') == adapter}
        if len(existing_clients) == 1:
            client = next(iter(existing_clients))
    if client not in CLIENTS:
        client, candidate_ref = choose_harness(call, agent_id=me['agent_id'], executor_id=executor_id,
            workspace_id=project['workspace_id'], client=client, candidate_ref=args.candidate_ref,
            interactive=interactive, read=read, write=write)
    else:
        candidate_ref = args.candidate_ref
    exact = dict(agent_id=args.agent, binding_id=args.binding_id, workspace_id=args.workspace_id)
    if saved:
        old = saved['selection']
        saved_exact = dict(agent_id=old.get('agent'), binding_id=saved.get('result', {}).get('binding', {}).get('binding_id'))
        if any(exact.get(key) not in (None, value) for key, value in saved_exact.items()):
            raise ConnectionError('PROFILE_CONFLICT', 'Exact connection selectors disagree with the saved legacy shortcut.')
        exact.update(saved_exact)
    action, connect_id, row = select_id(rows, harness=client, connect_id=args.connect_id,
        new_connection=args.new_connection, selectors=exact, interactive=interactive, read=read, write=write)
    if action == 'resume':
        if args.new_agent is not None:
            raise ConnectionError('CONNECTION_SELECTOR_CONFLICT', 'A new identity selector cannot resume an existing Harness ID.')
        reference = row['canonical_ref']
        effective = next(name for name, adapter in CLIENTS.items() if adapter == row['adapter_id'])
        selection = dict(agent=reference['agent_id'], client=effective, project=project['project'],
            label=project['label'], workspace_id=reference['workspace_id'], binding_id=reference['binding_id'],
            candidate_ref=args.candidate_ref, provider_home=args.provider_home, create_agent=False, display_name=None,
            public_connection=dict(version=1, connect_id=connect_id), quick_connect=_metadata(project, operation='reused'))
        return dict(action='resume', selection=selection, server_id=me['server_id'],
            reference={key: reference[key] for key in IDENTITY})
    # Legacy adoption is metadata-only, with exact binding/revision in its own
    # final review. Never create a new agent merely to assign a public name.
    legacy = None
    if saved:
        legacy = dict(saved['selection'], binding_id=exact['binding_id'])
    elif args.agent and args.binding_id:
        legacy = dict(agent=args.agent, binding_id=args.binding_id)
    elif project['workspace_id'] and not args.new_connection:
        catalog = merge_canonical_connections(call, local=ConnectionChoiceCatalog((), (), True),
            server_id=me['server_id'], project=project['project'], workspace_id=project['workspace_id'])
        if not catalog.complete:
            raise ConnectionError('CATALOG_UNCONFIRMED', 'The existing connection inventory is incomplete.')
        named = {r['canonical_ref']['binding_id'] for r in rows if r.get('canonical_ref')}
        candidates = [choice for choice in catalog.choices if choice.client == client and choice.binding_id not in named]
        if candidates:
            if not interactive:
                raise ConnectionError('CONNECTION_SELECTION_REQUIRED', 'Select an exact legacy connection before assigning its Harness ID.',
                    choices=[asdict(choice) for choice in candidates])
            write('Existing connections without a public Harness ID:')
            for index, choice in enumerate(candidates, 1):
                write(f'{index}. {choice.client} — existing connection')
            write('a. Add another connection\nc. Cancel')
            try:
                answer = read('Connection: ').strip().lower()
            except EOFError:
                answer = 'c'
            if answer.isdecimal() and 1 <= int(answer) <= len(candidates):
                chosen = candidates[int(answer) - 1]
                legacy = dict(agent=chosen.agent_id, binding_id=chosen.binding_id)
            elif answer != 'a':
                raise ConnectionError('CONNECT_CANCELLED', 'Connection selection cancelled.')
    if legacy:
        selection = dict(agent=legacy['agent'], client=client, project=project['project'], label=project['label'],
            workspace_id=project['workspace_id'], binding_id=legacy['binding_id'], candidate_ref=args.candidate_ref,
            provider_home=args.provider_home, create_agent=False, display_name=None,
            quick_connect=_metadata(project, operation='associated_existing'),
            public_connection=dict(version=1, connect_id=connect_id))
        return dict(action='associate', selection=selection, server_id=me['server_id'])
    requested_client = client
    client, candidate_ref = choose_harness(call, agent_id=me['agent_id'], executor_id=executor_id,
        workspace_id=project['workspace_id'], client=client, candidate_ref=candidate_ref,
        interactive=interactive, read=read, write=write)
    if client != requested_client:
        # The user explicitly chose an alternative. Resolve its existing IDs and
        # legacy bindings before proposing anything for the new family. Freeze
        # the already chosen project/name/root; do not run Git a second time.
        updated = copy(args)
        updated.client, updated.candidate_ref = client, candidate_ref
        seed = dict(name=project['label'], source=project['project_name_source'], status='saved',
            reason='saved_selection', cwd_resolution=project['cwd_resolution'], workspace_id=project['workspace_id'])
        return prepare(call, updated, root=project['project'], invocation_cwd=invocation_cwd,
            saved=saved, interactive=interactive, read=read, write=write, frozen_name=seed)
    slug = re.sub(r'[^a-z0-9]+', '-', project['label'].lower()).strip('-')[:40] or 'project'
    selection = dict(agent=args.agent or args.new_agent or slug + '-' + uuid.uuid4().hex[:12],
        client=client, project=project['project'], label=project['label'], workspace_id=project['workspace_id'],
        binding_id=None, candidate_ref=candidate_ref, provider_home=args.provider_home,
        create_agent=args.agent is None, display_name=args.name,
        quick_connect=_metadata(project, operation='created'),
        public_connection=dict(version=1, connect_id=connect_id,
            reservation_ref='pcr_' + uuid.uuid4().hex, project_revision=project['project_revision']))
    return dict(action='new', selection=selection, server_id=me['server_id'])


def prepare_remote(call, args, *, root, invocation_cwd, saved=None, interactive=False, read=input, write=print, frozen_name=None):
    """Resume an exact public remote binding; operator CWD grants no host root."""
    from .quick_connect_project import project_directory
    me = call('GET', PREFIX + '/connections/me')
    require_public_ids(call, me['server_id'])
    if saved and saved.get('selection', {}).get('quick_connect'):
        if saved.get('server_id') != me['server_id']:
            raise ConnectionError('PROFILE_CONFLICT', 'The retained remote connection belongs to another Server.')
        selection = dict(saved['selection'])
        public = selection.get('public_connection') or {}
        if (args.connect_id not in (None, public.get('connect_id')) or args.client not in (None, selection.get('client'))
                or args.workspace_id not in (None, selection.get('workspace_id'))
                or args.binding_id not in (None, selection.get('binding_id'))
                or args.agent not in (None, selection.get('agent'))
                or args.project_name not in (None, selection.get('label')) or args.new_agent is not None):
            raise ConnectionError('PROFILE_CONFLICT', 'The remote public connection selectors disagree with the retained shortcut.')
        return dict(action='retained', selection=selection, server_id=me['server_id'])
    if args.new_connection or args.new_agent or args.remote_draft:
        raise ConnectionError('REMOTE_ADDITION_REQUIRES_HOST', 'Add a remote public connection on its Connector execution host.')
    directory, _ = project_directory(call, me['server_id'])
    matches = [row for row in directory if (not args.workspace_id or row['workspace_id'] == args.workspace_id)
        and (not args.project_name or row['display_name'] == args.project_name)]
    if (not args.workspace_id and not args.project_name) or len(matches) != 1:
        raise ConnectionError('PROJECT_SELECTION_REQUIRED', 'Select one exact authorized remote project.', choices=list(directory))
    workspace = matches[0]
    rows = public_ids(call, server_id=me['server_id'], workspace_id=workspace['workspace_id'])
    client = args.client
    occupant = next((row for row in rows if row['connect_id'] == args.connect_id), None) if args.connect_id else None
    if client is None and occupant:
        client = next((name for name, adapter in CLIENTS.items() if adapter == occupant.get('adapter_id')), None)
    if client not in CLIENTS:
        raise ConnectionError('CLIENT_SELECTION_REQUIRED', 'Select the harness of an existing remote public connection.')
    action, name, row = select_id(rows, harness=client, connect_id=args.connect_id,
        selectors=dict(agent_id=args.agent, binding_id=args.binding_id),
        interactive=interactive, read=read, write=write)
    if action != 'resume':
        raise ConnectionError('REMOTE_ADDITION_REQUIRES_HOST', 'Configure a new remote public connection on its Connector host.')
    reference = row['canonical_ref']
    effective = next(name for name, adapter in CLIENTS.items() if adapter == row['adapter_id'])
    selection = dict(agent=reference['agent_id'], client=effective, project=root, label=workspace['display_name'],
        workspace_id=reference['workspace_id'], binding_id=reference['binding_id'], candidate_ref=args.candidate_ref,
        provider_home=args.provider_home, create_agent=False, display_name=None, operator_profile=args.operator_profile,
        public_connection=dict(version=1, connect_id=name), quick_connect=dict(version=1, operation='reused',
            project_name_source='existing_nexus', name_discovery=dict(status='not_needed', reason='existing_nexus'),
            cwd_resolution=dict(invocation_cwd=invocation_cwd, project_root=None, root_explicit=False, source='remote')))
    return dict(action='resume', selection=selection, server_id=me['server_id'], reference=reference)

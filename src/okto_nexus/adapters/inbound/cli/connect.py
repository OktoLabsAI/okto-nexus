"""Project setup from the terminal, with a retained review and canonical receipt."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import sys
import uuid

from ....application.terminal_connection import ConnectionError, TerminalConnection, RemoteTerminalConnection
from ....errors import OktoNexusError
from ...outbound.service_manager.context import atomic_json, read_json
from ...outbound.service_manager.locking import ExclusiveFileLock, LockBusy
from ...outbound.terminal_http import LocalOperatorHTTP
from .service import resolve_local_service
from . import connect_login


def project_profile(project, explicit_profile):
    project = str((project or Path.cwd()).expanduser().resolve(strict=True))
    if not Path(project).is_dir():
        raise ConnectionError('PROJECT_REQUIRED', 'Select an existing local project directory.')
    profile = explicit_profile or 'project-' + hashlib.sha256(project.encode('utf-8')).hexdigest()[:24]
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', profile):
        raise ConnectionError('PROFILE_INVALID', 'Use 1..80 letters, digits, hyphens or underscores for the profile name.')
    return project, profile


def saved_selection(saved, args, project):
    selection = dict(saved['selection'])
    if (getattr(args, 'connect_id', None) is not None
            and selection.get('public_connection', {}).get('connect_id') != args.connect_id
            or getattr(args, 'project_name', None) is not None and selection.get('label') != args.project_name):
        raise ConnectionError('PROFILE_CONFLICT', 'The explicit project name or Harness ID conflicts with this retained connection.')
    supplied = {key: getattr(args, key) for key in ('agent', 'client', 'workspace_id', 'binding_id', 'candidate_ref', 'provider_home')}
    if args.agent is not None and saved['state'] != 'done':
        supplied['create_agent'] = False
    if args.new_agent is not None:
        supplied.update(agent=args.new_agent, create_agent=True)
    if args.name is not None:
        supplied['display_name'] = args.name
    if args.project is not None or not args.profile:
        supplied['project'] = project
    if args.remote_draft is not None:
        from .remote_setup_io import read_draft
        draft = read_draft(args.remote_draft)
        if args.review_current and saved.get('kind') == 'remote_project_setup':
            if saved['state'] == 'review_submitted' and draft != selection.get('remote_draft'):
                raise ConnectionError('REVIEW_PENDING', 'Recover the pending review before changing its draft.')
            selection['remote_draft'] = draft
            from ....application.project_preset import CLIENTS
            selection['client'] = next((name for name, adapter in CLIENTS.items()
                if adapter == draft['installation']['adapter_id']), None)
            selection['candidate_ref'] = draft['installation']['candidate_ref']
        else:
            supplied['remote_draft'] = draft
    if any(value is not None and value != selection.get(key) for key, value in supplied.items()):
        raise ConnectionError('PROFILE_CONFLICT', 'Explicit choices conflict with the saved profile. Use its existing choices or a new named profile.')
    return selection


def _display(value, as_json):
    if as_json:
        from .quick_connect_outcome import public_wire
        value = public_wire(value)
        print(json.dumps(value, ensure_ascii=False))
        return
    from .quick_connect_outcome import display_public
    if display_public(value):
        return
    if value.get('profile') and not value.get('quick_connect'):
        print('Connection shortcut: ' + value['profile'])
    if value.get('canonical_metadata_revalidation_requested'):
        print('Canonical metadata revalidation was requested; existing revision metadata may change.')
    if value.get('state') == 'review' and value.get('kind') == 'remote_project_setup':
        from .remote_setup_io import display_review
        display_review(value)
    elif value.get('state') in ('awaiting_host', 'awaiting_finish', 'review_required') and value.get('setup_run_id'):
        print('Remote setup: ' + value['state'] + ' | Agent: ' + value['agent_id'])
        if value.get('handoff_path'):
            print('Host handoff (no key): ' + value['handoff_path'])
        if value['state'] == 'review_required':
            print('The approved effects changed. Use --review-current to inspect the affected review before continuing.')
        elif value['state'] == 'awaiting_finish':
            print('Operator decision recorded. Resume the original Connector request to complete its canonical Finish.')
        else:
            print('Resume Connector connect with --setup-receipt on the execution host, then return to this same profile.')
        if value.get('material_delivery') == 'delivered_once':
            print('Use the canonical agent key already received. This command does not issue it again.')
        elif value.get('material_status') == 'unavailable':
            print('Identity and workspace are committed, but this client did not confirm receiving the one-shot key.')
            print('The Server cannot recover its plaintext. Import a copy you retained, or inspect this partial setup; no rotation was performed.')
        print('No project task was submitted.')
    elif value.get('state') == 'review' and value.get('kind') == 'public_id_association':
        selection = value['selection']
        print(f"Project: {selection['label']} | Harness: {selection['client']}")
        print('ID do Harness (proposed): ' + selection['public_connection']['connect_id'])
        for effect in value['effects']:
            print('- ' + effect)
        print('Review revision: ' + value['review_revision'])
    elif value.get('state') == 'review':
        request = value['request']
        config = request['configuration']
        print(f"Agent: {request['agent_id']} | Harness: {config['adapter_id']}")
        if value.get('identity_creation'):
            identity = value['identity_creation']
            print(f"Create identity: {identity['display_name']} | Role: {identity['role']}")
            print('Coordination: visible collaborators, direct/channel messages, workspace handoffs, artifacts and events.')
            print('No broadcasts, channel creation, capability changes, experimental memory or global administration.')
            limits = identity['permissions']['limits']
            print(f"Communication limits: {limits['messages_per_minute']} messages/minute; {limits['max_recipients']} recipients.")
        print(f"Project: {config['workspace_root']}")
        print(f"Workspace: {request['workspace_id'] or 'create ' + config['workspace_label']}")
        if value['selection'].get('quick_connect'):
            quick = value['selection']['quick_connect']
            print('ID do Harness (proposed): ' + request['public_connection']['connect_id'])
            print('Project name source: ' + quick['project_name_source'])
            print('Invocation directory: ' + quick['cwd_resolution']['invocation_cwd'])
            print('Execution host: ' + request['executor_id'])
        print(f"Provider home: {config['provider_home'] or 'harness default'}")
        if value['version_check_required']:
            print('The selected executable will run its version check before the connection test.')
        for effect in value['effects']:
            print('- ' + effect)
        if value['selection'].get('login_start'):
            connect_login.display(value['selection']['login_start'])
        else:
            print('Startup: keep the current service mode. Optional user login startup: --start-at-login.')
        print('Review revision: ' + value['review_revision'])
    elif value.get('state') == 'login_start_review':
        print('Project configuration is already saved; review only the Server startup change.')
        connect_login.display(value['login_start'])
        print('Review revision: ' + value['review_revision'])
    elif value.get('state') == 'configured':
        print(f"Configuration saved: agent {value['agent_id']}, workspace {value['workspace_id']}, binding {value['binding_id']}.")
        print('Session readiness has not been checked. No project task was submitted.')
        if value.get('login_start'):
            current = value['login_start']['current_user_service']
            print('Current login startup: ' + ('enabled' if current['enabled'] else 'disabled')
                  if current else 'Current login startup integration is not confirmed by service status.')
    else:
        print(json.dumps(value, ensure_ascii=False, indent=2))


def run_connect(argv):
    from .quick_connect_customize import ReviewRestart
    invocation_cwd = frozen_name = None
    while True:
        try:
            return _run_connect_once(argv, invocation_cwd=invocation_cwd, frozen_name=frozen_name)
        except ReviewRestart as restart:
            argv, invocation_cwd, frozen_name = restart.argv, restart.invocation_cwd, restart.frozen_name


def _quick_entry_requested(args):
    # Public syntax opts in explicitly. Legacy selectors keep their old flow;
    # a retained Quick checkpoint is handled after the exact profile is read.
    if args.harness or args.project_name or args.connect_id:
        return True
    legacy = ('profile', 'project', 'client', 'agent', 'new_agent', 'name',
        'workspace_id', 'binding_id', 'candidate_ref', 'provider_home',
        'operator_profile', 'remote_draft', 'setup_receipt_output', 'approve')
    return not (any(getattr(args, key, None) is not None for key in legacy)
        or args.new_connection or args.review_current)


def _run_connect_once(argv, *, invocation_cwd=None, frozen_name=None):
    from .connect_arguments import parse_connect_args, parse_mode
    try:
        mode, remaining = parse_mode(argv)
        if mode == 'participant':
            from .participant import run_participant
            return run_participant(remaining)
        args, service_args = parse_connect_args(remaining)
    except SystemExit as error:
        if error.code and '--json' in argv:
            _display(dict(state='refused', code='INVALID_ARGUMENTS',
                message='Invalid connect arguments. Use connect --help.',
                effects_started=False, lifecycle_requested=False), True)
            return int(error.code)
        raise
    from .quick_connect_policy import entry_enabled
    enabled = entry_enabled()
    if not enabled and (args.harness or args.project_name or args.connect_id):
        _display(dict(state='refused', code='QUICK_CONNECT_DISABLED',
            message='Quick Connect entry is disabled; existing profiles remain available.',
            effects_started=False, lifecycle_requested=False), args.json)
        return 3
    if args.new_connection and not args.profile and (args.json or not sys.stdin.isatty()):
        _display(dict(state='selection_required', reason='new_connection_requires_profile',
            effects_started=False, lifecycle_requested=False, choices=[]), args.json)
        return 3
    guard = checkpoint = reservation = selected_choice = quick_prepared = quick_previous = None
    quick_operation = None
    quick_enabled = enabled and _quick_entry_requested(args)
    canonical_metadata = False
    try:
        from .terminal_target import resolve_terminal_target, terminal_target_selection
        invocation_cwd = invocation_cwd or str(Path.cwd())  # Capture once, including across customization.
        project, profile = project_profile(args.project or Path(invocation_cwd), args.profile)
        if args.new_connection:
            _, remote_operator = terminal_target_selection(service_args, profile, args.operator_profile)
            if remote_operator:
                raise ConnectionError('REMOTE_ADDITION_REQUIRES_HOST', 'Add a remote connection through its Connector host.')
        service = resolve_terminal_target(service_args, profile, args.operator_profile, resolve_local_service)
        if args.new_connection and hasattr(service, 'operator_profile'):
            raise ConnectionError('REMOTE_ADDITION_REQUIRES_HOST', 'Add a remote connection through its Connector host; this flag selects local managed setup only.')
        if (args.remote_draft or args.setup_receipt_output or args.review_current) and not hasattr(service, 'operator_profile'):
            raise ConnectionError('REMOTE_OPERATOR_REQUIRED', 'Remote host setup requires a saved human operator profile.')
        if hasattr(service, 'operator_profile') and args.start_at_login is not None:
            raise ConnectionError('REMOTE_STARTUP_NOT_LOCAL', 'Choose startup on the execution host using its Connector; this operator client cannot install a remote Server service.')
        directory = service.adapter.home / 'terminal/profiles'
        if not hasattr(service, 'operator_profile'):
            from .connection_reservation import _safe_paths
            _safe_paths(service.adapter.home, profile)
        target = directory / (profile + '.json')
        def save(value):
            nonlocal checkpoint
            atomic_json(target, value)
            checkpoint = deepcopy(value)
        prior = read_json(target) if target.exists() else None
        quick_enabled = quick_enabled or bool(args.profile and (prior or {}).get('selection', {}).get('quick_connect'))
        checkpoint = prior
        status = None
        if (args.profile and not args.plan and prior and prior.get('login_start_operation', {}).get('state') in ('pending', 'installed')):
            guard = ExclusiveFileLock(directory / (profile + '.guard'))
            guard.acquire()
            prior = read_json(target)
            saved_selection(prior, args, project)
            if args.start_at_login is False:
                raise ConnectionError('LOGIN_START_ALREADY_REVIEWED', 'Inspect the retained startup operation before changing its approved intent.')
            status = connect_login.resume(service, prior, save, timeout=min(30, args.timeout))
            if status and status['state'] == 'login_start_pending':
                _display(status, args.json)
                return 3
        status = status or (service.inspect() if args.plan else service.ensure_running(timeout=min(30, args.timeout)))
        if status['state'] != 'ready':
            _display({'state': 'service_not_ready', 'service': status}, args.json)
            return 3
        if quick_enabled:
            canonical_metadata = True
            from .quick_connect_selection import prepare
            call = service.operator_http if hasattr(service, 'operator_profile') else LocalOperatorHTTP(
                host=service.adapter.host, port=service.adapter.port)
            if hasattr(service, 'operator_profile'):
                from .quick_connect_selection import prepare_remote
                prepare_choice = prepare_remote
            else:
                prepare_choice = prepare
            own_saved = prior
            if not args.profile and prior and prior.get('state') in ('done', 'superseded'):
                own_saved = None  # The basic flow offers resume/add, not implicit profile priority.
            if args.new_connection and not args.profile:
                own_saved = None
                profile = 'connection-' + uuid.uuid4().hex[:24]
            if not hasattr(service, 'operator_profile') and not own_saved and (not prior or prior.get('state') not in ('done', 'superseded')):
                from .connection_reservation import read_reservation
                retained = read_reservation(service.adapter.home, profile)
                if retained and retained.get('selection', {}).get('quick_connect'):
                    own_saved = dict(state='reserved', server_id=retained['server_id'], selection=retained['selection'])
            quick_prepared = prepare_choice(call, args, root=project, invocation_cwd=invocation_cwd,
                saved=own_saved, interactive=sys.stdin.isatty() and not args.json, read=input, frozen_name=frozen_name)
            project = quick_prepared['selection']['project']
            if not args.profile and quick_prepared['action'] in ('resume', 'associate'):
                binding = quick_prepared['selection']['binding_id']
                prior_binding = (prior or {}).get('result', {}).get('binding', {}).get('binding_id')
                if prior_binding != binding:
                    key = [quick_prepared['server_id'], quick_prepared['selection']['agent'], binding, project]
                    profile = 'canonical-' + hashlib.sha256(json.dumps(key, separators=(',', ':')).encode()).hexdigest()[:24]
            if quick_prepared['action'] == 'new':
                if not args.profile and prior and prior.get('state') in ('done', 'superseded'):
                    profile = 'connection-' + uuid.uuid4().hex[:24]
                args.new_connection = True
            if quick_prepared['action'] == 'resume':
                args.client = quick_prepared['selection']['client']  # Explicit collision choice may use another harness.
            args.profile = profile
            target = directory / (profile + '.json')
            prior = read_json(target) if target.exists() else None
            checkpoint = prior
            quick_operation = 'reused' if prior and prior.get('state') == 'done' else None
        if not quick_enabled and not hasattr(service, 'operator_profile') and not args.profile:
            from .connection_choices import ConnectionChoiceScope, list_connection_choices, ConnectionChoiceCatalog, ChoiceIssue
            from .connection_picker import pick_connection, selection_required
            if args.new_connection and (args.json or not sys.stdin.isatty()):
                _display(selection_required(ConnectionChoiceCatalog((), (), True),
                    reason='new_connection_requires_profile', lifecycle_requested=not args.plan), args.json)
                return 3
            call = LocalOperatorHTTP(host=service.adapter.host, port=service.adapter.port)
            me = call('GET', '/api/v1/runtime-management/connections/me')
            if not status.get('instance_id'):
                catalog = ConnectionChoiceCatalog((), (ChoiceIssue(None, 'instance_unconfirmed'),), False)
            else:
                catalog = list_connection_choices(ConnectionChoiceScope(service.adapter.home,
                    Path(project), me['server_id'], instance_id=status['instance_id']))
                from .connection_reservation import pending_reservations
                pending = pending_reservations(service.adapter.home, project, me['server_id'])
                catalog = ConnectionChoiceCatalog(catalog.choices + pending.choices,
                    catalog.issues + pending.issues, catalog.complete and pending.complete)
                if catalog.complete:
                    from .canonical_connections import merge_canonical_connections
                    canonical_metadata = True
                    catalog = merge_canonical_connections(call, local=catalog, server_id=me['server_id'],
                        project=project, workspace_id=args.workspace_id)
            if not catalog.complete or (catalog.choices and (args.json or not sys.stdin.isatty()) and not args.new_connection):
                _display(selection_required(catalog, lifecycle_requested=not args.plan,
                    metadata_revalidation_requested=canonical_metadata), args.json)
                return 3
            action, selected_profile = ('add', None) if args.new_connection else (
                pick_connection(catalog, client=args.client, read=input) if sys.stdin.isatty() and not args.json else ('add', None))
            if action in ('cancel', 'unconfirmed'):
                _display(dict(state='canceled' if action == 'cancel' else 'selection_required',
                    effects_started=None if not args.plan or canonical_metadata else False,
                    lifecycle_requested=not args.plan, canonical_metadata_revalidation_requested=canonical_metadata), args.json)
                return 0 if action == 'cancel' else 3
            if action == 'resume':
                profile = selected_profile
                selected_choice = next(row for row in catalog.choices if row.profile == profile)
            elif catalog.choices or args.new_connection:
                profile = 'connection-' + uuid.uuid4().hex[:24]
                args.new_connection = True
            args.profile = profile
            target = directory / (profile + '.json')
            prior = read_json(target) if target.exists() else None
            checkpoint = prior
        if not hasattr(service, 'operator_profile'):
            from .connection_reservation import _safe_paths
            _safe_paths(service.adapter.home, profile)
        directory.mkdir(parents=True, exist_ok=True)
        if guard is None:
            guard = ExclusiveFileLock(directory / (profile + '.guard'))
            guard.acquire()
        saved = read_json(target) if target.exists() else None
        checkpoint = saved
        from .connection_reservation import read_reservation, reserve_connection
        reservation = read_reservation(service.adapter.home, profile) if not hasattr(service, 'operator_profile') else None
        if quick_prepared and quick_prepared['action'] == 'associate':
            quick_previous, saved, reservation = saved, None, None
        elif quick_prepared and quick_prepared['action'] == 'resume' and saved:
            binding = saved.get('result', {}).get('binding', {}).get('binding_id')
            prepared_selection = quick_prepared['selection']
            if binding != prepared_selection['binding_id'] or saved['selection']['agent'] != prepared_selection['agent']:
                raise ConnectionError('PROFILE_CONFLICT', 'The saved shortcut belongs to another connection.')
            saved = deepcopy(saved)
            saved['selection'].update(public_connection=prepared_selection['public_connection'],
                quick_connect=prepared_selection['quick_connect'])
        if selected_choice is not None and selected_choice.canonical_ref is not None and not saved:
            if reservation is not None:
                raise ConnectionError('PROFILE_CONFLICT', 'The canonical shortcut name is reserved by another local intent.')
            from .canonical_connections import associate_canonical
            call = LocalOperatorHTTP(host=service.adapter.host, port=service.adapter.port)
            facade = RemoteTerminalConnection if selected_choice.canonical_ref['execution_location'] == 'remote' else TerminalConnection
            flow = facade(call, lambda value: atomic_json(target, value))
            result = associate_canonical(flow, call, reference=selected_choice.canonical_ref, project=project)
            _display(dict(result, profile=profile, canonical_metadata_revalidation_requested=True,
                effects_started=None, lifecycle_requested=not args.plan), args.json)
            if not args.plan and not args.json and not args.no_chat and sys.stdin.isatty():
                from .work import interactive_work
                return interactive_work(service, profile, timeout=args.timeout)
            return 0
        if selected_choice is not None:
            retained = saved or reservation
            current_selection = retained.get('selection', {}) if retained else {}
            current_binding = (saved or {}).get('result', {}).get('binding', {}).get('binding_id') or current_selection.get('binding_id')
            if (not retained or current_selection.get('agent') != selected_choice.agent_id
                    or selected_choice.binding_id is not None and current_binding != selected_choice.binding_id
                    or selected_choice.client is not None and current_selection.get('client') != selected_choice.client):
                raise ConnectionError('PROFILE_DRIFT', 'The selected connection changed during the choice. Inspect it before continuing.')
        if args.new_connection and saved and not reservation:
            raise ConnectionError('PROFILE_CONFLICT', 'This profile belongs to another connection, not this addition intent.')
        if reservation:
            selection = saved_selection(saved or dict(selection=reservation['selection'], state='reserved'), args, project)
            current = LocalOperatorHTTP(host=service.adapter.host, port=service.adapter.port)(
                'GET', '/api/v1/runtime-management/connections/me')
            if current['server_id'] != reservation['server_id']:
                raise ConnectionError('SERVER_ID_MISMATCH', 'The addition intent belongs to another Server.')
            # Canonical review may enrich unspecified client/login/display
            # metadata. Its retained review is authoritative for those choices;
            # the original identity/project/setup intent must never change.
            if any(selection.get(key) != reservation['selection'].get(key)
                    for key in ('agent', 'project', 'create_agent', 'setup_intent_id')):
                raise ConnectionError('PROFILE_CONFLICT', 'The profile no longer matches its original addition intent.')
        elif saved:
            selection = saved_selection(saved, args, project)
        else:
            if (not quick_prepared and hasattr(service, 'operator_profile') and not args.remote_draft
                    and (not args.agent or not args.binding_id or args.new_agent)):
                raise ConnectionError('REMOTE_BINDING_REQUIRED', 'Select --agent and --binding-id for an existing approved remote connection. Connector onboarding remains on its execution host.')
            label = Path(project).name or 'Project'
            slug = re.sub(r'[^a-z0-9]+', '-', label.lower()).strip('-')[:40] or 'project'
            agent = args.agent or args.new_agent or slug + '-' + uuid.uuid4().hex[:12]
            selection = quick_prepared['selection'] if quick_prepared is not None else dict(agent=agent, client=args.client, project=project, label=Path(project).name or 'Project',
                workspace_id=args.workspace_id, binding_id=args.binding_id, candidate_ref=args.candidate_ref,
                provider_home=args.provider_home, create_agent=args.agent is None, display_name=args.name)
            if hasattr(service, 'operator_profile'):
                selection['operator_profile'] = service.operator_profile
                if args.remote_draft:
                    from .remote_setup_io import read_draft
                    selection['remote_draft'] = read_draft(args.remote_draft)
        if not quick_enabled and args.new_connection and reservation is None and not saved and not selection.get('workspace_id'):
            from .connection_choices import ConnectionChoiceScope, list_connection_choices
            from .connection_project import project_workspace_choices, pick_project_workspace
            call = LocalOperatorHTTP(host=service.adapter.host, port=service.adapter.port)
            current = call('GET', '/api/v1/runtime-management/connections/me')
            if not status.get('instance_id'):
                raise ConnectionError('PROJECT_SELECTION_UNCONFIRMED', 'The local service instance is not confirmed.')
            project_catalog = list_connection_choices(ConnectionChoiceScope(service.adapter.home,
                Path(project), current['server_id'], instance_id=status['instance_id']))
            workspaces = project_workspace_choices(call, project_catalog, project)
            if len(workspaces) > 1 and (args.json or not sys.stdin.isatty()):
                _display(dict(state='selection_required', reason='workspace_selection_required',
                    choices=[dict(workspace_id=row.workspace_id, label=row.label) for row in workspaces],
                    effects_started=None if not args.plan else False, lifecycle_requested=not args.plan), args.json)
                return 3
            if workspaces:
                workspace_id = pick_project_workspace(workspaces, read=input)
                if workspace_id is None:
                    _display(dict(state='canceled', effects_started=None if not args.plan else False,
                        lifecycle_requested=not args.plan), args.json)
                    return 0
                selection['workspace_id'] = workspace_id
        existing_login = connect_login.selected(saved) if saved else selection.get('login_start')
        if (reservation and (not saved or saved['state'] != 'done')
                and args.start_at_login is not None and args.start_at_login != bool(existing_login)):
            raise ConnectionError('PROFILE_CONFLICT', 'Recover the retained addition before changing its startup choice.')
        if args.start_at_login is False and existing_login:
            if saved['state'] == 'done' and saved.get('login_start_plan') and not saved.get('login_start_operation'):
                saved.pop('login_start_plan')
                save(saved)  # Decline an unapproved startup-only review.
            elif saved['state'] != 'review':
                raise ConnectionError('LOGIN_START_ALREADY_REVIEWED', 'The startup choice was already approved. Use service disable --user to change an installed integration explicitly.')
            else:
                selection.pop('login_start', None)
                saved = None
        elif args.start_at_login and not existing_login:
            if saved and saved['state'] not in ('review', 'done'):
                raise ConnectionError('LOGIN_START_SETUP_PENDING', 'Resume the approved setup before reviewing another startup effect.')
            plan = service.adapter.login_start_review()
            if saved and saved['state'] == 'done':
                saved['login_start_plan'] = plan
                save(saved)
            else:
                selection['login_start'] = plan
                saved = None
        if args.new_connection and reservation is None:
            current = LocalOperatorHTTP(host=service.adapter.host, port=service.adapter.port)(
                'GET', '/api/v1/runtime-management/connections/me')
            reservation = reserve_connection(service.adapter.home, profile, selection, current['server_id'])
            selection = reservation['selection']
        remote_setup = bool(selection.get('remote_draft'))
        handoff_path = None
        if remote_setup:
            from ....application.remote_terminal_setup import RemoteProjectSetup
            from .remote_setup_io import handoff_sink, material_sink
            output = args.setup_receipt_output or directory / (profile + '.setup-handoff.json')
            export, handoff_path = handoff_sink(output, selection['remote_draft']['setup_run_id'], as_json=args.json)
            flow = RemoteProjectSetup(service.operator_http, save, origin=service.operator_http.base,
                material_sink=material_sink(args.json), handoff_sink=export)
        elif args.review_current or args.setup_receipt_output:
            raise ConnectionError('REMOTE_DRAFT_REQUIRED', 'This profile does not contain a remote host setup draft.')
        elif hasattr(service, 'operator_profile') or saved and saved.get('remote_scope'):
            call = service.operator_http if hasattr(service, 'operator_profile') else LocalOperatorHTTP(
                host=service.adapter.host, port=service.adapter.port)
            flow = RemoteTerminalConnection(call, save)
        else:
            def save_local_setup(value):
                if reservation is not None and value.get('server_id') != reservation['server_id']:
                    raise ConnectionError('SERVER_ID_MISMATCH', 'The Server changed after the addition was reserved.')
                save(value)
            flow = TerminalConnection(LocalOperatorHTTP(host=service.adapter.host, port=service.adapter.port),
                                      save_local_setup)
        recovered_review = bool(remote_setup and saved and saved['state'] == 'review_submitted')
        if recovered_review:
            saved = flow.recover_review(saved)
        elif args.review_current:
            if not saved or saved['state'] == 'done':
                raise ConnectionError('REMOTE_REVIEW_UNAVAILABLE', 'Select a pending remote setup profile to refresh its review.')
            saved = flow.review(selection, previous=saved)
        elif not saved:
            try:
                saved = flow.review_public_association(selection, previous=quick_previous) if quick_prepared and quick_prepared['action'] == 'associate' else flow.review(selection)
            except ConnectionError as error:
                if (error.code != 'CLIENT_SELECTION_REQUIRED' or not error.choices
                        or args.json or not sys.stdin.isatty() or remote_setup
                        or hasattr(service, 'operator_profile')):
                    raise
                from .connection_picker import pick_harness
                client = pick_harness(error.choices, read=input)
                if client is None:
                    _display(dict(state='canceled', effects_started=None if not args.plan else False,
                        lifecycle_requested=not args.plan), args.json)
                    return 0
                selection['client'] = client
                saved = flow.review(selection)
            if saved['state'] == 'configured':
                saved = read_json(target)  # Reused bindings can still review local startup.
        if quick_enabled and saved['state'] == 'done':
            summary = flow.observe(saved)
            save(saved)  # Additive shortcut metadata, after exact canonical revalidation.
        if quick_enabled and saved['state'] == 'done' and not args.plan and not args.json and sys.stdin.isatty():
            public = summary.get('public_connection')
            if public:
                print(f"Retomar {selection['client']} — ID do Harness: {public['connect_id']} | Project: {selection['label']}")
                print('No model test, grant renewal or new session will be submitted.')
                try:
                    resume_answer = input('Confirm resume? [y/N] ').strip().lower()
                except EOFError:
                    resume_answer = ''
                if resume_answer != 'y':
                    _display(dict(state='canceled', lifecycle_requested=not args.plan,
                        canonical_metadata_revalidation_requested=True, effects_started=None), args.json)
                    return 0
        if saved['state'] == 'done':
            result = flow.observe(saved)
        elif args.plan or args.review_current or recovered_review:
            result = saved
        else:
            if connect_login.selected(saved):
                service.adapter.check_login_start_review(connect_login.selected(saved))
            approval = args.approve
            if saved['state'] == 'review' and not approval:
                from .quick_connect_outcome import annotate
                _display(annotate(saved, saved, profile=profile, home=service.adapter.home), args.json)
                if args.json or not sys.stdin.isatty():
                    return 3
                prompt = ('Apply this remote project review? [y/N] ' if remote_setup
                    else 'Associate this Harness ID with the existing connection? [y/N] ' if saved.get('kind') == 'public_id_association'
                    else 'Confirm this review, including the model connection test? [y/N] ')
                if quick_enabled:
                    prompt = prompt.replace('[y/N]', '[y/customize/cancel]')
                try:
                    answer = input(prompt).strip().lower()
                except EOFError:
                    answer = ''
                if quick_enabled and answer in ('customize', 'p', 'personalizar'):
                    from .quick_connect_customize import customize
                    restart = customize(args, service_args, saved, invocation_cwd=invocation_cwd, read=input)
                    if restart is None:
                        _display(dict(state='canceled', lifecycle_requested=not args.plan,
                            canonical_metadata_revalidation_requested=canonical_metadata, effects_started=None), args.json)
                        return 0
                    saved['state'] = 'superseded'
                    saved['superseded_by_profile'] = next(restart.argv[i + 1] for i, value in enumerate(restart.argv) if value == '--profile')
                    save(saved)
                    raise restart  # finally releases the old profile lock before another is acquired.
                if answer != 'y':
                    _display(dict(state='canceled', lifecycle_requested=not args.plan,
                        canonical_metadata_revalidation_requested=canonical_metadata, effects_started=None), args.json)
                    return 0
                approval = saved['review_revision']
            result = flow.apply(saved, approval=approval, timeout=args.timeout)
        if result['state'] == 'configured':
            saved = read_json(target)
            if connect_login.selected(saved):
                operation = saved.get('login_start_operation')
                if args.plan and not operation:
                    result = connect_login.separate_review(saved)
                elif not args.plan:
                    approval = args.approve
                    if not operation and not connect_login.initial_review_covers_login(saved) and not approval:
                        review = connect_login.separate_review(saved)
                        _display(review, args.json)
                        if args.json or not sys.stdin.isatty():
                            return 3
                        if input('Apply this login startup review? [y/N] ').strip().lower() != 'y':
                            return 0
                        approval = review['review_revision']
                    connect_login.authorize(saved, save, approval)
                    transition = connect_login.resume(service, saved, save, timeout=min(30, args.timeout))
                    if transition and transition['state'] == 'login_start_pending':
                        result = transition
                    else:
                        result['login_start'] = dict(operation_state=saved['login_start_operation']['state'],
                            current_user_service=(transition or status).get('user_service'))
        if handoff_path and result.get('handoff'):
            result['handoff_path'] = handoff_path
        if reservation is not None:
            result = dict(result, profile=profile)
        if quick_enabled:
            from .quick_connect_outcome import annotate
            result = annotate(result, saved, profile=profile, home=service.adapter.home,
                plan=args.plan, operation=quick_operation)
        _display(result, args.json)
        if result['state'] == 'configured' and not args.plan and not args.json and not args.no_chat and sys.stdin.isatty():
            from .work import interactive_work
            return interactive_work(service, profile, timeout=args.timeout)
        return 0 if result['state'] in ('configured', 'review', 'login_start_review') else 3
    except KeyboardInterrupt:
        return 130  # The service and any submitted test retain ownership.
    except (ConnectionError, OktoNexusError, LockBusy, OSError, ValueError, KeyError, TypeError) as error:
        if getattr(error, 'code', None) == 'CONNECT_CANCELLED':
            _display(dict(state='canceled', effects_started=None if not args.plan or canonical_metadata else False,
                lifecycle_requested=not args.plan, canonical_metadata_revalidation_requested=canonical_metadata), args.json)
            return 0
        pending_effect = (isinstance(checkpoint, dict) and checkpoint.get('kind') == 'remote_project_setup'
            and checkpoint.get('state') in ('bootstrap_submitted', 'decision_submitted'))
        possible_effect = bool(getattr(error, 'possible_effect', False) or pending_effect)
        partial = getattr(error, 'code', None) == 'CONFIGURED_SHORTCUT_PENDING'
        needs_selection = getattr(error, 'code', None) in ('CLIENT_SELECTION_REQUIRED', 'INSTALLATION_SELECTION_REQUIRED',
            'PROJECT_SELECTION_REQUIRED', 'HARNESS_ID_SELECTION_REQUIRED', 'CONNECTION_SELECTION_REQUIRED')
        value = {'state': 'configured_shortcut_pending' if partial else 'unconfirmed' if possible_effect else 'selection_required' if needs_selection else 'refused',
                  'code': getattr(error, 'code', 'PROFILE_BUSY' if isinstance(error, LockBusy) else 'CONFIG_ERROR'),
                  'message': getattr(error, 'message', getattr(error, 'action', 'Inspect the selected service and saved profile before continuing.')),
                  'possible_effect': possible_effect,
                  **({'effects_started': None, 'canonical_metadata_revalidation_requested': True} if canonical_metadata else {}),
                  **({'profile': profile} if reservation is not None else {})}
        if getattr(error, 'choices', None) is not None:
            value['choices'] = error.choices
        if partial and getattr(error, 'committed_public_connection', None):
            value['public_connection'] = error.committed_public_connection
        if quick_enabled and checkpoint and checkpoint.get('selection', {}).get('quick_connect'):
            from .quick_connect_outcome import annotate
            value = annotate(value, checkpoint, profile=profile, home=service.adapter.home, operation=quick_operation)
        _display(value, args.json)
        return 3
    finally:
        if guard is not None:
            guard.release()

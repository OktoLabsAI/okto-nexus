"""Project setup from the terminal, with a retained review and canonical receipt."""
import argparse
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
    supplied = {key: getattr(args, key) for key in ('agent', 'client', 'workspace_id', 'binding_id', 'candidate_ref', 'provider_home')}
    if args.agent is not None and saved['state'] != 'done':
        supplied['create_agent'] = False
    if args.new_agent is not None:
        supplied.update(agent=args.new_agent, create_agent=True)
    if args.name is not None:
        supplied['display_name'] = args.name
    if args.project is not None or not args.profile:
        supplied['project'] = project
    if any(value is not None and value != selection.get(key) for key, value in supplied.items()):
        raise ConnectionError('PROFILE_CONFLICT', 'Explicit choices conflict with the saved profile. Use its existing choices or a new named profile.')
    return selection


def _display(value, as_json):
    if as_json:
        print(json.dumps(value, ensure_ascii=False))
        return
    if value.get('state') == 'review':
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
    parser = argparse.ArgumentParser(prog='okto-nexus connect',
        description='Review and connect this local project using the canonical managed setup.')
    parser.add_argument('--profile', help='saved local project profile name')
    parser.add_argument('--operator-profile', help='use this saved human operator profile on a remote Server')
    startup = parser.add_mutually_exclusive_group()
    startup.add_argument('--start-at-login', dest='start_at_login', action='store_true', default=None,
        help='include user login startup and controlled supervisor transition in this review')
    startup.add_argument('--no-start-at-login', dest='start_at_login', action='store_false',
        help='omit login startup from an unapproved review; existing integrations are preserved')
    identity = parser.add_mutually_exclusive_group()
    identity.add_argument('--agent', help='reuse this authorized existing canonical agent ID')
    identity.add_argument('--new-agent', help='propose this unused ID instead of generating a new project identity ID')
    parser.add_argument('--name', help='display name for the new project identity')
    parser.add_argument('--client', choices=['codex', 'claude', 'pi'])
    parser.add_argument('--project', type=Path)
    parser.add_argument('--workspace-id')
    parser.add_argument('--binding-id')
    parser.add_argument('--candidate-ref')
    parser.add_argument('--provider-home')
    parser.add_argument('--plan', action='store_true', help='save/show the review without starting service, probes or model turns')
    parser.add_argument('--approve', help='apply the exact displayed review revision')
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--no-chat', action='store_true', help='return after connection setup, without entering interactive project work')
    parser.add_argument('--timeout', type=float, default=300, help='maximum test observation time; does not cancel execution')
    args, service_args = parser.parse_known_args(argv)
    if args.plan and args.approve:
        parser.error('--plan and --approve are mutually exclusive')
    if args.agent and args.name:
        parser.error('--name is for a new identity; existing names are preserved')
    if not 0 < args.timeout <= 300:
        parser.error('--timeout must be greater than 0 and at most 300 seconds')
    guard = None
    try:
        from .terminal_target import resolve_terminal_target
        project, profile = project_profile(args.project, args.profile)
        service = resolve_terminal_target(service_args, profile, args.operator_profile, resolve_local_service)
        if hasattr(service, 'operator_profile') and args.start_at_login:
            raise ConnectionError('REMOTE_STARTUP_NOT_LOCAL', 'Choose startup on the execution host using its Connector; this operator client cannot install a remote Server service.')
        directory = service.adapter.home / 'terminal/profiles'
        target = directory / (profile + '.json')
        save = lambda value: atomic_json(target, value)
        prior = read_json(target) if target.exists() else None
        status = None
        if (not args.plan and prior and prior.get('login_start_operation', {}).get('state') in ('pending', 'installed')):
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
        directory.mkdir(parents=True, exist_ok=True)
        if guard is None:
            guard = ExclusiveFileLock(directory / (profile + '.guard'))
            guard.acquire()
        saved = read_json(target) if target.exists() else None
        if saved:
            selection = saved_selection(saved, args, project)
        else:
            if hasattr(service, 'operator_profile') and (not args.agent or not args.binding_id or args.new_agent):
                raise ConnectionError('REMOTE_BINDING_REQUIRED', 'Select --agent and --binding-id for an existing approved remote connection. Connector onboarding remains on its execution host.')
            label = Path(project).name or 'Project'
            slug = re.sub(r'[^a-z0-9]+', '-', label.lower()).strip('-')[:40] or 'project'
            agent = args.agent or args.new_agent or slug + '-' + uuid.uuid4().hex[:12]
            selection = dict(agent=agent, client=args.client, project=project, label=Path(project).name or 'Project',
                workspace_id=args.workspace_id, binding_id=args.binding_id, candidate_ref=args.candidate_ref,
                provider_home=args.provider_home, create_agent=args.agent is None, display_name=args.name)
            if hasattr(service, 'operator_profile'):
                selection['operator_profile'] = service.operator_profile
        existing_login = connect_login.selected(saved) if saved else selection.get('login_start')
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
        if hasattr(service, 'operator_profile'):
            flow = RemoteTerminalConnection(service.operator_http, lambda value: atomic_json(target, value))
        else:
            flow = TerminalConnection(LocalOperatorHTTP(host=service.adapter.host, port=service.adapter.port),
                                      lambda value: atomic_json(target, value))
        if not saved:
            saved = flow.review(selection)
            if saved['state'] == 'configured':
                saved = read_json(target)  # Reused bindings can still review local startup.
        if saved['state'] == 'done':
            result = flow.observe(saved)
        elif args.plan:
            result = saved
        else:
            if connect_login.selected(saved):
                service.adapter.check_login_start_review(connect_login.selected(saved))
            approval = args.approve
            if saved['state'] == 'review' and not approval:
                _display(saved, args.json)
                if args.json or not sys.stdin.isatty():
                    return 3
                if input('Apply this review, including the model connection test? [y/N] ').strip().lower() != 'y':
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
        _display(result, args.json)
        if result['state'] == 'configured' and not args.plan and not args.json and not args.no_chat and sys.stdin.isatty():
            from .work import interactive_work
            return interactive_work(service, profile, timeout=args.timeout)
        return 0 if result['state'] in ('configured', 'review', 'login_start_review') else 3
    except KeyboardInterrupt:
        return 130  # The service and any submitted test retain ownership.
    except (ConnectionError, OktoNexusError, LockBusy, OSError, ValueError, KeyError, TypeError) as error:
        _display({'state': 'unconfirmed' if getattr(error, 'possible_effect', False) else 'refused',
                  'code': getattr(error, 'code', 'PROFILE_BUSY' if isinstance(error, LockBusy) else 'CONFIG_ERROR'),
                  'message': getattr(error, 'message', getattr(error, 'action', 'Inspect the selected service and saved profile before continuing.')),
                  'possible_effect': getattr(error, 'possible_effect', False)}, args.json)
        return 3
    finally:
        if guard is not None:
            guard.release()

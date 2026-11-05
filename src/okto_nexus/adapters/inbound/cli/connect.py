"""Project setup from the terminal, with a retained review and canonical receipt."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

from ....application.terminal_connection import ConnectionError, TerminalConnection
from ....errors import OktoNexusError
from ...outbound.service_manager.context import atomic_json, read_json
from ...outbound.service_manager.locking import ExclusiveFileLock, LockBusy
from ...outbound.terminal_http import LocalOperatorHTTP
from .service import resolve_local_service


def _display(value, as_json):
    if as_json:
        print(json.dumps(value, ensure_ascii=False))
        return
    if value.get('state') == 'review':
        request = value['request']
        config = request['configuration']
        print(f"Agent: {request['agent_id']} | Harness: {config['adapter_id']}")
        print(f"Project: {config['workspace_root']}")
        print(f"Workspace: {request['workspace_id'] or 'create ' + config['workspace_label']}")
        print(f"Provider home: {config['provider_home'] or 'harness default'}")
        if value['version_check_required']:
            print('The selected executable will run its version check before the connection test.')
        for effect in value['effects']:
            print('- ' + effect)
        print('Review revision: ' + value['review_revision'])
    elif value.get('state') == 'configured':
        print(f"Configuration saved: agent {value['agent_id']}, workspace {value['workspace_id']}, binding {value['binding_id']}.")
        print('Session readiness has not been checked. No project task was submitted.')
    else:
        print(json.dumps(value, ensure_ascii=False, indent=2))


def run_connect(argv):
    parser = argparse.ArgumentParser(prog='okto-nexus connect',
        description='Review and connect this local project using the canonical managed setup.')
    parser.add_argument('--profile', help='saved local project profile name')
    parser.add_argument('--agent', help='authorized existing canonical agent ID')
    parser.add_argument('--client', choices=['codex', 'claude', 'pi'])
    parser.add_argument('--project', type=Path)
    parser.add_argument('--workspace-id')
    parser.add_argument('--binding-id')
    parser.add_argument('--candidate-ref')
    parser.add_argument('--provider-home')
    parser.add_argument('--plan', action='store_true', help='save/show the review without starting service, probes or model turns')
    parser.add_argument('--approve', help='apply the exact displayed review revision')
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--timeout', type=float, default=300, help='maximum test observation time; does not cancel execution')
    args, service_args = parser.parse_known_args(argv)
    if args.plan and args.approve:
        parser.error('--plan and --approve are mutually exclusive')
    if not 0 < args.timeout <= 300:
        parser.error('--timeout must be greater than 0 and at most 300 seconds')
    guard = None
    try:
        service = resolve_local_service(service_args)
        status = service.inspect() if args.plan else service.ensure_running(timeout=min(30, args.timeout))
        if status['state'] != 'ready':
            _display({'state': 'service_not_ready', 'service': status}, args.json)
            return 3
        project = str((args.project or Path.cwd()).expanduser().resolve(strict=True))
        if not Path(project).is_dir():
            raise ConnectionError('PROJECT_REQUIRED', 'Select an existing local project directory.')
        profile = args.profile or 'project-' + hashlib.sha256(project.encode('utf-8')).hexdigest()[:24]
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', profile):
            raise ConnectionError('PROFILE_INVALID', 'Use 1..80 letters, digits, hyphens or underscores for the profile name.')
        directory = service.adapter.home / 'terminal/profiles'
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / (profile + '.json')
        guard = ExclusiveFileLock(directory / (profile + '.guard'))
        guard.acquire()
        saved = read_json(target) if target.exists() else None
        if saved:
            selection = saved['selection']
            supplied = {key: getattr(args, key) for key in ('agent', 'client', 'workspace_id', 'binding_id', 'candidate_ref', 'provider_home')}
            if args.project is not None or not args.profile:
                supplied['project'] = project
            if any(value is not None and value != selection.get(key) for key, value in supplied.items()):
                raise ConnectionError('PROFILE_CONFLICT', 'Explicit choices conflict with the saved profile. Use its existing choices or a new named profile.')
        else:
            agent = args.agent
            if not agent and sys.stdin.isatty() and not args.json:
                agent = input('Existing canonical agent ID: ').strip()
            if not agent:
                raise ConnectionError('AGENT_SELECTION_REQUIRED', 'Pass --agent for an authorized existing identity.')
            selection = dict(agent=agent, client=args.client, project=project, label=Path(project).name or 'Project',
                workspace_id=args.workspace_id, binding_id=args.binding_id, candidate_ref=args.candidate_ref,
                provider_home=args.provider_home)
        flow = TerminalConnection(LocalOperatorHTTP(host=service.adapter.host, port=service.adapter.port),
                                  lambda value: atomic_json(target, value))
        if not saved:
            saved = flow.review(selection)
            if saved['state'] == 'configured':
                _display(saved, args.json)
                return 0
        if saved['state'] == 'done':
            result = flow.observe(saved)
        elif args.plan:
            result = saved
        else:
            approval = args.approve
            if saved['state'] == 'review' and not approval:
                _display(saved, args.json)
                if args.json or not sys.stdin.isatty():
                    return 3
                if input('Apply this review, including the model connection test? [y/N] ').strip().lower() != 'y':
                    return 0
                approval = saved['review_revision']
            result = flow.apply(saved, approval=approval, timeout=args.timeout)
        _display(result, args.json)
        return 0 if result['state'] in ('configured', 'review') else 3
    except KeyboardInterrupt:
        return 130  # The service and any submitted test retain ownership.
    except (ConnectionError, OktoNexusError, LockBusy, OSError, ValueError, KeyError, TypeError) as error:
        _display({'state': 'unconfirmed' if getattr(error, 'possible_effect', False) else 'refused',
                  'code': getattr(error, 'code', 'PROFILE_BUSY' if isinstance(error, LockBusy) else 'CONFIG_ERROR'),
                  'message': getattr(error, 'message', 'Inspect the selected service and saved profile before continuing.'),
                  'possible_effect': getattr(error, 'possible_effect', False)}, args.json)
        return 3
    finally:
        if guard is not None:
            guard.release()

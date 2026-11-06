"""Review optional project preset evolution without resetting reconnect."""
import argparse
import json
from pathlib import Path
import sys

from ....application.terminal_connection import ConnectionError
from ....application.terminal_preset import TerminalPreset
from ....errors import OktoNexusError
from ...outbound.service_manager.context import atomic_json, read_json
from ...outbound.service_manager.locking import ExclusiveFileLock, LockBusy
from ...outbound.terminal_http import LocalOperatorHTTP
from .connect import project_profile
from .native_input import display_text
from .service import resolve_local_service
from .terminal_target import resolve_terminal_target


def display(value, as_json):
    if as_json:
        print(json.dumps(value, ensure_ascii=False))
    elif value.get('state') == 'review':
        review = value['preset_review']
        request = value['request']
        print('Agent: ' + display_text(request['agent_id']) + ' | Harness: ' +
            display_text(request['configuration']['adapter_id']))
        print('Connection: ' + display_text(request['binding_id']) + ' | Workspace: ' +
            display_text(request['workspace_id']))
        print('Project preset: ' + display_text(str(review['source_origin'])) + ' -> ' +
            display_text(str(review['target_origin'])))
        for row in review['changes']:
            print('Change ' + display_text(row['field']) + ': ' + display_text(json.dumps(row['before'])) +
                ' -> ' + display_text(json.dumps(row['after'])))
        for row in review['preserved']:
            print('Keep custom ' + display_text(row['field']) + ': ' + display_text(json.dumps(row['current'])))
        for effect in value['effects']:
            print('- ' + display_text(effect))
        authority = review['authority_changes']
        for row in authority['connections']:
            print('Affected connection: ' + display_text(row['alias'] or row['binding_id'] or row['endpoint_id']) +
                ' | workspace ' + display_text(row['workspace_label'] or row['workspace_id']))
        for grant_id in authority['revoked_grant_ids']:
            print('Revoke grant: ' + display_text(grant_id))
        for endpoint_id in authority['disabled_boot_endpoint_ids']:
            print('Disable boot approval: ' + display_text(endpoint_id))
        if review['new_authorization'] is not None:
            print('New grant actions: ' + ', '.join(review['actions']))
        print('Review revision: ' + value['review_revision'])
    else:
        print(display_text(json.dumps(value, ensure_ascii=False, indent=2)))


def run_preset(argv):
    parser = argparse.ArgumentParser(prog='okto-nexus preset',
        description='Review optional preset adoption/update for the existing project. Normal reconnect preserves settings.')
    parser.add_argument('--profile')
    parser.add_argument('--project', type=Path)
    parser.add_argument('--operator-profile')
    parser.add_argument('--plan', action='store_true', help='save/show the diff without starting services, testing or applying')
    parser.add_argument('--approve', help='apply exactly this saved review revision, including its listed effects')
    parser.add_argument('--refresh', action='store_true', help='replace an unapproved review with current evidence')
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--timeout', type=float, default=300)
    args, service_args = parser.parse_known_args(argv)
    if args.approve and (args.plan or args.refresh):
        parser.error('--approve cannot be combined with --plan or --refresh')
    if not 0 < args.timeout <= 300:
        parser.error('--timeout must be greater than 0 and at most 300 seconds')
    guard = None
    try:
        project, name = project_profile(args.project, args.profile)
        service = resolve_terminal_target(service_args, name, args.operator_profile, resolve_local_service)
        target = service.adapter.home / 'terminal/profiles' / (name + '.json')
        if not target.exists():
            raise ConnectionError('CONNECTION_REQUIRED', 'Connect this project before reviewing a preset update.')
        guard = ExclusiveFileLock(target.with_suffix('.guard'))
        guard.acquire()
        connection = read_json(target)
        if connection.get('format') != 1 or connection.get('state') != 'done':
            raise ConnectionError('CONNECTION_REQUIRED', 'Finish the existing connection before reviewing a preset update.')
        if (args.project is not None or not args.profile) and connection['selection']['project'] != project:
            raise ConnectionError('PROFILE_CONFLICT', 'This profile belongs to another project.')
        saved = connection.get('preset_evolution')
        pending = saved and saved['state'] not in ('review', 'done', 'refused')
        if args.refresh and pending:
            raise ConnectionError('UPDATE_PENDING', 'Recover the approved update before replacing its review.')
        acting = bool(args.approve or pending) and not args.plan
        status = service.ensure_running(timeout=min(30, args.timeout)) if acting else service.inspect()
        if status['state'] != 'ready':
            display(dict(state='service_not_ready', service=status), args.json)
            return 3
        def save(value):
            connection['preset_evolution'] = value
            atomic_json(target, connection)
        call = service.operator_http if hasattr(service, 'operator_http') else LocalOperatorHTTP(
            host=service.adapter.host, port=service.adapter.port)
        flow = TerminalPreset(call, save, connection)
        if not saved or saved['state'] == 'done' or args.refresh:
            saved = flow.review()
        if saved['state'] == 'up_to_date' or args.plan:
            display(saved, args.json)
            return 0
        approval = args.approve
        if saved['state'] == 'review' and not approval:
            display(saved, args.json)
            if args.json or not sys.stdin.isatty():
                return 3
            if input('Apply this preset review and all listed effects? [y/N] ').strip().lower() != 'y':
                return 0
            approval = saved['review_revision']
        result = flow.apply(saved, approval=approval, timeout=args.timeout)
        display(result, args.json)
        return 0 if result['state'] == 'preset_applied' else 3
    except KeyboardInterrupt:
        return 130
    except EOFError:
        return 0  # No approval was obtained from the interactive prompt.
    except (ConnectionError, OktoNexusError, LockBusy, OSError, ValueError, KeyError, TypeError) as error:
        display(dict(state='unconfirmed' if getattr(error, 'possible_effect', False) else 'refused',
            code=getattr(error, 'code', 'PROFILE_BUSY' if isinstance(error, LockBusy) else 'CONFIG_ERROR'),
            message=getattr(error, 'message', 'Inspect the saved project and update checkpoint before continuing.'),
            possible_effect=getattr(error, 'possible_effect', False)), args.json)
        return 3
    finally:
        if guard is not None:
            guard.release()

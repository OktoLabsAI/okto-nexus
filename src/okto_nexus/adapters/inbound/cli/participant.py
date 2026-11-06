"""Existing-identity participant init; no service or provider process starts."""
import argparse
import getpass
import json
import os
from pathlib import Path
import sys
import warnings

from ....application.terminal_connection import ConnectionError
from ....application.terminal_participant import TerminalParticipant
from ....config import load_config
from ...outbound.operator_client import server_origin
from ...outbound.participant_client import participant_key
from ...outbound.participant_files import private_directory
from ...outbound.service_manager.context import atomic_json, read_json
from ...outbound.service_manager.locking import ExclusiveFileLock
from .connect import project_profile
from .native_input import display_text


def _key(args, flow, saved):
    if args.key_stdin:
        return participant_key(sys.stdin.read(55).removesuffix('\n').removesuffix('\r'))
    if args.key_env:
        return participant_key(os.environ.get(args.key_env))
    if saved and saved['state'] != 'review':
        return flow.key(saved, None)
    if sys.stdin.isatty():
        # getpass normally falls back to echoing input on an unsuitable TTY.
        # A participant key must never take that fallback.
        with warnings.catch_warnings():
            warnings.simplefilter('error', getpass.GetPassWarning)
            try:
                return participant_key(getpass.getpass('Existing participant key (hidden): '))
            except getpass.GetPassWarning:
                pass
    raise ConnectionError('PARTICIPANT_KEY_REQUIRED', 'Use a hidden terminal prompt, --key-stdin, or --key-env NAME with an existing agent key. Missing identities must be created explicitly by an operator.')


def _selection(args, project, saved):
    if saved:
        selection = saved['review']['selection']
        supplied = {name: getattr(args, name) for name in
            ('server', 'agent', 'workspace_id', 'client', 'client_version', 'entry_name')}
        if args.server:
            supplied['server'] = server_origin(args.server)
        if args.project is not None or not args.profile:
            supplied['project'] = project
        if args.config_file:
            supplied['config_file'] = str(args.config_file.expanduser().resolve())
        if any(value is not None and value != selection.get(name) for name, value in supplied.items()):
            raise ConnectionError('PROFILE_CONFLICT', 'Explicit choices conflict with this participant profile. Reuse its choices or choose a new named profile.')
        return selection
    if not all((args.server, args.agent, args.workspace_id, args.client)):
        raise ConnectionError('PARTICIPANT_SELECTION_REQUIRED', 'Select --server, --agent, --workspace-id and --client for the first review. The identity and workspace must already exist.')
    if args.client == 'generic' and (args.config_file or args.client_version):
        raise ConnectionError('MANUAL_CONFIGURATION_REQUIRED', 'Generic export has no installed file or qualified client version.')
    target = args.config_file or (Path(project) / ('.mcp.json' if args.client == 'claude' else '.codex/config.toml'))
    return dict(server=server_origin(args.server), agent=args.agent, workspace_id=args.workspace_id,
        client=args.client, client_version=args.client_version, entry_name=args.entry_name or 'nexus',
        project=project, selected_file=bool(args.config_file),
        config_file=str(target.expanduser().absolute()) if args.client != 'generic' else None)


def _display(value, as_json):
    if as_json:
        print(json.dumps(value, ensure_ascii=False))
        return
    if value.get('code'):
        print(display_text(value['code'] + ': ' + value['message']))
        return
    context = value['context']
    for line in (f"Participant: {context['agent_id']} | Workspace: {context['workspace']['workspace_id']}",
                 f"Server: {value['origin']} | State: {value['state']}",
                 'Delivery: ' + context['delivery'],
                 'File: ' + (value['file']['path'] if value['file'] else 'manual export'),
                 'Proposed entry: ' + json.dumps({value['entry_name']: value['entry']}, ensure_ascii=False)):
        print(display_text(line))
    for effect in value['effects']:
        print('- ' + display_text(effect))
    if value['origin'].startswith('http:'):
        print('Transport: loopback HTTP is plaintext on this host.')
    print('Review revision: ' + value['review_revision'])
    print(value['next_action'])


def run_participant(argv):
    parser = argparse.ArgumentParser(prog='okto-nexus init', description=__doc__)
    parser.add_argument('--mode', choices=('participant',), default='participant')
    parser.add_argument('--home', type=Path)
    parser.add_argument('--profile')
    parser.add_argument('--server', help='explicit HTTPS origin; HTTP is limited to loopback')
    parser.add_argument('--agent', help='existing canonical participant identity; no automatic creation')
    parser.add_argument('--workspace-id')
    parser.add_argument('--client', choices=('claude', 'codex', 'generic'))
    parser.add_argument('--client-version', help='observed client version, if known; does not qualify readiness')
    parser.add_argument('--project', type=Path)
    parser.add_argument('--config-file', type=Path, help='explicit local client configuration; defaults to project scope')
    parser.add_argument('--entry-name')
    parser.add_argument('--plan', action='store_true')
    parser.add_argument('--approve', help='exact review revision; resumes the same setup after a partial effect')
    parser.add_argument('--refresh', action='store_true', help='replace only an unapproved review after inspecting drift')
    parser.add_argument('--json', action='store_true')
    keys = parser.add_mutually_exclusive_group()
    keys.add_argument('--key-stdin', action='store_true')
    keys.add_argument('--key-env', metavar='NAME', help='read only this explicitly authorized environment variable')
    args = parser.parse_args(argv)
    if args.approve and (args.plan or args.refresh):
        parser.error('--approve cannot be combined with --plan or --refresh')
    guard = None
    try:
        project, profile = project_profile(args.project, args.profile)
        home = (args.home or load_config(os.environ, []).home_dir).expanduser().resolve()
        directory = home / 'terminal/participants'
        private_directory(directory)
        target = directory / (profile + '.json')
        if target.is_symlink() or getattr(target, 'is_junction', lambda: False)():
            raise ConnectionError('PROFILE_PATH_UNSAFE', 'Use a regular participant profile file.')
        guard = ExclusiveFileLock(directory / (profile + '.guard'))
        guard.acquire()
        flow = TerminalParticipant(home, profile, lambda value: atomic_json(target, value))
        saved = read_json(target) if target.exists() else None
        if saved:
            flow.validate(saved)
        selection = _selection(args, project, saved)
        if args.refresh and saved and saved['state'] != 'review':
            raise ConnectionError('SETUP_ALREADY_APPROVED', 'This setup may have local effects. Resume its retained checkpoints before starting another review.')
        if args.approve and not saved:
            raise ConnectionError('REVIEW_REQUIRED', 'Create a participant review first with --plan.')
        # A saved review can be displayed without reacquiring a secret or making HTTP calls.
        key = None
        if not saved or args.refresh or args.approve or not args.plan:
            key = _key(args, flow, saved)
        if not saved or args.refresh:
            saved = flow.review(selection, key)
        if args.plan:
            _display(flow.result(saved), args.json)
            return 0
        approval = args.approve
        if saved['state'] != 'review' and approval is None:
            approval = saved['review_revision']
        if approval is None:
            _display(flow.result(saved), args.json)
            if args.json or not sys.stdin.isatty():
                return 0
            if input('Apply this review to the OS vault and selected client file? [y/N] ').strip().lower() not in ('y', 'yes'):
                return 0
            approval = saved['review_revision']
        _display(flow.apply(saved, key, approval), args.json)
        return 0
    except (KeyboardInterrupt, EOFError):
        return 130
    except Exception as error:
        # Vault/ACL extensions have platform-specific exception classes. Keep
        # their raw diagnostics (which may include sensitive input) off stdout.
        _display(dict(state='unconfirmed', code=getattr(error, 'code', 'PARTICIPANT_SETUP_UNCONFIRMED'),
            message=error.message if isinstance(error, ConnectionError) else
            'Inspect the retained participant setup and selected file before retrying. Existing Server identities and runtime configuration are preserved.'), args.json)
        return 3
    finally:
        if guard is not None:
            guard.release()

"""Launch an external participant client with protected credential delivery."""
import argparse
import json
import os
from pathlib import Path
import sys

from ....application.participant_launch import ParticipantLaunch
from ....application.terminal_connection import ConnectionError
from ....config import load_config
from ...outbound.participant_files import _check_private
from ...outbound.service_manager.context import atomic_json, read_json
from ...outbound.service_manager.locking import ExclusiveFileLock
from .connect import project_profile
from .native_input import display_text


def _display(value, as_json):
    if as_json:
        print(json.dumps(value, ensure_ascii=False))
    elif value.get('code'):
        print(display_text(value['code'] + ': ' + value['message']))
    else:
        review = value['review']
        process = review['process']
        for line in (f"Participant launch: {review['client']} | State: {value['state']}",
                'Server: ' + review['origin'], 'Client: ' + process['executable'],
                'Project: ' + process['cwd'], 'Configuration: ' + process['config_file'],
                'Arguments: ' + json.dumps(process['arguments']),
                'Credential reference: ' + review['credential_reference']):
            print(display_text(line))
        for effect in review['effects']:
            print('- ' + display_text(effect))
        if review['previous'] and review['previous']['state'] in ('starting', 'started'):
            print('The previous launch is uncertain and may still be running; another launch can overlap it.')
        print('Review revision: ' + value['review_revision'])
        print(value['next_action'])


def run_participant_launch(argv):
    parser = argparse.ArgumentParser(prog='okto-nexus participant', description=__doc__)
    parser.add_argument('action', choices=('launch',))
    parser.add_argument('--home', type=Path)
    parser.add_argument('--profile')
    parser.add_argument('--project', type=Path)
    parser.add_argument('--executable', type=Path, help='selected native Claude/Codex executable, never a shell command')
    parser.add_argument('--plan', action='store_true')
    parser.add_argument('--approve', help='exact launch review revision; replay only reports the retained attempt')
    parser.add_argument('--new', action='store_true', help='review a new launch, acknowledging possible overlap with an uncertain previous process')
    parser.add_argument('--json', action='store_true', help='JSON review/receipt; the launched foreground client owns the terminal')
    args = parser.parse_args(argv)
    if args.approve and (args.plan or args.new):
        parser.error('--approve cannot be combined with --plan or --new')
    guard = None
    try:
        project, profile = project_profile(args.project, args.profile)
        home = (args.home or load_config(os.environ, []).home_dir).expanduser().resolve()
        directory = home / 'terminal/participants'
        setup_path, launch_path = directory / (profile + '.json'), directory / (profile + '.launch.json')
        if not setup_path.exists():
            raise ConnectionError('PARTICIPANT_PROFILE_ABSENT', 'Complete init --mode participant for this profile first.')
        for path in (directory, setup_path, launch_path):
            if path.is_symlink() or getattr(path, 'is_junction', lambda: False)():
                raise ConnectionError('PROFILE_PATH_UNSAFE', 'Use regular private participant profile files.')
        _check_private(directory)
        guard = ExclusiveFileLock(directory / (profile + '.guard'))
        guard.acquire()
        saved = read_json(setup_path)
        flow = ParticipantLaunch(home, profile, lambda value: atomic_json(launch_path, value))
        review, _ = flow._setup(saved)
        if (args.project is not None or not args.profile) and review['selection']['project'] != project:
            raise ConnectionError('PROFILE_CONFLICT', 'This participant profile selects another project.')
        intent = read_json(launch_path) if launch_path.exists() else None
        if intent:
            flow.validate(intent, saved)
            if args.executable and not args.new and str(args.executable.expanduser().resolve()) != intent['review']['process']['executable']:
                raise ConnectionError('PROFILE_CONFLICT', 'Use --new to review a different client executable.')
        if args.approve and not intent:
            raise ConnectionError('REVIEW_REQUIRED', 'Create the launch review with --plan first.')
        if not intent or args.new:
            executable = args.executable or (intent['review']['process']['executable'] if intent else None)
            intent = flow.review(saved, executable, environment=os.environ, previous=intent)
        if args.plan:
            _display(flow.result(intent), args.json)
            return 0
        approval = args.approve
        if intent['state'] != 'review' and approval is None:
            _display(flow.result(intent), args.json)
            return 0
        if approval is None:
            _display(flow.result(intent), args.json)
            if args.json or not sys.stdin.isatty():
                return 0
            if input('Launch this client in the current terminal? [y/N] ').strip().lower() not in ('y', 'yes'):
                return 0
            approval = intent['review_revision']
        value = flow.apply(intent, saved, approval, environment=os.environ)
        _display(value, args.json)
        return 0 if value.get('exit_code') in (None, 0) else 3
    except (KeyboardInterrupt, EOFError):
        return 130
    except Exception as error:
        _display(dict(state='unconfirmed', code=error.code if isinstance(error, ConnectionError) else 'PARTICIPANT_LAUNCH_UNCONFIRMED',
            message=error.message if isinstance(error, ConnectionError) else
            'Inspect the retained launch intent. The client may still be running; retry never automatically launches a second process.'), args.json)
        return 3
    finally:
        if guard is not None:
            guard.release()

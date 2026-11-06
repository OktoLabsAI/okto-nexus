"""Review and resume removal of a participant's own local configuration and key."""
import argparse
import json
import os
from pathlib import Path
import sys

from ....application.participant_removal import ParticipantRemoval
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
        print(display_text(f"Participant removal: {value['profile']} | State: {value['state']} | Stage: {value['stage']}"))
        print(display_text(f"Agent: {review['agent_id']} | Server: {review['origin']}"))
        if review['file']:
            print(display_text('File: ' + review['file']['path'] + ' | Entry: ' + review['entry_name']))
            print('Changed fields: ' + ', '.join(review['file']['changed_fields']))
        for effect in review['effects']:
            print('- ' + display_text(effect))
        print('Review revision: ' + value['review_revision'])
        print(value['next_action'])


def run_participant_remove(argv):
    parser = argparse.ArgumentParser(prog='okto-nexus participant remove', description=__doc__)
    parser.add_argument('--home', type=Path)
    parser.add_argument('--profile')
    parser.add_argument('--project', type=Path)
    parser.add_argument('--plan', action='store_true')
    parser.add_argument('--approve', help='exact removal review revision')
    parser.add_argument('--refresh', action='store_true', help='replace only an unapproved removal review')
    parser.add_argument('--keep-config', action='store_true', help='explicitly leave all client files untouched; retire the profile and remove only its vault entry')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args(argv)
    if args.approve and (args.plan or args.refresh):
        parser.error('--approve cannot be combined with --plan or --refresh')
    guard = None
    try:
        project, profile = project_profile(args.project, args.profile)
        home = (args.home or load_config(os.environ, []).home_dir).expanduser().resolve()
        directory = home / 'terminal/participants'
        target = directory / (profile + '.json')
        if not target.exists():
            raise ConnectionError('PARTICIPANT_PROFILE_ABSENT', 'No participant setup exists for this selection; no files were created.')
        for path in (directory, target):
            if path.is_symlink() or getattr(path, 'is_junction', lambda: False)():
                raise ConnectionError('PROFILE_PATH_UNSAFE', 'Use regular private participant profile files.')
        _check_private(directory)
        guard = ExclusiveFileLock(directory / (profile + '.guard'))
        guard.acquire()
        saved = read_json(target)
        flow = ParticipantRemoval(home, profile, lambda value: atomic_json(target, value))
        setup, _ = flow.setup.validate(saved)
        if (args.project is not None or not args.profile) and setup['selection']['project'] != project:
            raise ConnectionError('PROFILE_CONFLICT', 'This participant profile selects another project.')
        removal = saved.get('removal')
        if args.approve and not removal:
            raise ConnectionError('REVIEW_REQUIRED', 'Create a local removal review with --plan first.')
        if args.keep_config and removal and not args.refresh and not removal['review']['keep_config']:
            raise ConnectionError('PROFILE_CONFLICT', 'Refresh an unapproved removal review to change the file choice.')
        if not removal or args.refresh:
            saved = flow.review(saved, keep_config=args.keep_config)
            removal = saved['removal']
        if args.plan:
            _display(flow.result(saved), args.json)
            return 0
        approval = args.approve
        if approval is None and removal['stage'] != 'review':
            approval = removal['review_revision']
        if approval is None:
            _display(flow.result(saved), args.json)
            if args.json or not sys.stdin.isatty():
                return 0
            if input('Remove this local setup as reviewed? [y/N] ').strip().lower() not in ('y', 'yes'):
                return 0
            approval = removal['review_revision']
        _display(flow.apply(saved, approval), args.json)
        return 0
    except (KeyboardInterrupt, EOFError):
        return 130
    except Exception as error:
        _display(dict(state='unconfirmed', code=error.code if isinstance(error, ConnectionError) else 'PARTICIPANT_REMOVAL_UNCONFIRMED',
            message=error.message if isinstance(error, ConnectionError) else
            'Preserve the retained removal intent and inspect the client file or protected vault. No Server identity was deleted.'), args.json)
        return 3
    finally:
        if guard is not None:
            guard.release()

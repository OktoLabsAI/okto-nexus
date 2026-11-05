"""Human operator login stays on the operator's client and protected OS vault."""
import argparse
import getpass
import json
import os
from pathlib import Path
import sys

from ....application.terminal_connection import ConnectionError
from ....config import load_config
from ...outbound.operator_client import OperatorProfile
from ...outbound.service_manager.locking import ExclusiveFileLock, LockBusy


def run_operator(argv):
    if argv and argv[0] == 'approval':
        from .operator_approval import run_operator_approval
        return run_operator_approval(argv[1:])
    parser = argparse.ArgumentParser(prog='okto-nexus operator')
    parser.epilog = 'Review Connector requests: okto-nexus operator approval APPROVAL_ID --profile NAME'
    parser.add_argument('action', choices=('login', 'status', 'logout'))
    parser.add_argument('--profile', required=True)
    parser.add_argument('--home', type=Path)
    parser.add_argument('--server', help='HTTPS origin; HTTP allowed only for loopback')
    parser.add_argument('--username')
    parser.add_argument('--password-stdin', action='store_true')
    args = parser.parse_args(argv)
    if args.action == 'login' and (not args.server or not args.username):
        parser.error('login requires --server and --username')
    if args.action != 'login' and (args.server or args.username or args.password_stdin):
        parser.error('login options are not accepted for status or logout')
    guard = None
    try:
        profile = OperatorProfile(args.home or load_config(os.environ, []).home_dir, args.profile)
        if args.action != 'status':
            profile.path.parent.mkdir(parents=True, exist_ok=True)
            guard = ExclusiveFileLock(profile.path.with_suffix('.guard'))
            guard.acquire()
        if args.action == 'login':
            if args.password_stdin:
                password = sys.stdin.read(1026).removesuffix('\n').removesuffix('\r')
            elif sys.stdin.isatty():
                password = getpass.getpass('Operator password: ')
            else:
                raise ConnectionError('PASSWORD_REQUIRED', 'Use --password-stdin or a hidden interactive prompt.')
            if not 1 <= len(password) <= 1024:
                raise ConnectionError('PASSWORD_INVALID', 'The password input has invalid length.')
            result = profile.login(args.server, args.username, password)
        elif args.action == 'status':
            client = profile.client()
            me = client.verify()
            result = dict(state='authenticated', profile=args.profile, origin=client.base, server_id=me['server_id'])
        else:
            metadata = profile.read()
            client = profile.client()
            revoked = False
            try:
                client('POST', '/api/v1/operator-auth/logout')
                revoked = True
            except ConnectionError:
                pass
            profile.secret('remove', metadata['origin'])
            result = dict(state='signed_out_locally', profile=args.profile, remote_revocation='confirmed' if revoked else 'unconfirmed')
        print(json.dumps(result, ensure_ascii=False))
        return 3 if result.get('remote_revocation') == 'unconfirmed' else 0
    except (EOFError, KeyboardInterrupt):
        return 130
    except (ConnectionError, OSError, ValueError, KeyError, TypeError, LockBusy) as error:
        print(json.dumps(dict(state='unconfirmed', code=getattr(error, 'code', 'OPERATOR_PROFILE_UNAVAILABLE'),
            message=getattr(error, 'message', 'Inspect the selected operator profile and protected OS vault.'))))
        return 3
    finally:
        if guard is not None:
            guard.release()

"""Explicit service diagnostics. Status never starts or cancels anything."""
from __future__ import annotations

import argparse
import json
import os

from ....config import load_config
from ....errors import OktoNexusError
from ...outbound.service_manager.inspection import inspect_local_server
from .serve import _split_serve_args


def run_service(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog='okto-nexus service',
        description='Inspect the configured local Server without starting it or any harness.')
    parser.add_argument('action', choices=['status'])
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--timeout', type=float, default=2.0,
                        help='readiness observation timeout in seconds (0 < timeout <= 30)')
    args, remaining = parser.parse_known_args(argv)
    if not 0 < args.timeout <= 30:
        parser.error('--timeout must be greater than 0 and at most 30 seconds')
    try:
        port, host, _, _, rest = _split_serve_args(remaining, os.environ)
        config = load_config(os.environ, rest)
        result = inspect_local_server(home=config.home_dir, database=config.db_path,
                                      host=host, port=port, timeout=args.timeout)
    except (OktoNexusError, OSError, ValueError) as error:
        result = {'state': 'failed', 'reason': getattr(error, 'code', 'CONFIG_ERROR'),
                  'next_action': 'Review the selected local instance configuration.'}
        if args.json:
            print(json.dumps(result))
        else:
            print(f"Service inspection failed: {result['reason']}. {result['next_action']}")
        return 2
    if args.json:
        print(json.dumps(result))
    else:
        print(f"Server: {result['state']} ({result['instance_id']})")
        print(f"Installed: {result['installed_version']}; active: {result['active_version'] or 'unconfirmed'}")
        if result.get('reason'):
            print(result['reason'])
        if result.get('next_action'):
            print(result['next_action'])
    return 0 if result['state'] in {'ready', 'stopped'} else 3

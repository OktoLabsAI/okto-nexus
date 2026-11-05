"""Explicit service diagnostics. Status never starts or cancels anything."""
from __future__ import annotations

import argparse
import json
import os
import time

from ....application.service_lifecycle import ServiceLifecycle
from ....bootstrap.local_discovery import split_discovery_args
from ....config import load_config
from ....errors import OktoNexusError
from ...outbound.service_manager.context import CONTEXT_NAME, execution_context, read_json, validate_context
from ...outbound.service_manager.local import LocalServerLifecycle
from .serve import _split_serve_args


def run_service(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog='okto-nexus service',
        description='Inspect or explicitly start the configured local Server.')
    parser.add_argument('action', choices=['status', 'start', 'stop', 'restart'])
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--timeout', type=float, default=None,
                        help='observation timeout in seconds; timeout never kills the service')
    args, remaining = parser.parse_known_args(argv)
    timeout = args.timeout if args.timeout is not None else (2.0 if args.action == 'status' else 30.0)
    if not 0 < timeout <= 300:
        parser.error('--timeout must be greater than 0 and at most 300 seconds')
    try:
        port, host, project_root, log_level, rest = _split_serve_args(remaining, os.environ)
        discovery, rest = split_discovery_args(rest)
        config = load_config(os.environ, rest)
        saved = config.home_dir.resolve() / CONTEXT_NAME
        environment = os.environ
        if saved.exists():
            previous = validate_context(read_json(saved))
            environment = previous['environment']
            port, host, project_root, log_level, rest = _split_serve_args(
                previous['arguments'] + remaining, environment)
            discovery, rest = split_discovery_args(rest)
            config = load_config(environment, rest)
        context = execution_context(config, host=host, port=port, project_root=project_root,
                                    log_level=log_level, discovery=discovery, env=environment)
        adapter = LocalServerLifecycle(home=config.home_dir, database=config.db_path,
                                       host=host, port=port, context=context)
        service = ServiceLifecycle(adapter, monotonic=time.monotonic, sleep=time.sleep)
        action = service.inspect if args.action == 'status' else getattr(service, args.action)
        result = action(timeout=timeout)
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
    success = (result['state'] == 'ready' if args.action in {'start', 'restart'} else
               result['state'] in {'ready', 'stopped'} if args.action == 'status' else
               result['state'] == 'stopped' and result.get('shutdown_outcome') != 'unconfirmed')
    return 0 if success else 3

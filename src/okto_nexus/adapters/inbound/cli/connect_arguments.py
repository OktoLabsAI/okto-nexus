"""Pure connect grammar. Service, directory and credential discovery happen later.

All options keep their original arity before argparse sees the two positionals.
SystemExit is argparse's existing help/error contract; callers own JSON output.
"""
import argparse
from pathlib import Path

from .... import config
from ....application.project_preset import CLIENTS
from ....domain.quick_connect import normalize_connect_id
from ....errors import OktoNexusError
from .serve import _split_serve_args


_SERVE = frozenset(('--port', '--host', '--project-root', '--log-level'))
_DISCOVERY = frozenset(('--harness-root', '--pi-install-root', '--pi-node'))
_VALUES = frozenset(('--profile', '--operator-profile', '--remote-draft', '--setup-receipt-output',
    '--agent', '--new-agent', '--name', '--client', '--project', '--workspace-id', '--binding-id',
    '--candidate-ref', '--provider-home', '--approve', '--timeout', '--id'))
_SWITCHES = frozenset(('--new-connection', '--review-current', '--start-at-login', '--no-start-at-login',
    '--plan', '--json', '--no-chat'))


def _parser():
    parser = argparse.ArgumentParser(prog='okto-nexus connect', allow_abbrev=False,
        description='Review and connect this project using the canonical managed setup.')
    parser.add_argument('harness', nargs='?', help='public harness token (' + ', '.join(CLIENTS) + ')')
    parser.add_argument('project_name', nargs='?', help='logical project name; never a directory path')
    parser.add_argument('--id', dest='connect_id', metavar='HARNESS_ID', help='ID do Harness (Harness ID) in this project')
    parser.add_argument('--profile', help='technical saved local profile; retained for scripts and recovery')
    parser.add_argument('--new-connection', action='store_true', help='explicitly add another connection')
    parser.add_argument('--operator-profile', help='saved human operator profile on a remote Server')
    parser.add_argument('--remote-draft', type=Path, help='remote host draft exported by Connector')
    parser.add_argument('--setup-receipt-output', type=Path, help='export the public remote handoff')
    parser.add_argument('--review-current', action='store_true')
    startup = parser.add_mutually_exclusive_group()
    startup.add_argument('--start-at-login', dest='start_at_login', action='store_true', default=None)
    startup.add_argument('--no-start-at-login', dest='start_at_login', action='store_false')
    identity = parser.add_mutually_exclusive_group()
    identity.add_argument('--agent', help='existing canonical agent ID')
    identity.add_argument('--new-agent', help='proposed unused canonical identity ID')
    parser.add_argument('--name', help='display name of the new identity')
    parser.add_argument('--client', help='legacy harness selector; tokens resolve after parsing')
    parser.add_argument('--project', type=Path, help='physical directory, independently of project name')
    parser.add_argument('--workspace-id')
    parser.add_argument('--binding-id')
    parser.add_argument('--candidate-ref')
    parser.add_argument('--provider-home')
    parser.add_argument('--plan', action='store_true', help='review without service, Git, probes or model turns')
    parser.add_argument('--approve', help='apply the exact displayed review revision')
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--no-chat', action='store_true')
    parser.add_argument('--timeout', type=float, default=300)
    return parser


def parse_mode(argv):
    """Extract mode without importing participant execution or consuming its flags.

    Unknown participant options remain for its own parser to reject. This guard
    identifies the new positional grammar, not participant configuration values.
    """
    parser = argparse.ArgumentParser(prog='okto-nexus connect', add_help=False, allow_abbrev=False)
    parser.add_argument('--mode', choices=('managed', 'participant'), default='managed')
    args, remaining = parser.parse_known_args(list(argv))
    if args.mode == 'participant':
        index = 0
        # Existing no-value options cannot consume a following new positional.
        switches = _SWITCHES | {'--refresh', '--key-stdin', '--help', '-h'}
        while index < len(remaining):
            token = remaining[index]
            flag, separator, _ = token.partition('=')
            if flag == '--id' or not token.startswith('-') or token == '--':
                parser.error('QUICK_CONNECT_MODE_UNSUPPORTED: use the legacy participant options without Quick Connect positionals or --id')
            index += 1
            if separator or flag in switches:
                continue
            # Leave unknown-option validation to the real participant parser;
            # its argument is not a Quick Connect positional by inference.
            if index < len(remaining) and not remaining[index].startswith('-'):
                index += 1
    return args.mode, remaining


def _config_flags():
    return {entry[1] for fields in (config._PATH_FIELDS, config._INT_FIELDS, config._ENUM_FIELDS,
        config._FLOAT_FIELDS, config._STRING_FIELDS, config._BOOL_FIELDS) for entry in fields.values()}


def _split_options(argv, parser):
    own, service = [], []
    service_flags = _config_flags() | _SERVE | _DISCOVERY
    index = 0
    while index < len(argv):
        token = argv[index]
        if token == '--':
            own.extend(argv[index:])
            break
        flag, separator, _ = token.partition('=')
        if not token.startswith('-'):
            own.append(token)
            index += 1
            continue
        if flag not in _VALUES | _SWITCHES | service_flags:
            parser.error('unrecognized argument: ' + flag)
        destination = service if flag in service_flags else own
        destination.append(token)
        index += 1
        if flag in _SWITCHES or separator:
            continue
        if index >= len(argv) or argv[index].startswith('--'):
            parser.error('argument ' + flag + ': expected one argument')
        destination.append(argv[index])
        index += 1
    return own, service


def _validate_discovery(argv, parser):
    """Structural validation only; canonical discovery later checks real paths."""
    rest, roots, unique = [], set(), set()
    index = 0
    while index < len(argv):
        token = argv[index]
        flag, separator, inline = token.partition('=')
        index += 1
        if flag not in _DISCOVERY:
            rest.append(token)
            continue
        raw = inline if separator else argv[index]
        if not separator:
            index += 1
        if not raw or not Path(raw).is_absolute():
            parser.error('discovery paths must be absolute local paths')
        if flag == '--harness-root':
            roots.add(Path(raw))
            if len(roots) > 32:
                parser.error('at most 32 discovery roots are allowed')
        elif flag in unique:
            parser.error('a discovery option was repeated: ' + flag)
        else:
            unique.add(flag)
    if ('--pi-install-root' in unique) != ('--pi-node' in unique):
        parser.error('Pi discovery requires both --pi-install-root and --pi-node')
    return rest


def parse_connect_args(argv):
    """Return managed argparse values and the original validated service argv."""
    argv = list(argv)
    parser = _parser()
    if '-h' in argv or '--help' in argv:
        parser.parse_args(['--help'])
    mode, remaining = parse_mode(argv)
    if mode != 'managed':
        parser.error('QUICK_CONNECT_MODE_UNSUPPORTED: dispatch legacy participant mode before managed parsing')
    own, service = _split_options(remaining, parser)
    args = parser.parse_intermixed_args(own)
    if args.harness is not None:
        args.harness = args.harness.lower()
    if args.client is not None:
        args.client = args.client.lower()
    if args.harness is not None and args.client is not None and args.harness != args.client:
        parser.error('ARGUMENT_CONFLICT: positional harness and --client disagree')
    args.client = args.harness if args.harness is not None else args.client
    if args.connect_id is not None:
        try:
            args.connect_id = normalize_connect_id(args.connect_id)
        except ValueError as error:
            parser.error(str(error))
    if args.plan and args.approve:
        parser.error('--plan and --approve are mutually exclusive')
    if args.review_current and args.approve:
        parser.error('--review-current requires a later approval of its new revision')
    if args.agent and args.name:
        parser.error('--name is for a new identity; existing names are preserved')
    if not 0 < args.timeout <= 300:
        parser.error('--timeout must be greater than 0 and at most 300 seconds')
    rest = _validate_discovery(service, parser)
    try:
        _, _, _, _, rest = _split_serve_args(rest, env={})
        config._parse_cli(rest)
    except OktoNexusError:
        parser.error('invalid service configuration arguments')
    return args, service

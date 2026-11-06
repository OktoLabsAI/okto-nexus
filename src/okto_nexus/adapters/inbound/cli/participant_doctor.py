"""Participant diagnostics with explicit credential/environment/MCP checks."""
import argparse
import os
from pathlib import Path

from ....application.participant_diagnostics import ParticipantDiagnostics, inspect_participant
from ....application.terminal_connection import ConnectionError
from ....config import load_config
from ...outbound.participant_files import _check_private
from ...outbound.service_manager.context import read_json
from .connect import project_profile
from .doctor import _finish


def run_participant_doctor(argv):
    parser = argparse.ArgumentParser(prog='okto-nexus doctor --mode participant', description=__doc__)
    parser.add_argument('--profile')
    parser.add_argument('--project', type=Path)
    parser.add_argument('--home', type=Path)
    parser.add_argument('--check-server', action='store_true', help='read the existing protected credential and authenticate an explicit GET')
    parser.add_argument('--check-mcp', action='store_true', help='also initialize MCP and list tools; no tools, agent sessions or model calls')
    parser.add_argument('--check-environment', action='store_true', help='inspect this process\'s named credential reference; with --check-server use it instead of the vault')
    parser.add_argument('--timeout', type=float, default=10)
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args(argv)
    if not 0 < args.timeout <= 30:
        parser.error('--timeout must be greater than zero and at most 30 seconds per active stage')
    report = ParticipantDiagnostics(args.profile)
    try:
        project, name = project_profile(args.project, args.profile)
        report.profile = name
        home = (args.home or load_config(os.environ, []).home_dir).expanduser().resolve()
        target = home / 'terminal/participants' / (name + '.json')
        if not target.exists():
            report.set('participant_profile', 'UNKNOWN', 'PROFILE_ABSENT',
                'No saved participant profile exists for this selection.',
                'Use init --mode participant to review setup. Doctor creates no files.')
        else:
            if target.is_symlink() or target.parent.is_symlink() or getattr(target.parent, 'is_junction', lambda: False)():
                raise ConnectionError('PROFILE_PATH_UNSAFE', 'Select a regular private participant profile.')
            _check_private(target.parent)
            saved = read_json(target)
            if (args.project is not None or not args.profile) and saved['review']['selection']['project'] != project:
                raise ConnectionError('PROFILE_CONFLICT', 'This profile selects another project.')
            inspect_participant(report, home, saved, check_server=args.check_server,
                check_mcp=args.check_mcp, check_environment=args.check_environment,
                environment=os.environ, timeout=args.timeout)
    except KeyboardInterrupt:
        return 130
    except Exception as error:
        report.error('participant_profile', error)
    return _finish(report, args.json)

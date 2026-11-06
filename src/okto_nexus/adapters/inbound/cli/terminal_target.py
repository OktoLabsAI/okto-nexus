"""Resolve remote operator topology before any local lifecycle operation."""
import argparse
import os
from pathlib import Path
from types import SimpleNamespace

from ....application.terminal_connection import ConnectionError
from ....config import load_config
from ...outbound.operator_client import OperatorProfile
from ...outbound.service_manager.context import read_json


class RemoteTarget:
    def __init__(self, home, name):
        self.adapter = SimpleNamespace(home=home)
        self.operator_http = OperatorProfile(home, name).client()
        self.operator_profile = name

    def inspect(self):
        me = self.operator_http.verify()
        return dict(state='ready', topology='remote_operator', server_id=me['server_id'],
                    origin=self.operator_http.base, local_service='not_applicable')

    def ensure_running(self, **kwargs):
        return self.inspect()  # Remote unavailability never starts a local component.


def terminal_target_selection(service_args, profile, operator_profile):
    """Read topology before opening a vault, HTTP client or local lifecycle."""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--home', type=Path)
    args, remaining = parser.parse_known_args(service_args)
    home = (args.home or load_config(os.environ, []).home_dir).expanduser().resolve()
    path = home / 'terminal/profiles' / (profile + '.json')
    saved = read_json(path) if path.exists() else None
    previous = saved.get('selection', {}).get('operator_profile') if saved else None
    if saved and operator_profile is not None and operator_profile != previous:
        raise ConnectionError('PROFILE_CONFLICT', 'The project profile belongs to another operator topology. Choose a new project profile.')
    selected = operator_profile or previous
    if selected and remaining:
        raise ConnectionError('REMOTE_OPTIONS_INVALID', 'Local service options cannot configure a remote Server. Use its saved operator profile.')
    return home, selected


def resolve_terminal_target(service_args, profile, operator_profile, local_resolver):
    home, selected = terminal_target_selection(service_args, profile, operator_profile)
    if selected:
        return RemoteTarget(home, selected)
    return local_resolver(service_args)

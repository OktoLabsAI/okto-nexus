"""Short local reservation before canonical setup; no second setup authority."""
from copy import deepcopy
import re
import uuid
import os

from ....application.terminal_connection import ConnectionError
from ...outbound.service_manager.context import atomic_json, read_json
from ...outbound.service_manager.locking import ExclusiveFileLock


def _safe_paths(home, profile=None):
    from .connection_choices import _directory
    if profile is not None and (not isinstance(profile, str)
            or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', profile)):
        raise ConnectionError('PROFILE_INVALID', 'Select a simple local profile name, never a path.')
    # Validate every potentially redirected parent before mkdir, lock or read.
    _directory(home / 'terminal')
    _directory(home / 'terminal/profiles')
    _directory(home / 'terminal/connection-intents')


def pending_reservations(home, project, server_id):
    """Find additions interrupted before review, without creating the store."""
    from .connection_choices import ConnectionChoice, ChoiceIssue, ConnectionChoiceCatalog, _read, _directory, MAX_PROFILES
    choices, issues = [], []
    directory = home / 'terminal/connection-intents'
    try:
        _safe_paths(home)
        _directory(directory)
        with os.scandir(directory) as entries:
            for index, entry in enumerate(entries):
                if index >= MAX_PROFILES:
                    issues.append(ChoiceIssue(None, 'reservation_limit'))
                    break
                if not entry.name.endswith('.json'):
                    continue
                name = entry.name[:-5]
                if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', name):
                    issues.append(ChoiceIssue(None, 'reservation_invalid'))
                    continue
                try:
                    value = _read(home / 'terminal/connection-intents' / entry.name)
                    if value.get('server_id') != server_id:
                        continue
                    reservation = read_reservation(home, name)
                    selection = reservation['selection']
                    if selection.get('project') != project:
                        continue
                    if (home / 'terminal/profiles' / entry.name).exists():
                        continue
                    choices.append(ConnectionChoice(name, selection['agent'], selection.get('client'),
                        selection.get('binding_id'), selection.get('workspace_id'), 'reserved',
                        True, False, False, False, False, False))
                except (ConnectionError, OSError, ValueError, KeyError, TypeError, RecursionError):
                    issues.append(ChoiceIssue(name, 'reservation_unconfirmed'))
    except FileNotFoundError:
        pass
    except (OSError, ValueError):
        issues.append(ChoiceIssue(None, 'reservation_unavailable'))
    return ConnectionChoiceCatalog(tuple(choices), tuple(issues), not issues)


def read_reservation(home, profile):
    _safe_paths(home, profile)
    path = home / 'terminal/connection-intents' / (profile + '.json')
    if path.is_symlink():
        raise ConnectionError('PROFILE_CONFLICT', 'The addition checkpoint must be a regular local document.')
    if not path.exists():
        return None
    value = read_json(path)
    if (value.get('format') != 1 or value.get('kind') != 'new_connection'
            or not isinstance(value.get('selection'), dict)
            or not re.fullmatch(r'connect_[a-f0-9]{32}', value.get('client_intent_id', ''))
            or value['selection'].get('setup_intent_id') != value['client_intent_id']
            or not isinstance(value.get('server_id'), str) or not value['server_id']):
        raise ConnectionError('PROFILE_CONFLICT', 'The retained addition intent is invalid; preserve it for inspection.')
    return value


def reserve_connection(home, profile, selection, server_id):
    """Caller owns PROFILE.guard; catalog exclusion is short, never interactive."""
    _safe_paths(home, profile)
    directory = home / 'terminal/connection-intents'
    directory.mkdir(parents=True, exist_ok=True)
    guard = ExclusiveFileLock(directory / 'catalog.guard')
    guard.acquire()
    try:
        previous = read_reservation(home, profile)
        if previous:
            expected = dict(selection)
            expected.setdefault('setup_intent_id', previous['client_intent_id'])
            if previous['server_id'] != server_id or previous['selection'] != expected:
                raise ConnectionError('PROFILE_CONFLICT', 'This profile reserves another addition intent.')
            return previous
        if (home / 'terminal/profiles' / (profile + '.json')).exists():
            raise ConnectionError('PROFILE_CONFLICT', 'This profile already belongs to a connection; choose another profile for addition.')
        selection = deepcopy(selection)
        intent_id = 'connect_' + uuid.uuid4().hex
        selection['setup_intent_id'] = intent_id
        value = dict(format=1, kind='new_connection', server_id=server_id,
            client_intent_id=intent_id, selection=selection)
        atomic_json(directory / (profile + '.json'), value)
        return value
    finally:
        guard.release()

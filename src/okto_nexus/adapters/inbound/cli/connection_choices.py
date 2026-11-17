"""Bounded, passive discovery of terminal shortcuts, never execution authority.

The caller selects a destination before discovery. Legacy local shortcuts do not
record the human or service instance: their home is a namespace, not proof of
either identity. Every returned choice requires canonical revalidation.
"""
from dataclasses import dataclass
import os
from pathlib import Path
import re

from ....domain.server_origin import normalize_server_origin
from ...outbound.service_manager.context import read_json

MAX_PROFILES = 256
MAX_DOCUMENT_BYTES = 131072
_NAME = re.compile(r'[A-Za-z0-9_-]{1,80}')


@dataclass(frozen=True)
class ConnectionChoiceScope:
    home: Path
    project: Path
    server_id: str
    instance_id: str | None = None
    operator_profile: str | None = None
    origin: str | None = None
    username: str | None = None


@dataclass(frozen=True)
class ConnectionChoice:
    profile: str
    agent_id: str
    client: str | None
    binding_id: str | None
    workspace_id: str | None
    setup_state: str
    setup_pending: bool
    startup_pending: bool
    work_pending: bool
    control_pending: bool
    authorization_pending: bool
    decision_pending: bool
    # No readiness/grant claim can be established by local JSON.
    requires_canonical_revalidation: bool = True
    canonical_ref: dict | None = None
    binding_ref: dict | None = None


@dataclass(frozen=True)
class ChoiceIssue:
    profile: str | None
    reason: str


@dataclass(frozen=True)
class ConnectionChoiceCatalog:
    choices: tuple[ConnectionChoice, ...]
    issues: tuple[ChoiceIssue, ...]
    complete: bool


def _text(value, *, optional=False):
    if optional and value is None:
        return None
    if not isinstance(value, str) or not value or len(value) > 4096 or any(ord(c) < 32 for c in value):
        raise ValueError('Invalid shortcut metadata')
    return value


def _read(path):
    # Do not follow a shortcut outside the explicitly selected store. read_json
    # also bounds the actual read if an atomic replacement races this stat.
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_DOCUMENT_BYTES:
        raise ValueError('Invalid shortcut document')
    return read_json(path)


def _directory(path):
    if path.is_symlink() or path.exists() and not path.is_dir():
        raise ValueError('Invalid shortcut directory')


def _pending(document, key):
    slot = document.get(key)
    if slot is None:
        return False
    if key == 'decision':
        # TerminalWork retains immutable decision metadata without a local
        # delivery state. Only its canonical receipt can settle that outcome.
        if (not isinstance(slot, dict) or not isinstance(slot.get('approval_key'), dict)
                or not slot['approval_key'].get('canonical_request_id')):
            raise ValueError('Invalid decision checkpoint')
        _text(slot.get('client_intent_id'))
        return True
    if not isinstance(slot, dict) or not isinstance(slot.get('state'), str):
        raise ValueError('Invalid work checkpoint')
    # Unknown future stages remain pending, rather than authorizing a new send.
    return slot['state'] not in {'admitted', 'blocked', 'done', 'decided', 'issued'}


def list_connection_choices(scope: ConnectionChoiceScope) -> ConnectionChoiceCatalog:
    """Read only the chosen home; no mkdir, lock, vault, HTTP or lifecycle call.

    Incomplete catalogs must not be interpreted as an empty installation. The
    instance_id is a caller-selected fence for subsequent canonical validation;
    legacy profiles cannot prove it. Remote human metadata must match exactly.
    """
    home = Path(scope.home).expanduser().resolve()
    project = str(Path(scope.project).expanduser().resolve())
    _text(scope.server_id)
    if not Path(scope.project).expanduser().is_absolute():
        raise ValueError('Select an absolute project directory')
    if scope.operator_profile is None:
        _text(scope.instance_id)
        if scope.origin is not None or scope.username is not None:
            raise ValueError('Local scope cannot select a remote operator')
    else:
        if not _NAME.fullmatch(scope.operator_profile) or scope.instance_id is not None:
            raise ValueError('Select one operator topology')
        _text(scope.username)
        if normalize_server_origin(scope.origin) != scope.origin:
            raise ValueError('Select a normalized origin')
    profiles, work = home / 'terminal/profiles', home / 'terminal/work'
    try:
        _directory(home / 'terminal')
        _directory(profiles)
        _directory(work)
        if scope.operator_profile is not None:
            _directory(home / 'terminal/operators')
            operator = _read(home / 'terminal/operators' / (scope.operator_profile + '.json'))
            if (operator.get('format') != 1 or operator.get('server_id') != scope.server_id
                    or operator.get('origin') != scope.origin or operator.get('username') != scope.username):
                raise ValueError('Operator metadata changed')
    except (OSError, ValueError, TypeError, RecursionError):
        return ConnectionChoiceCatalog((), (ChoiceIssue(None, 'scope_unconfirmed'),), False)
    choices, issues = [], []
    try:
        with os.scandir(profiles) as entries:
            for index, entry in enumerate(entries):
                if index >= MAX_PROFILES:
                    issues.append(ChoiceIssue(None, 'catalog_limit'))
                    break
                if not entry.name.endswith('.json'):
                    continue
                name = entry.name[:-5]
                if not _NAME.fullmatch(name):
                    issues.append(ChoiceIssue(None, 'profile_invalid'))
                    continue
                try:
                    saved = _read(Path(entry.path))
                    selection = saved.get('selection')
                    if saved.get('format') != 1 or not isinstance(selection, dict):
                        raise ValueError('Invalid profile')
                    # Never open another topology's operator metadata or work.
                    if (saved.get('server_id') != scope.server_id
                            or selection.get('operator_profile') != scope.operator_profile):
                        continue
                    saved_project = _text(selection.get('project'))
                    if not Path(saved_project).is_absolute():
                        raise ValueError('Invalid project')
                    if str(Path(saved_project).resolve()) != project:
                        continue
                    state = _text(saved.get('state'))
                    agent = _text(selection.get('agent'))
                    client = _text(selection.get('client'), optional=True)
                    result = saved.get('result', {})
                    if not isinstance(result, dict):
                        raise ValueError('Invalid receipt')
                    binding = result.get('binding', {})
                    if not isinstance(binding, dict):
                        raise ValueError('Invalid binding')
                    binding_id = _text(binding.get('binding_id') or selection.get('binding_id'), optional=True)
                    workspace = _text(binding.get('workspace_id') or selection.get('workspace_id'), optional=True)
                    identity_fields = ('server_id', 'executor_id', 'binding_id', 'endpoint_id',
                        'agent_id', 'workspace_id', 'workspace_binding_id')
                    binding_ref = {key: binding[key] for key in identity_fields} if all(
                        isinstance(binding.get(key), str) and binding[key] for key in identity_fields) else None
                    checkpoint_path = work / (name + '.json')
                    checkpoint = _read(checkpoint_path) if checkpoint_path.exists() or checkpoint_path.is_symlink() else {}
                    if checkpoint and checkpoint.get('format') != 1:
                        raise ValueError('Invalid checkpoint')
                    checkpoint_scope = checkpoint.get('scope')
                    if checkpoint_scope is not None:
                        if not isinstance(checkpoint_scope, dict) or any(
                            checkpoint_scope.get(key) != value for key, value in (
                                ('server_id', scope.server_id), ('agent_id', agent), ('binding_id', binding_id))):
                            raise ValueError('Work checkpoint scope changed')
                    choices.append(ConnectionChoice(name, agent, client, binding_id, workspace,
                        state, state != 'done', _pending(saved, 'login_start_operation'),
                        _pending(checkpoint, 'work'), _pending(checkpoint, 'control'),
                        _pending(checkpoint, 'authorization'), _pending(checkpoint, 'decision'), binding_ref=binding_ref))
                except (OSError, ValueError, KeyError, TypeError, RecursionError):
                    issues.append(ChoiceIssue(name, 'checkpoint_unconfirmed'))
    except FileNotFoundError:
        pass  # Missing store is a passive empty result, never created here.
    except OSError:
        issues.append(ChoiceIssue(None, 'catalog_unavailable'))
    return ConnectionChoiceCatalog(tuple(sorted(choices, key=lambda row: row.profile)), tuple(issues), not issues)

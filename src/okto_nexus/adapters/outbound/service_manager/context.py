"""Explicit non-secret execution context for the existing foreground entrypoint."""
from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path
import sys
import tempfile
import time

from ....config import (_BOOL_FIELDS, _ENUM_FIELDS, _FLOAT_FIELDS, _INT_FIELDS,
                       _PATH_FIELDS, _STRING_FIELDS)

CONTEXT_NAME = 'service-context.json'
# Deliberately exclude provider keys, shell startup hooks, PYTHONPATH and arbitrary
# application environment. Credentials remain in the user's existing vault/login.
ENVIRONMENT_REFERENCES = ('SystemRoot', 'WINDIR', 'USERPROFILE', 'HOMEDRIVE',
    'HOMEPATH', 'APPDATA', 'LOCALAPPDATA', 'PROGRAMDATA', 'TEMP', 'TMP', 'HOME',
    'XDG_CONFIG_HOME', 'XDG_DATA_HOME', 'XDG_RUNTIME_DIR', 'LANG', 'LC_ALL')


def document_revision(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(',', ':')).encode('utf-8')).hexdigest()


def atomic_json(path: Path, value: dict) -> None:
    fd, name = tempfile.mkstemp(prefix='.service-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        deadline = time.monotonic() + 1.0
        while True:
            try:
                os.replace(name, path)
                break
            except OSError as error:
                # Windows CRT readers do not share DELETE. A passive status
                # read can briefly prevent replacement of an otherwise valid
                # receipt. Retry only that OS contention, for a bounded time;
                # the old receipt remains intact until replacement succeeds.
                if (os.name != 'nt' or getattr(error, 'winerror', None) not in {5, 32}
                        or time.monotonic() >= deadline):
                    raise
                time.sleep(.01)
    finally:
        Path(name).unlink(missing_ok=True)


def read_json(path: Path) -> dict:
    with path.open('r', encoding='utf-8') as stream:
        raw = stream.read(131073)
    if len(raw) > 131072:
        raise ValueError('Service context exceeds the supported size')
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError('Invalid service document')
    return value


def execution_context(config, *, host, port, project_root, log_level, discovery, env) -> dict:
    arguments = ['--host', host, '--port', str(port), '--project-root',
                 str(Path(project_root).expanduser().resolve()), '--log-level', log_level]
    for fields in (_PATH_FIELDS, _BOOL_FIELDS, _ENUM_FIELDS, _FLOAT_FIELDS,
                   _INT_FIELDS, _STRING_FIELDS):
        for name, definition in fields.items():
            value = getattr(config, name)
            if value is None:
                continue
            if name in _PATH_FIELDS:
                value = str(Path(value).resolve())
            elif type(value) is bool:
                value = str(value).lower()
            arguments.extend([definition[1], str(value)])
    for path in discovery.trusted_roots:
        arguments.extend(['--harness-root', str(path)])
    if discovery.pi_install_root is not None:
        arguments.extend(['--pi-install-root', str(discovery.pi_install_root),
                          '--pi-node', str(discovery.pi_node)])
    environment = {key: env[key] for key in ENVIRONMENT_REFERENCES if env.get(key)}
    # Freeze only absolute search directories, not aliases/functions or the
    # caller's current-directory PATH entry. Explicit discovery approvals survive.
    environment['PATH'] = os.pathsep.join(dict.fromkeys(str(Path(item).resolve())
        for item in env.get('PATH', os.defpath).split(os.pathsep)
        if item and Path(item).is_absolute()))
    environment.update(PYTHONUNBUFFERED='1', OKTO_NEXUS_NO_BANNER='1')
    return {'revision': 1, 'component': 'server',
            # Keep the venv executable symlink: resolving it on POSIX would
            # select the base interpreter and discard the installed environment.
            'executable': str(Path(sys.executable).absolute()),
            'environment_prefix': str(Path(sys.prefix).absolute()),
            'cwd': str(Path(project_root).expanduser().resolve()),
            'arguments': arguments, 'environment': environment}


def validate_context(value: dict, *, require_paths=True) -> dict:
    if value.get('upgrade_pending'):
        raise ValueError('SERVICE_UPGRADE_PENDING: resume the retained upgrade plan')
    if value.get('revision') not in {1, 2} or value.get('component') != 'server':
        raise ValueError('Unsupported service context')
    for key in ('executable', 'environment_prefix', 'cwd'):
        if not isinstance(value.get(key), str) or not Path(value[key]).is_absolute():
            raise ValueError('Service paths must be absolute')
    if require_paths and (not Path(value['executable']).is_file() or not Path(value['cwd']).is_dir()):
        raise ValueError('Service executable or working directory no longer exists')
    arguments, environment = value.get('arguments'), value.get('environment')
    if (not isinstance(arguments, list) or not all(type(x) is str for x in arguments)
            or not isinstance(environment, dict) or not all(type(k) is str and type(v) is str
                for k, v in environment.items())
            or set(environment) - set(ENVIRONMENT_REFERENCES) - {'PATH', 'PYTHONUNBUFFERED', 'OKTO_NEXUS_NO_BANNER'}):
        raise ValueError('Unsupported service environment or arguments')
    return value

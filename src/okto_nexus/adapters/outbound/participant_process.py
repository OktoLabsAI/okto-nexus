"""Foreground external-client launch; credentials travel only in the child environment."""
import hashlib
import os
from pathlib import Path
import subprocess

from nexus_connector_core.discovery import candidate, discover_path

from ...application.execution_local_realizations import directory_identity
from ...application.terminal_connection import ConnectionError, document_revision
from .participant_client import participant_key
from . import participant_files

ADAPTERS = {'claude': 'claude_stream', 'codex': 'codex_app_server'}
CONTEXT_VARIABLES = ('HOME', 'USERPROFILE', 'APPDATA', 'LOCALAPPDATA', 'XDG_CONFIG_HOME',
    'CODEX_HOME', 'CLAUDE_CONFIG_DIR')


def select_executable(client, executable=None, *, environment):
    adapter = ADAPTERS.get(client)
    if adapter is None:
        raise ConnectionError('PARTICIPANT_LAUNCH_UNSUPPORTED', 'Generic clients require their own secure launcher.')
    if executable is None:
        choices = discover_path(adapter, path_env=environment.get('PATH', ''))
        if len(choices) != 1:
            raise ConnectionError('CLIENT_SELECTION_REQUIRED',
                'Select --executable with the absolute native client path; discovery found zero or multiple installations.')
        executable = choices[0].executable
    return candidate(adapter, Path(executable).expanduser().absolute(), explicit=True).executable


def launch_context(review, config, executable, *, environment):
    selected = select_executable(config.client, executable, environment=environment)
    binary = Path(selected)
    with binary.open('rb') as stream:
        info = os.fstat(stream.fileno())
        sha = hashlib.file_digest(stream, 'sha256').hexdigest()
    participant_files.current_owned_entry(review['file'], config)
    file = Path(review['file']['path'])
    project = Path(review['selection']['project']).resolve(strict=True)
    args = []
    if config.client == 'codex':
        # A shared app-server can predate this environment. Never silently fall
        # back to it if the installed version does not support this option.
        args = ['--no-daemon']
        codex_home = environment.get('CODEX_HOME')
        if codex_home:
            user_config = Path(codex_home).expanduser().resolve() / 'config.toml'
        else:
            user_home = environment.get('USERPROFILE' if os.name == 'nt' else 'HOME')
            user_config = Path(user_home).resolve() / '.codex/config.toml' if user_home else None
        if file not in (project / '.codex/config.toml', user_config):
            raise ConnectionError('CLIENT_CONFIG_NOT_LOADED',
                'Codex launch supports the selected project .codex/config.toml or its actual user config.toml. Review init for one of those files.')
    elif file != project / '.mcp.json':
        args = ['--mcp-config', str(file)]
    return dict(executable=selected, binary=dict(sha256=sha, device=info.st_dev, inode=info.st_ino),
        arguments=args, project=directory_identity(str(project)), cwd=str(project),
        config_file=str(file), config_sha256=participant_files.digest(file.read_bytes()),
        config_access_revision=participant_files.access_revision(file),
        client_context_revision=document_revision({name: environment.get(name) for name in CONTEXT_VARIABLES}))


def child_environment(config, key, environment):
    # Windows environment names are case-insensitive. Remove other participant
    # references even when their casing differs; leave the caller's map intact.
    result = {name: value for name, value in environment.items()
        if not name.upper().startswith('NEXUS_PARTICIPANT_TOKEN_')}
    result[config.credential_environment] = participant_key(key)
    return result


def spawn(context, environment):
    # Inherit the user's terminal, ordinary provider login and native policies.
    # No prompt, shell, background daemon, transcript capture or model request.
    return subprocess.Popen([context['executable'], *context['arguments']],
        cwd=context['cwd'], env=environment, shell=False)

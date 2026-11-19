"""Launch the reviewed Codex frontend on the operator's terminal."""

import hashlib
import os
import platform
import socket
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID

from nexus_connector_core import CoreError
from nexus_connector_core.discovery import candidate, discover_path

from ....application.terminal_connection import ConnectionError
from ....domain.presentation_protocol import CODEX_VIEWER_WINDOWS_SHA256
from .codex_viewer_relay import ViewerTurnConfirmation, local_codex_relay

_AUTH_VARIABLE = 'NEXUS_CODEX_VIEWER_TOKEN'


def select_viewer(executable=None):
    """Use the exact frontend build exercised with the local relay."""
    if os.name != 'nt' or platform.machine().casefold() not in {'amd64', 'x86_64'}:
        raise ConnectionError('VIEWER_BUILD_UNAVAILABLE', 'This platform has no reviewed local Codex viewer build.')
    try:
        choices = discover_path('codex_app_server') if executable is None else (
            candidate('codex_app_server', executable.expanduser(), explicit=True),)
    except (CoreError, OSError):
        choices = ()
    matches = [Path(item.executable) for item in choices
               if item.fingerprint == 'sha256:' + CODEX_VIEWER_WINDOWS_SHA256]
    if len(matches) != 1:
        raise ConnectionError('VIEWER_BUILD_UNAVAILABLE',
                              'Select the reviewed Codex 0.170.0 executable with --viewer-executable.')
    return matches[0]


def _environment(root, proxy):
    directories = {'APPDATA': 'roaming', 'LOCALAPPDATA': 'local', 'TEMP': 'temp', 'TMP': 'temp',
                   'CODEX_HOME': 'codex', 'XDG_CONFIG_HOME': 'config', 'XDG_CACHE_HOME': 'cache'}
    result = {name: str(root / folder) for name, folder in directories.items()}
    for path in set(result.values()):
        Path(path).mkdir(parents=True, exist_ok=True)
    windows = Path(os.environ['SystemRoot'])
    result.update({
        'SystemRoot': str(windows), 'WINDIR': str(windows), 'PATH': str(windows / 'System32'),
        'COMSPEC': str(windows / 'System32' / 'cmd.exe'), 'PATHEXT': '.COM;.EXE',
        'HOME': str(root), 'USERPROFILE': str(root), 'HOMEDRIVE': root.drive,
        'HOMEPATH': str(root)[len(root.drive):], 'TERM': 'xterm-256color',
        'DO_NOT_TRACK': '1', 'DISABLE_TELEMETRY': '1',
        'HTTP_PROXY': proxy, 'HTTPS_PROXY': proxy, 'ALL_PROXY': proxy, 'NO_PROXY': '127.0.0.1',
    })
    return result


def _check_viewer(executable):
    with executable.open('rb') as binary:
        if hashlib.file_digest(binary, 'sha256').hexdigest() != CODEX_VIEWER_WINDOWS_SHA256:
            raise ConnectionError('VIEWER_BUILD_CHANGED', 'The reviewed Codex executable changed before launch.')


def _report_input_status(message):
    # Codex waits for the native turn/start reply before painting its next RPC
    # notification. The attached Nexus console can report the durable queue now.
    print(f'\n{message}', file=sys.stderr, flush=True)


def present_codex(link, executable):
    """The foreground process is the viewer. Exiting closes only its attachment."""
    from .windows_viewer_terminal import run_viewer_terminal

    try:
        with TemporaryDirectory(prefix='nexus-codex-viewer-') as temporary, socket.socket() as deny_proxy:
            deny_proxy.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            deny_proxy.bind(('127.0.0.1', 0))
            root = Path(temporary)
            project = root / 'project'
            project.mkdir()
            environment = _environment(root / 'profile', f'http://127.0.0.1:{deny_proxy.getsockname()[1]}')
            confirmation = ViewerTurnConfirmation(_report_input_status) if getattr(link, 'input_revision', None) else None
            with local_codex_relay(link, viewer_home=environment['CODEX_HOME'], platform_os='windows',
                                   report_input_status=_report_input_status, confirmation=confirmation) as endpoint:
                thread_id = str(UUID(endpoint.thread_id))
                if thread_id != endpoint.thread_id:
                    raise ValueError('Invalid native session identity')
                _check_viewer(executable)
                environment[_AUTH_VARIABLE] = endpoint.token
                result = run_viewer_terminal(
                    [str(executable), 'resume', thread_id, '--remote', endpoint.address,
                     '--remote-auth-token-env', _AUTH_VARIABLE, '--no-alt-screen',
                     '-c', 'check_for_update_on_startup=false', '-c', 'analytics.enabled=false'],
                    cwd=project, env=environment, confirmation=confirmation,
                )
                if not endpoint.connected.is_set() and not result.detached:
                    raise ConnectionError('VIEWER_NOT_ATTACHED', 'The Codex viewer did not connect to this presentation.')
    except (KeyError, OSError, ValueError):
        raise ConnectionError('VIEWER_LAUNCH_FAILED', 'The local Codex viewer could not be opened.') from None
    if result.returncode:
        raise ConnectionError('VIEWER_EXIT_FAILED', 'The Codex viewer closed with an error.')

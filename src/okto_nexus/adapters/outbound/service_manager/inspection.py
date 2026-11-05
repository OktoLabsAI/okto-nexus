"""Bounded local inspection, without starting processes or creating state files."""
from __future__ import annotations

from importlib.metadata import version
import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, build_opener

from ....domain.service_lifecycle import SERVICE_PROTOCOL_REVISION
from .identity import server_instance_id
from .locking import ExclusiveFileLock, LockBusy


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _held(path: Path) -> bool | None:
    guard = ExclusiveFileLock(path)
    try:
        guard.acquire(create=False)
    except FileNotFoundError:
        return False
    except LockBusy:
        return True
    except OSError:
        return None
    else:
        guard.release()
        return False


def inspect_local_server(*, home: Path, database: Path, host: str, port: int,
                         timeout: float = 2.0) -> dict:
    home, database = home.resolve(), database.resolve()
    result = {'component': 'server', 'instance_id': server_instance_id(home, database),
              'installed_version': version('okto-nexus'), 'active_version': None,
              'generation': None, 'state': 'unknown', 'ready_for_queries': False,
              'work_state': 'not_checked', 'reason': None, 'next_action': None,
              'effective_configuration': {'home': str(home), 'database': str(database),
                                          'bind_host': host, 'port': port}}
    guards = [_held(home / 'nexus.serve.guard'),
              _held(database.with_name(database.name + '.serve.guard'))]
    try:
        metadata = json.loads((home / 'nexus.serve.lock').read_text(encoding='utf-8'))
        if not isinstance(metadata, dict):
            metadata = {}
    except FileNotFoundError:
        metadata = {}
    except (OSError, ValueError):
        return {**result, 'reason': 'INSTANCE_METADATA_UNAVAILABLE',
                'next_action': 'Inspect permissions and the existing foreground instance.'}
    if guards == [False, False] and (not metadata or metadata.get('lock_version') == 2):
        return {**result, 'state': 'stopped', 'reason': 'NO_SERVICE_OWNER',
                'next_action': 'Start the configured instance explicitly. Runtime work has not been inspected.'}
    if guards != [True, True]:
        return {**result, 'reason': 'INSTANCE_OWNERSHIP_UNCONFIRMED',
                'next_action': 'Inspect the existing owner; do not start a competing instance.'}
    if host not in {'127.0.0.1', 'localhost', '0.0.0.0', '::', '::1'}:
        return {**result, 'reason': 'LOCAL_CONTROL_UNAVAILABLE',
                'next_action': 'This bind has no loopback control address; inspect the foreground service.'}
    address = '[::1]' if host in {'::', '::1'} else '127.0.0.1'
    endpoint = f'http://{address}:{port}/api/v1/service'
    try:
        opener = build_opener(ProxyHandler({}), NoRedirect())
        with opener.open(endpoint, timeout=timeout) as response:
            # No unbounded or secret-bearing body is surfaced in a diagnostic.
            payload = response.read(32769)
            if len(payload) > 32768:
                raise ValueError('Oversized readiness response')
            document = json.loads(payload)
            data = document.get('data') if document.get('ok') is True else None
            if not isinstance(data, dict):
                raise ValueError('Invalid readiness envelope')
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, AttributeError):
        return {**result, 'state': 'degraded', 'reason': 'SERVICE_UNREACHABLE',
                'next_action': 'Inspect startup/transport diagnostics for this instance; no process was started.'}
    if (data.get('instance_id') != result['instance_id'] or not metadata.get('generation')
            or data.get('generation') != metadata['generation']
            or data.get('pid') != metadata.get('pid')
            or data.get('component') != 'server'):
        return {**result, 'state': 'failed', 'reason': 'INSTANCE_MISMATCH',
                'next_action': 'The endpoint does not prove ownership of this configured instance.'}
    if (data.get('protocol_revision') != SERVICE_PROTOCOL_REVISION
            or data.get('active_version') != result['installed_version']):
        return {**result, 'state': 'degraded', 'active_version': data.get('active_version'),
                'reason': 'VERSION_INCOMPATIBLE',
                'next_action': 'Review active and installed versions; do not interrupt or upgrade implicitly.'}
    allowed = {'component', 'instance_id', 'generation', 'active_version', 'pid', 'supervisor',
               'state', 'ready_for_queries', 'storage_initialized', 'admission',
               'reason', 'next_action', 'protocol_revision', 'shutdown'}
    if (data.get('state') not in {'starting', 'ready', 'degraded', 'stopping', 'failed'}
            or type(data.get('ready_for_queries')) is not bool):
        return {**result, 'state': 'failed', 'reason': 'INVALID_READINESS',
                'next_action': 'Inspect the active service protocol.'}
    return {**result, **{key: data[key] for key in allowed if key in data}}

"""Bounded inspection of an explicitly selected installed service environment."""
from __future__ import annotations

import hashlib
from importlib import metadata
import json
import os
import re
from pathlib import Path
import subprocess
import sys

UPGRADE_PROTOCOL = 2


class EnvironmentInspectionError(ValueError):
    code = 'UPGRADE_ENVIRONMENT_UNAVAILABLE'
    action = 'Inspect the selected installed Python and package files, then retry the same reviewed operation. No alternate environment was selected.'

DISTRIBUTION = 'okto-nexus'
PACKAGE = 'okto_nexus'


def _distribution(name, package):
    distribution = metadata.distribution(name)
    direct = distribution.read_text('direct_url.json')
    if direct and json.loads(direct).get('dir_info', {}).get('editable'):
        raise ValueError('Upgrade requires an installed wheel, not an editable checkout')
    paths = sorted(distribution.files or (), key=str)
    if len(paths) > 10000 or not any(str(path).replace('\\', '/').startswith(package + '/') and str(path).endswith('.py') for path in paths):
        raise ValueError('Installed package payload could not be verified')
    digest, total = hashlib.sha256(), 0
    for item in paths:
        name = str(item).replace('\\', '/')
        if '__pycache__/' in name or name.endswith(('.pyc', '.pyo')):
            continue
        path = Path(distribution.locate_file(item))
        with path.open('rb') as stream:
            blob = stream.read(64 * 1024 * 1024 + 1)
        total += len(blob)
        if len(blob) > 64 * 1024 * 1024 or total > 256 * 1024 * 1024:
            raise ValueError('Installed package inspection exceeded its byte budget')
        digest.update(name.encode('utf-8') + b'\0' + hashlib.sha256(blob).digest())
    return {'version': distribution.version, 'digest': digest.hexdigest()}


def snapshot():
    package = _distribution(DISTRIBUTION, PACKAGE)
    core = _distribution('okto-nexus-connector-core', 'nexus_connector_core')
    pins = [match.group(1) for requirement in metadata.requires(DISTRIBUTION) or ()
        if (match := re.fullmatch(r'okto[-_]nexus[-_]connector[-_]core\s*==\s*([0-9.]+)', requirement, re.I))]
    if pins != [core['version']]:
        raise ValueError('The installed Core does not match the application exact pin')
    executable = Path(sys.executable).absolute()
    if executable.name.lower() == 'pythonw.exe':
        executable = executable.with_name('python.exe')
    return {'protocol': UPGRADE_PROTOCOL, 'distribution': DISTRIBUTION,
        'package': package, 'core': core, 'executable': str(executable),
        'environment_prefix': str(Path(sys.prefix).absolute()),
        'python_version': sys.version.split()[0],
        'python_digest': hashlib.sha256(executable.read_bytes()).hexdigest()}


def _probe(executable):
    path = Path(executable).expanduser().absolute()
    if not path.is_file():
        raise ValueError('The selected Python executable is missing')
    environment = {key: value for key, value in os.environ.items() if key.upper() in {
        'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'TEMP', 'TMP', 'USERPROFILE', 'HOME',
        'LOCALAPPDATA', 'APPDATA', 'LANG', 'LC_ALL'}}
    result = subprocess.run([str(path), '-I', '-m', PACKAGE + '.service_environment'],
        cwd=path.parent, env=environment, stdin=subprocess.DEVNULL,
        capture_output=True, timeout=60)
    if result.returncode or len(result.stdout) > 16384:
        raise ValueError('The selected installed environment did not confirm upgrade support')
    value = json.loads(result.stdout)
    if (not isinstance(value, dict) or value.get('protocol') != UPGRADE_PROTOCOL
            or value.get('distribution') != DISTRIBUTION
            or not isinstance(value.get('executable'), str)
            or Path(value['executable']).absolute() != path):
        raise ValueError('The selected environment returned an incompatible identity')
    for key in ('package', 'core'):
        entry = value.get(key)
        if (not isinstance(entry, dict) or not isinstance(entry.get('version'), str)
                or not re.fullmatch(r'[0-9a-f]{64}', str(entry.get('digest', '')))):
            raise ValueError('The selected environment returned an invalid package fingerprint')
    if (not isinstance(value.get('environment_prefix'), str)
            or not Path(value['environment_prefix']).is_absolute()
            or not re.fullmatch(r'[0-9a-f]{64}', str(value.get('python_digest', '')))):
        raise ValueError('The selected environment returned invalid interpreter references')
    return value


def probe(executable):
    try:
        return _probe(executable)
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        raise EnvironmentInspectionError('The selected installed environment did not complete bounded inspection') from error


def verify_context(value):
    """Fail before bootstrap if a selected installed payload changed in place."""
    if value.get('upgrade_pending'):
        raise ValueError('SERVICE_UPGRADE_PENDING')
    if value.get('revision') == 2:
        observed = hashlib.sha256(json.dumps(snapshot(), sort_keys=True, ensure_ascii=False,
            separators=(',', ':')).encode('utf-8')).hexdigest()
        if observed != value.get('environment_fingerprint'):
            raise ValueError('SERVICE_ENVIRONMENT_CHANGED')


def release_version(value):
    """Only ordered stable releases are eligible for this upgrade protocol."""
    if not isinstance(value, str) or not re.fullmatch(r'\d+\.\d+\.\d+', value):
        raise ValueError('UPGRADE_VERSION_UNCONFIRMED: a stable release version is required')
    return tuple(int(part) for part in value.split('.'))


def installed_versions(executable):
    """Read legacy package metadata without importing its application or Core."""
    command = ('import json; from importlib.metadata import version; '
        'print(json.dumps([version(' + repr(DISTRIBUTION) + '), '
        'version("okto-nexus-connector-core")]))')
    result = subprocess.run([str(executable), '-I', '-c', command],
        cwd=Path(executable).parent, stdin=subprocess.DEVNULL,
        capture_output=True, timeout=10)
    if result.returncode or len(result.stdout) > 1024:
        raise ValueError('UPGRADE_SOURCE_VERSION_UNCONFIRMED')
    value = json.loads(result.stdout)
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError('UPGRADE_SOURCE_VERSION_UNCONFIRMED')
    for version in value:
        release_version(version)
    return value


if __name__ == '__main__':
    try:
        print(json.dumps(snapshot()))
    except (OSError, ValueError, metadata.PackageNotFoundError):
        raise SystemExit(2) from None

"""WSL own-/tmp bootstrap; never installs to system/user locations."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import ssl
import subprocess
import sys
import tarfile
import urllib.request

ROOT = Path('/tmp/nexus-qc28-xmlie7rv')
assert ROOT.is_dir() and ROOT.parent == Path('/tmp') and ROOT.name.startswith('nexus-qc28-')
os.chdir(ROOT)
for name in ('home', 'xdg-config', 'xdg-data', 'xdg-cache', 'cache', 'tmp', 'downloads', 'python'):
    (ROOT / name).mkdir(exist_ok=True)
ENV = dict(PATH='/usr/bin:/bin', HOME=str(ROOT / 'home'), USERPROFILE=str(ROOT / 'home'),
           XDG_CONFIG_HOME=str(ROOT / 'xdg-config'), XDG_DATA_HOME=str(ROOT / 'xdg-data'),
           XDG_CACHE_HOME=str(ROOT / 'xdg-cache'), TMPDIR=str(ROOT / 'tmp'), LANG='C.UTF-8',
           UV_CACHE_DIR=str(ROOT / 'cache'), UV_NO_CONFIG='1', UV_PYTHON_INSTALL_DIR=str(ROOT / 'python'),
           UV_PYTHON_BIN_DIR=str(ROOT / 'bin'), UV_PYTHON_PREFERENCE='only-managed')


def write(name, value):
    (ROOT / name).write_text(json.dumps(value, indent=2) + '\n')


def run(label, argv, timeout=180):
    print('START ' + label, flush=True)
    with (ROOT / (label + '.log')).open('w') as output:
        result = subprocess.run(argv, cwd=ROOT, env=ENV, stdin=subprocess.DEVNULL,
                                stdout=output, stderr=subprocess.STDOUT, timeout=timeout)
    write(label + '-command.json', dict(argv=argv, exit_code=result.returncode, timeout=timeout))
    print('END ' + label + ' ' + str(result.returncode), flush=True)
    assert result.returncode == 0, label


def download(url, target, bound):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                        urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    with opener.open(url, timeout=30) as response:
        content = response.read(bound + 1)
        assert len(content) <= bound
    target.write_bytes(content)
    return content


def main():
    write('environment.json', dict(OS=platform.platform(), bootstrap_python=sys.version,
        env=ENV, os_release=Path('/etc/os-release').read_text(), at=datetime.now(timezone.utc).isoformat(),
        scope='Own /tmp only; env -i; no apt/sudo/dotfiles/system or user installs.'))
    assert platform.machine() == 'x86_64'
    base = 'https://github.com/astral-sh/uv/releases/download/0.10.7/'
    name = 'uv-x86_64-unknown-linux-gnu.tar.gz'
    expected = download(base + name + '.sha256', ROOT / 'downloads/uv.sha256', 4096).decode().split()[0]
    assert len(expected) == 64 and all(c in '0123456789abcdef' for c in expected)
    raw = download(base + name, ROOT / 'downloads' / name, 64 * 1024 * 1024)
    actual = hashlib.sha256(raw).hexdigest()
    assert actual == expected
    with tarfile.open(ROOT / 'downloads' / name, 'r:gz') as archive:
        member = archive.getmember('uv-x86_64-unknown-linux-gnu/uv')
        assert member.isfile()
        binary = archive.extractfile(member).read()
    (ROOT / 'uv').write_bytes(binary)
    (ROOT / 'uv').chmod(0o700)
    write('uv-download.json', dict(release='https://github.com/astral-sh/uv/releases/tag/0.10.7',
        archive_url=base + name, sha256_url=base + name + '.sha256', expected_sha256=expected,
        actual_sha256=actual, uv_binary_sha256=hashlib.sha256(binary).hexdigest(),
        extracted_members=['uv-x86_64-unknown-linux-gnu/uv'], TLS_verified=True))
    run('uv-version', [str(ROOT / 'uv'), '--version'])
    assert (ROOT / 'uv-version.log').read_text().startswith('uv 0.10.7 ')
    run('python-install', [str(ROOT / 'uv'), 'python', 'install', '3.13.1', '--install-dir', str(ROOT / 'python'),
        '--no-bin', '--no-registry', '--no-config', '--cache-dir', str(ROOT / 'cache')])
    write('bootstrap-ready.json', dict(status='TEMP_RUNTIME_READY', root=str(ROOT)))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        write('bootstrap-failed.json', dict(status='STOPPED_SETUP_FAILURE_NO_SYSTEM_INSTALL',
              error_type=type(error).__name__, message=str(error)))
        raise

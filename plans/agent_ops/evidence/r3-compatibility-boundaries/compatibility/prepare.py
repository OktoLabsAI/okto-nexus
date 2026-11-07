"""Build historical artifacts in Temp; shared environments stay read-only."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys
import venv
import zipfile

ROOT = Path(__file__).resolve().parent
NEXUS = Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
CONNECTOR = Path('D:/Projetos/Techridy/okto-nexus-connector')
CI = Path('C:/Users/jpamb/AppData/Local/Temp/nexus-ci-connector-refresh-la1tb1l6/venv')
DEPS = Path('C:/Users/jpamb/AppData/Roaming/Python/Python313/site-packages')
BASES = {'nexus': (NEXUS, 'c1e78e26fb2bd57ace3370417a2cb7529856b603'),
         'connector': (CONNECTOR, 'a3017d97b6a295cb2b46b9dd391b4c04ed121ee2')}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    private = ROOT / 'private'
    private.mkdir()
    for name in ('home', 'appdata', 'localappdata', 'temp'):
        (private / name).mkdir()
    env = {key: value for key, value in os.environ.items()
           if key.upper() in {'SYSTEMROOT', 'WINDIR', 'SYSTEMDRIVE', 'COMSPEC', 'PATHEXT',
                              'PROCESSOR_ARCHITECTURE', 'NUMBER_OF_PROCESSORS'}}
    env.update(PATH=str(Path(env['SYSTEMROOT']) / 'System32'),
               TEMP=str(private / 'temp'), TMP=str(private / 'temp'),
               USERPROFILE=str(private / 'home'), HOME=str(private / 'home'),
               APPDATA=str(private / 'appdata'), LOCALAPPDATA=str(private / 'localappdata'),
               PIP_NO_INDEX='1', PIP_DISABLE_PIP_VERSION_CHECK='1', NO_COLOR='1')
    (ROOT / 'environment.json').write_text(json.dumps(env, indent=2) + '\n', encoding='utf-8')
    old_env = ROOT / 'old-venv'
    venv.EnvBuilder(with_pip=False).create(old_env)
    # Dependency-only fallback. Local old packages precede both read-only paths.
    (old_env / 'Lib/site-packages/qualified-dependencies.pth').write_text(
        str(CI / 'Lib/site-packages') + '\n' + str(DEPS) + '\n', encoding='utf-8')
    python = old_env / 'Scripts/python.exe'
    wheels = ROOT / 'wheels'
    wheels.mkdir()
    records = {}
    for name, (repo, revision) in BASES.items():
        archive = ROOT / (name + '-source.zip')
        subprocess.run(['rtk', 'proxy', 'git', 'archive', '--format=zip', '--output=' + str(archive), revision],
                       cwd=repo, check=True)
        source = ROOT / 'build-source' / name
        source.mkdir(parents=True)
        with zipfile.ZipFile(archive) as z:
            z.extractall(source)
        command = [str(python), '-I', '-X', 'utf8', '-m', 'build', '--wheel', '--no-isolation',
                   '--outdir', str(wheels), str(source)]
        with (ROOT / (name + '-build.log')).open('wb') as output:
            result = subprocess.run(command, cwd=ROOT, env=env, stdout=output, stderr=subprocess.STDOUT)
        records[name] = {'repo': str(repo), 'commit': revision, 'archive_sha256': sha(archive),
                         'command': command, 'exit_code': result.returncode}
        (ROOT / 'preparation.json').write_text(json.dumps(records, indent=2) + '\n', encoding='utf-8')
        if result.returncode:
            raise SystemExit(result.returncode)
    core = NEXUS / 'vendor/wheels/okto_nexus_connector_core-0.0.13-py3-none-any.whl'
    assert sha(core) == 'b01d4e2c6882b581d41cdf40179d5a96a6ff671b9f762244f3a4cae929a99988'
    shutil.copy2(core, wheels / core.name)
    old_wheels = sorted(wheels.glob('*.whl'))
    assert len(old_wheels) == 3
    command = [str(python), '-I', '-m', 'pip', 'install', '--no-index', '--no-deps',
               '--ignore-installed', *map(str, old_wheels)]
    with (ROOT / 'old-install.log').open('wb') as output:
        result = subprocess.run(command, cwd=ROOT, env=env, stdout=output, stderr=subprocess.STDOUT)
    records['installation'] = {'command': command, 'exit_code': result.returncode,
                               'wheels': {p.name: sha(p) for p in old_wheels},
                               'readonly_dependency_paths': [str(CI / 'Lib/site-packages'), str(DEPS)]}
    (ROOT / 'preparation.json').write_text(json.dumps(records, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'root': str(ROOT), 'exit_code': result.returncode,
                      'historical_artifacts': records['installation']['wheels']}))
    raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()

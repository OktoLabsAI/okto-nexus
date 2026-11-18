"""Owned isolated build/install orchestration; no provider or personal prefix."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from owned_commands import run_owned

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
ALLOCATION = HERE/'allocation.json'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def environment(root):
    # Allowlist avoids even copying provider/token values into child envs.
    names = {'PATH','SYSTEMROOT','WINDIR','COMSPEC','PATHEXT','NUMBER_OF_PROCESSORS',
             'PROCESSOR_ARCHITECTURE','SYSTEMDRIVE','OS','PROGRAMFILES','PROGRAMFILES(X86)',
             'COMMONPROGRAMFILES','COMMONPROGRAMFILES(X86)'}
    env = {key:os.environ[key] for key in os.environ if key.upper() in names}
    for key, directory in (('TEMP','tmp'),('TMP','tmp'),('USERPROFILE','userprofile'),
                           ('HOME','userprofile'),('APPDATA','appdata'),('LOCALAPPDATA','localappdata')):
        (root/directory).mkdir(exist_ok=True)
        env[key] = str(root/directory)
    env.update(PIP_CONFIG_FILE=os.devnull, PIP_DISABLE_PIP_VERSION_CHECK='1', PIP_NO_INPUT='1',
               PIP_CACHE_DIR=str(root/'pip-cache'), UV_NO_CONFIG='1', UV_CACHE_DIR=str(root/'uv-cache'),
               UV_NO_PROGRESS='1', PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1')
    return env


def command(root, label, argv, *, cwd=None, timeout=600):
    cwd = cwd or root
    recorded = dict(at=datetime.now(timezone.utc).isoformat(),label=label,argv=list(map(str,argv)),cwd=str(cwd))
    path=root/'commands.json'
    records=json.loads(path.read_text()) if path.exists() else []
    records.append(recorded)
    path.write_text(json.dumps(records,indent=2)+'\n',encoding='utf-8')
    print('START '+label,flush=True)
    with (root/(label+'.log')).open('w',encoding='utf-8') as log:
        result=run_owned(argv,root=root,cwd=cwd,env=environment(root),log=log,timeout=timeout)
    recorded.update(result)
    path.write_text(json.dumps(records,indent=2)+'\n',encoding='utf-8')
    print('END '+label+' '+str(result['exit_code']),flush=True)
    if not result['success']:
        raise SystemExit(result['exit_code'] or 124)


def pins():
    paths=[]
    for folder in ('src','frontend/src','frontend/public','tests'):
        paths.extend(p for p in (REPO/folder).rglob('*') if p.is_file()
                     and '__pycache__' not in p.parts and p.suffix not in ('.pyc','.pyo'))
    paths.extend(REPO/name for name in ('pyproject.toml','README.md','LICENSE','uv.lock',
                                      'vendor/ci/manifest.json','tools/ci_installed.py',
                                      'tools/build_validation_artifacts.py'))
    paths.extend(p for p in (REPO/'frontend').glob('*') if p.is_file()
                 and p.suffix in ('.json','.ts','.js','.mjs','.html'))
    return {p.relative_to(REPO).as_posix():sha(p) for p in sorted(set(paths)) if p.is_file()}


def source_ready():
    path = HERE/'SOURCE_ASSET_READY.json'
    assert path.is_file(), 'Root SOURCE_ASSET_READY required before any allocation/build/install.'
    ready = json.loads(path.read_text(encoding='utf-8'))
    assert ready.get('source_asset_ready') is True and ready.get('version') == '0.3.7'
    assert len(ready['source_commit']) == 40 and ready['assets']
    head = subprocess.check_output(['rtk','proxy','git','rev-parse','HEAD'],cwd=REPO,text=True).strip()
    assert head == ready['source_commit'], (head,ready['source_commit'])
    static = REPO/'src/okto_nexus/adapters/inbound/http/static'
    assert 'index.html' in ready['assets']
    for name,pin in ready['assets'].items():
        assert (static/name).resolve().is_relative_to(static.resolve()), name
        assert sha(static/name) == pin, name
    return ready


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=('prepare','build','install','smoke','twine','audit'))
    args=parser.parse_args()
    source_ready()
    if args.action=='prepare':
        assert not ALLOCATION.exists(), 'Existing allocation is preserved; do not silently create another root.'
        root=Path(tempfile.mkdtemp(prefix='nexus-hst-r1-package-'))
        ALLOCATION.write_text(json.dumps(dict(root=str(root),created_at=datetime.now(timezone.utc).isoformat()),indent=2)+'\n',encoding='utf-8')
        (root/'SOURCE_ASSET_READY.json').write_text(json.dumps(source_ready(),indent=2)+'\n',encoding='utf-8')
        command(root,'venv',['rtk','proxy','uv','venv','--python','C:/Python313/python.exe','--seed',root/'venv'])
        print(json.dumps(dict(root=str(root),python=str(root/'venv/Scripts/python.exe'),installed=False)),flush=True)
        return
    root=Path(json.loads(ALLOCATION.read_text())['root']).resolve()
    assert root.parent==Path(tempfile.gettempdir()).resolve() and root.name.startswith('nexus-hst-r1-package-')
    python=root/'venv/Scripts/python.exe'
    if args.action=='build':
        assert not (root/'source').exists(), 'Never overwrite an antecedent source/artifact.'
        before=pins()
        (root/'source-pins-before.json').write_text(json.dumps(before,indent=2)+'\n',encoding='utf-8')
        source=root/'source'
        source.mkdir()
        shutil.copytree(REPO/'src',source/'src',ignore=shutil.ignore_patterns('__pycache__','*.pyc','*.pyo','*.egg-info'))
        for name in ('pyproject.toml','README.md','LICENSE'):
            if (REPO/name).exists():
                shutil.copyfile(REPO/name,source/name)
        command(root,'build',['rtk','proxy','uv','build','--out-dir',root/'artifacts',source])
        artifacts={p.name:sha(p) for p in (root/'artifacts').iterdir() if p.is_file()}
        after=pins()
        changed=[name for name in before.keys()|after.keys() if before.get(name)!=after.get(name)]
        assert not changed, changed
        (root/'build-manifest.json').write_text(json.dumps(dict(artifacts=artifacts,source_drift=changed,
            source_pins=before),indent=2)+'\n',encoding='utf-8')
        print(json.dumps(dict(root=str(root),artifacts=artifacts)),flush=True)
    else:
        wheel=root/'artifacts/okto_nexus-0.3.7-py3-none-any.whl'
        assert wheel.exists()
        if args.action=='twine':
            command(root,'twine-install',['rtk','proxy',python,'-m','pip','install','twine'])
            command(root,'twine',['rtk','proxy',python,'-m','twine','check',wheel,
                root/'artifacts/okto_nexus-0.3.7.tar.gz',
                REPO/'vendor/wheels/okto_nexus_connector_core-0.0.14-py3-none-any.whl',
                REPO/'vendor/ci/okto_nexus_connector-0.0.13-py3-none-any.whl'])
            command(root,'pip-check',['rtk','proxy',python,'-m','pip','check'])
        elif args.action=='audit':
            command(root,'installed-audit',['rtk','proxy',python,'-I',HERE/'audit.py'])
        else:
            command(root,'ci-'+args.action,['rtk','proxy',python,'-I',REPO/'tools/ci_installed.py',
                args.action,'--wheel',wheel,'--output',root/'ci'])
        print(json.dumps(dict(root=str(root),python=str(python),wheel=str(wheel),wheel_sha256=sha(wheel),
                              action=args.action,status='PASS')),flush=True)


if __name__=='__main__':
    main()

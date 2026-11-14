"""Pinned committed snapshots and isolated wheels. No service/provider actions."""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import tarfile
import zipfile

BUNDLE=Path(__file__).resolve().parent
ROOT=BUNDLE/'final-build'
ROOT.mkdir()
PYTHON=BUNDLE/'venv/Scripts/python.exe'
ENV=json.loads((BUNDLE/'environment.json').read_bytes())
REPOS={
 'core':('D:/Projetos/Techridy/okto-nexus-connector-core','7810f3b9bd2576bca5ccc8286a4c661789bf73a4','nexus_connector_core','okto_nexus_connector_core-0.0.14-py3-none-any.whl'),
 'nexus':('D:/Projetos/Techridy/okto_labs_okto_nexus','6714d69563f86e965b7551239a09367982eadbca','okto_nexus','okto_nexus-0.3.3-py3-none-any.whl'),
 'connector':('D:/Projetos/Techridy/okto-nexus-connector','e612ff852cf22264c52cc9d083548d6100a60efa','okto_nexus_connector','okto_nexus_connector-0.0.12-py3-none-any.whl'),
}
RTK=shutil.which('rtk')
GIT=shutil.which('git')
assert RTK and GIT
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(path,value):
    with Path(path).open('x',encoding='utf-8') as f:json.dump(value,f,indent=2);f.write('\n')
def run(label,args,python=True):
    with (ROOT/(label+'.stdout')).open('xb') as out,(ROOT/(label+'.stderr')).open('xb') as err:
        result=subprocess.run(([str(PYTHON),'-I','-B','-X','utf8'] if python else [])+args,
            cwd=ROOT,env=ENV,stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW,timeout=300)
    assert result.returncode==0,(label,result.returncode)
    print(label+':PASS',flush=True)

for name,(repo,commit,package,wheel) in REPOS.items():
    archive=ROOT/(name+'-source.tar')
    run('archive-'+name+'-v2',[RTK,'proxy',GIT,'-C',repo,'archive','--format=tar','--output='+str(archive),
                        commit,'pyproject.toml','README.md','LICENSE','src'],python=False)
    target=ROOT/('source-'+name);target.mkdir()
    with tarfile.open(archive) as source:source.extractall(target,filter='data')
    manifest={p.relative_to(target).as_posix():sha(p) for p in target.rglob('*') if p.is_file()}
    save(ROOT/('source-'+name+'-manifest.json'),{'commit':commit,'files':manifest})
    run('build-'+name,['-m','pip','wheel','--no-deps','--no-build-isolation','--no-index',
                      '--wheel-dir',str(ROOT/'wheels'),str(target)])
run('install',['-m','pip','install','--force-reinstall','--no-index','--no-deps',*[str(ROOT/'wheels'/v[3]) for v in REPOS.values()]])
run('pip-check',['-m','pip','check'])
payloads={}
for name,(_,commit,package,wheelname) in REPOS.items():
    wheel=ROOT/'wheels'/wheelname
    with zipfile.ZipFile(wheel) as archive:
        matched=[]
        for member in archive.namelist():
            if not member.startswith(package+'/') or member.endswith('/'):
                continue
            source=ROOT/('source-'+name)/'src'/member
            installed=BUNDLE/'venv/Lib/site-packages'/member
            assert source.is_file() and source.read_bytes()==archive.read(member)==installed.read_bytes(),member
            matched.append({'path':member,'sha256':sha(installed),'bytes':installed.stat().st_size})
        payloads[name]={'commit':commit,'files':matched,'wheel_sha256':sha(wheel)}
save(ROOT/'installation.json',{'status':'OFFLINE_INSTALLED_NOT_SERVICE_QUALIFIED','python':str(PYTHON),
    'products':payloads,'dependency_manifest_sha256':sha(BUNDLE/'dependency-manifest.json'),
    'environment_sha256':sha(BUNDLE/'environment.json'),'service_calls':0,'provider_calls':0})
print(json.dumps({'installation_sha256':sha(ROOT/'installation.json'),
                 'wheels':{name:payloads[name]['wheel_sha256'] for name in payloads}}))

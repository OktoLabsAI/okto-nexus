"""Own offline wheel build from exact committed archives; no product lifecycle."""
from pathlib import Path
import argparse,hashlib,json,os,shutil,subprocess,tarfile
HERE=Path(__file__).resolve().parent
PACKAGE=HERE/'package'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,v):
    with Path(p).open('x',encoding='utf-8') as out:json.dump(v,out,indent=2);out.write('\n')
def run(argv,*,cwd,label,env=None):
    out=PACKAGE/(label+'.stdout');err=PACKAGE/(label+'.stderr')
    with out.open('xb') as stdout,err.open('xb') as stderr:
        child=subprocess.Popen(argv,cwd=cwd,env=env,stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0));code=child.wait()
    assert code==0,(label,code)
    return {'returncode':code,'stdout_sha256':sha(out),'stderr_sha256':sha(err)}
def main():
    p=argparse.ArgumentParser();p.add_argument('--nexus-commit',required=True);p.add_argument('--connector-commit',required=True)
    args=p.parse_args()
    assert len(args.nexus_commit)==len(args.connector_commit)==40
    assert not PACKAGE.exists();PACKAGE.mkdir()
    source=HERE.with_name('work-request12')/'package/prepare_dependencies.py'
    shutil.copyfile(source,PACKAGE/'prepare_dependencies.py')
    dependencies=run(['C:/Python313/python.exe','-I','-B','-X','utf8',str(PACKAGE/'prepare_dependencies.py')],
        cwd=PACKAGE,label='dependency-copy')
    python=PACKAGE/'venv/Scripts/python.exe';env=json.loads((PACKAGE/'environment.json').read_bytes())
    sources={}
    for name,repo,commit in [('nexus',Path('D:/Projetos/Techridy/okto_labs_okto_nexus'),args.nexus_commit),
        ('connector',Path('D:/Projetos/Techridy/okto-nexus-connector'),args.connector_commit)]:
        target=PACKAGE/(name+'-source');target.mkdir();archive=PACKAGE/(name+'-source.tar')
        run(['rtk','git','archive','--format=tar','--output',str(archive),commit,'pyproject.toml','README.md','LICENSE','src'],
            cwd=repo,label=name+'-archive')
        with tarfile.open(archive) as stream:
            for member in stream.getmembers():
                path=(target/member.name).resolve();assert path.is_relative_to(target) and not member.issym() and not member.islnk()
            stream.extractall(target,filter='data')
        sources[name]={'repository':str(repo),'commit':commit,'archive_sha256':sha(archive)}
    wheels=PACKAGE/'built-wheels';wheels.mkdir()
    build=run([str(python),'-I','-B','-X','utf8','-m','pip','wheel','--no-index','--no-deps','--no-build-isolation',
        '--disable-pip-version-check','--wheel-dir',str(wheels),str(PACKAGE/'nexus-source'),str(PACKAGE/'connector-source')],
        cwd=PACKAGE,env=env,label='wheel-build')
    core=Path('C:/Users/jpamb/AppData/Local/Temp/r3-native-t19-t20-v2-fk9g74yv/final-build/wheels/okto_nexus_connector_core-0.0.14-py3-none-any.whl')
    assert sha(core)=='d881ab35ac619147df51cbe3a10964e534c50acd117e45e2612dcec7fbc1afe9'
    shutil.copyfile(core,wheels/core.name)
    pins={path.name:sha(path) for path in wheels.glob('*.whl')};assert len(pins)==3
    original=(HERE.with_name('work-request12')/'package/install_packages.py').read_text(encoding='utf-8')
    start=original.index('SOURCE = ');end=original.index('sha = lambda')
    installer=original[:start]+'SOURCE = Path('+repr(str(wheels))+')\nWHEELS = '+repr(pins)+'\n'+original[end:]
    (PACKAGE/'install_packages.py').write_text(installer,encoding='utf-8')
    installed=run(['C:/Python313/python.exe','-I','-B','-X','utf8',str(PACKAGE/'install_packages.py')],
        cwd=PACKAGE,label='package-install')
    save(PACKAGE/'build-provenance.json',{'sources':sources,'wheels':pins,'dependencies':dependencies,'build':build,
        'installation':installed,'installation_sha256':sha(PACKAGE/'installation.json'),'services_started':0,'models_called':0})
    print(json.dumps({'status':'NEW_PACKAGES_INSTALLED','wheels':pins,'installation_sha256':sha(PACKAGE/'installation.json')}))
if __name__=='__main__':main()

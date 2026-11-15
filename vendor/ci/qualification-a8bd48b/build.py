from pathlib import Path
import hashlib,importlib.metadata,json,os,shutil,subprocess,sys,tarfile
HERE=Path(__file__).resolve().parent
REPO=Path('D:/Projetos/Techridy/okto-nexus-connector')
BASE=Path('C:/Users/jpamb/AppData/Local/Temp/r3-core-consumer-integration-h_elhexb')
commit=sys.argv[1]
env=os.environ.copy(); env['SOURCE_DATE_EPOCH']='1767225600'
def run(args,cwd=None):
 with (HERE/'build.log').open('ab') as log:
  subprocess.run(['rtk','proxy',*map(str,args)],cwd=cwd,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
source=HERE/'connector-source'; source.mkdir()
archive=HERE/'connector-source.tar'
run(['git','-C',REPO,'archive','--format=tar','--output='+str(archive),commit,'pyproject.toml','README.md','LICENSE','src','tests'])
with tarfile.open(archive) as tar:
 assert tar.pax_headers['comment']==commit
 tar.extractall(source,filter='data')
run([sys.executable,'-m','build','--wheel','--no-isolation','--outdir',HERE/'wheels',source])
run(['uv','venv','--python',BASE/'venv/Scripts/python.exe',HERE/'venv'])
site=HERE/'venv/Lib/site-packages'
for path in (BASE/'venv/Lib/site-packages').iterdir():
 if path.name.startswith(('okto_nexus_connector-','okto_nexus_connector.')) or path.name in ('okto_nexus_connector','__pycache__'): continue
 target=site/path.name
 if path.is_dir(): shutil.copytree(path,target,dirs_exist_ok=True)
 else: shutil.copy2(path,target)
wheel=next((HERE/'wheels').glob('*.whl'))
run(['uv','pip','install','--python',HERE/'venv/Scripts/python.exe','--no-deps','--no-index',wheel])
versions=json.loads(subprocess.check_output(['rtk','proxy',sys.executable,'-c',
 "import importlib.metadata,json; print(json.dumps({n:importlib.metadata.version(n) for n in ('build','setuptools','wheel')}))"],text=True))
def pin(path): return {'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'bytes':path.stat().st_size}
record={'format':1,'connector_commit':commit,'archive':pin(archive),'wheel':pin(wheel),
 'source_date_epoch':env['SOURCE_DATE_EPOCH'],'build_python':sys.executable,'build_versions':versions,
 'dependencies_copied_from':str(BASE/'venv'),'new_prefix':str(HERE/'venv'),
 'core_wheel_unchanged':pin(BASE/'wheels/okto_nexus_connector_core-0.0.14-py3-none-any.whl'),
 'nexus_backend_wheel_unchanged':pin(BASE/'wheels/okto_nexus-0.3.3-py3-none-any.whl'),
 'live_campaign_modified':False,'provider_invoked':False,'published':False}
(HERE/'build-provenance.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
print(json.dumps(record))

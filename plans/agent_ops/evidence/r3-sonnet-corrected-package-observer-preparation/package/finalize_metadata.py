from pathlib import Path
import hashlib,importlib.metadata,json,os,shutil,subprocess,sys,tarfile
HERE=Path(__file__).resolve().parent
REPO=Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
BASE=Path('C:/Users/jpamb/AppData/Local/Temp/r3-connector-reconciliation-wheel-6pb8bst4')
COMMIT='c9c7e5b2e876c8b9eda52f47a072cd7a3a5af9b7'
def pin(p): return {'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size}
def run(args):
    env=os.environ.copy(); env['SOURCE_DATE_EPOCH']='1767225600'
    with (HERE/'build.log').open('ab') as log:
        subprocess.run(['rtk','proxy',*map(str,args)],env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
archive=HERE/'nexus-source.tar'
reused={'vendor/wheels/okto_nexus_connector_core-0.0.14-py3-none-any.whl':'ea1797805279667a5b39fdb6e9e6185ed8dcb958a1c7f98e91651e841754dca5','vendor/ci/okto_nexus_connector-0.0.12-py3-none-any.whl':'2b8ce688541a5ae6e9806467569be0743fef6ff607c763f2b93accf0f93e017d'}
record={'format':1,'nexus_commit':COMMIT,'connector_commit':'a8bd48bdc6d6e835c55eb601a7e7fa316453aa7b','core_commit':'497ee2b7a14b99c50cba97eac74f3b00d4863f26',
 'archive':pin(archive),'wheels':[pin(p) for p in sorted((HERE/'wheels').glob('*.whl'))],
 'reused_wheels':reused,'build_python':sys.executable,'build_versions':json.loads(subprocess.check_output(["rtk","proxy",sys.executable,"-c","import importlib.metadata,json; print(json.dumps({n:importlib.metadata.version(n) for n in ('build','setuptools','wheel')}))"],text=True)),
 'source_date_epoch':'1767225600','dependency_copy_source':str(BASE/'venv'),'new_prefix':str(HERE/'venv'),
 'home_build_reused_commit':'d3713c435ab2b853a2bb54feb77dc2161f28270b','home_review':pin(HERE/'home-review.json'),
 'scope':'Offline package composition only; no service, provider, campaign, credentials or plan activation.'}
(HERE/'build-provenance.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'status':'BUILT_ISOLATED','wheels':record['wheels']}))

from pathlib import Path
import hashlib, importlib.util, importlib.metadata, json, os, shutil, subprocess, sys, tarfile
HERE=Path(__file__).resolve().parent
REPOS=Path('D:/Projetos/Techridy')
sources={'core':('okto-nexus-connector-core','497ee2b7a14b99c50cba97eac74f3b00d4863f26'),
 'connector':('okto-nexus-connector','165a01f9c2acbc8e40388706f86534434968ed72'),
 'nexus':('okto_labs_okto_nexus',subprocess.check_output(['rtk','proxy','git','-C',str(REPOS/'okto_labs_okto_nexus'),'rev-parse','HEAD'],text=True).strip())}
env=os.environ.copy(); env['SOURCE_DATE_EPOCH']='1767225600'
def run(args,cwd=None,log='build.log'):
 with (HERE/log).open('ab') as f:
  subprocess.run(['rtk','proxy',*map(str,args)],cwd=cwd,env=env,stdout=f,stderr=subprocess.STDOUT,check=True)
for name,(repo,commit) in sources.items():
 root=HERE/(name+'-source'); root.mkdir()
 archive=HERE/(name+'-source.tar')
 run(['git','-C',REPOS/repo,'archive','--format=tar','--output='+str(archive),commit,'pyproject.toml','README.md','LICENSE','src','tests','tools'])
 with tarfile.open(archive) as t: t.extractall(root,filter='data')
 run([sys.executable,'-m','build','--wheel','--no-isolation','--outdir',HERE/'wheels',root])
spec=importlib.util.spec_from_file_location('normalize',HERE/'core-source/tools/build_artifacts.py')
module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
core=next((HERE/'wheels').glob('okto_nexus_connector_core-*.whl')); module._normalize_wheel(core)
original=Path('C:/Users/jpamb/AppData/Local/Temp/sonnet-canonical-recovery-proposal-7oq808_t/package/venv')
run(['uv','venv','--python',original/'Scripts/python.exe',HERE/'venv'])
site=HERE/'venv/Lib/site-packages'
for path in (original/'Lib/site-packages').iterdir():
 if path.name.startswith(('okto_nexus','nexus_connector_core')) or path.name=='__pycache__': continue
 target=site/path.name
 if path.is_dir(): shutil.copytree(path,target,dirs_exist_ok=True)
 else: shutil.copy2(path,target)
run(['uv','pip','install','--python',HERE/'venv/Scripts/python.exe','--no-deps','--no-index',*sorted((HERE/'wheels').glob('*.whl'))])
def pin(p): return {'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size}
record={'format':1,'sources':{n:{'repository':r,'commit':c,'archive':pin(HERE/(n+'-source.tar'))} for n,(r,c) in sources.items()},
 'build_python':sys.executable,'build_versions':{n:importlib.metadata.version(n) for n in ('build','setuptools','wheel')},
 'source_date_epoch':env['SOURCE_DATE_EPOCH'],'core_normalization':'archived tools/build_artifacts.py _normalize_wheel',
 'wheels':[pin(p) for p in sorted((HERE/'wheels').glob('*.whl'))],
 'dependency_origin':str(original),'dependency_copy_only':True,'campaign_environment_modified':False,
 'nexus_ui':'committed assets only; concurrent UI changes not included or qualified'}
(HERE/'build-provenance.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'status':'BUILT_INSTALLED_ISOLATED','sources':{n:c for n,(_,c) in sources.items()},'wheels':record['wheels']}))

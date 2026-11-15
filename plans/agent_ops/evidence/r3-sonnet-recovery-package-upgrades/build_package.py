"""Offline own-package builder. Requires final reviewed Connector commit; no services."""
from pathlib import Path
import argparse,json,hashlib,subprocess,os,tarfile,re,shutil,sys
HERE=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('--connector-commit',required=True);args=p.parse_args()
assert re.fullmatch('[0-9a-f]{40}',args.connector_commit)
P=json.loads((HERE/'package-build-plan.json').read_bytes());ROOT=Path(P['package_root'])
assert not ROOT.exists();ROOT.mkdir()
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def checked(pin):
 p=Path(pin['path']);assert sha(p)==pin['sha256'];return p
def run(label,argv,cwd=None,env=None):
 with (ROOT/(label+'.stdout')).open('xb') as out,(ROOT/(label+'.stderr')).open('xb') as err:
  cp=subprocess.run(argv,cwd=cwd or ROOT,env=env,stdin=subprocess.DEVNULL,stdout=out,stderr=err,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 assert cp.returncode==0,label+'_FAILED_OUTPUTS_PRESERVED'
prepare=checked(P['reuse_dependency_preparer']);shutil.copyfile(prepare,ROOT/'prepare_dependencies.py')
run('dependencies',[sys.executable,'-I','-B','-X','utf8',str(ROOT/'prepare_dependencies.py')])
python=ROOT/'venv/Scripts/python.exe';env=json.loads((ROOT/'environment.json').read_bytes())
archive=ROOT/'connector-source.tar'
run('archive',['git','-C',P['connector_repo'],'archive','--format=tar','--output='+str(archive),args.connector_commit])
source=ROOT/'connector-source';source.mkdir()
with tarfile.open(archive) as f:f.extractall(source,filter='data')
wheels=ROOT/'built-wheels';wheels.mkdir()
run('build-connector',[str(python),'-I','-B','-X','utf8','-m','pip','wheel','--no-deps','--no-build-isolation','--wheel-dir',str(wheels),str(source)],env=env)
for name,pin in P['unchanged_wheels'].items():shutil.copyfile(checked(pin),wheels/name)
expected={'okto_nexus-0.3.3-py3-none-any.whl','okto_nexus_connector-0.0.12-py3-none-any.whl','okto_nexus_connector_core-0.0.14-py3-none-any.whl'}
assert {x.name for x in wheels.glob('*.whl')}==expected
wheelpins={name:sha(wheels/name) for name in sorted(expected)}
installer=checked(P['reuse_installer_template']).read_text()
installer=re.sub(r'^SOURCE = .*$', lambda _: 'SOURCE = Path('+repr(str(wheels))+')',installer,flags=re.M)
installer=re.sub(r'^WHEELS = .*$', 'WHEELS = '+repr(wheelpins),installer,flags=re.M)
(ROOT/'install_packages.py').write_text(installer)
run('package-install',[str(python),'-I','-B','-X','utf8',str(ROOT/'install_packages.py')],env=env)
provenance={'connector_commit':args.connector_commit,'connector_archive_sha256':sha(archive),'wheels':wheelpins,'unchanged_wheel_source_pins':P['unchanged_wheels'],'installed_manifest_sha256':sha(ROOT/'installation.json'),'historical_package_mutated':False,'provider_calls':0,'services_started':0,'installed_regression_pending':True}
(ROOT/'build-provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
print(json.dumps(provenance))

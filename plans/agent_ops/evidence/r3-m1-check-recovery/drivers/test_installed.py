from pathlib import Path
import json,sys,subprocess,os
R=Path(__file__).parent
P=json.loads((R/'build-install-result.json').read_text())
group=sys.argv[1]
groups={'client':['tests/execution_r4/test_terminal_connect.py'],
 'adjacent':['tests/execution_r4/test_local_installation_check.py',
 'tests/execution_r4/test_terminal_identity.py::test_finish_creates_one_reviewed_identity_and_recovery_never_rotates_its_key',
 'tests/execution_r4/test_terminal_preset.py::test_local_update_recovers_original_test_and_finish_without_repeating_effects']}
assert group in groups
O=R/('installed-'+group);O.mkdir()
env=json.loads((R/'environment.json').read_text())
for key,name in [('USERPROFILE','userprofile'),('APPDATA','appdata'),('LOCALAPPDATA','localappdata'),('TEMP','tmp'),('TMP','tmp')]:
    p=O/name;p.mkdir(exist_ok=True);env[key]=str(p)
env['OKTO_NEXUS_NO_BANNER']='1'
argv=[P['python'],'-I','-X','utf8',str(Path(P['source'])/'tools/ci_installed.py'),'test','--wheel',P['wheel'],'--output',str(O/'canonical'),'--tests',*groups[group]]
(O/'command.json').write_text(json.dumps({'argv':argv,'isolated_home':True,'provider':False,'native_service_registration':False},indent=2))
with (O/'stdout.txt').open('xb') as out,(O/'stderr.txt').open('xb') as err:
    child=subprocess.Popen(argv,cwd=O,env=env,stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
    (O/'process.json').write_text(json.dumps({'pid':child.pid}))
    code=child.wait()
print(json.dumps({'group':group,'returncode':code,'output':str(O)}))
raise SystemExit(code)

from pathlib import Path
import hashlib,importlib.metadata as metadata,json,os,subprocess,sys,xml.etree.ElementTree as ET,zipfile
import okto_nexus,nexus_connector_core

R=Path(__file__).parent;candidate=R/'candidate';reports=R/'reports'
WHEEL=Path('C:/Users/jpamb/AppData/Local/Temp/dx04-mcp-guide-installed-sk13m28a/candidate-v1/wheels/okto_nexus-0.3.3-py3-none-any.whl')
EXPECTED='9b18dc0c69673bb730198ca461f2464c8ee4ae3fdc1226f22ffcb8140783412f'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(WHEEL)==EXPECTED
package=Path(okto_nexus.__file__).parent
assert 'site-packages' in package.parts and 'Techridy' not in str(package)
assert metadata.version('mcp')=='1.30.0'
with zipfile.ZipFile(WHEEL) as z:
    names=[n for n in z.namelist() if n.startswith('okto_nexus/') and not n.endswith('/')]
    for name in names:assert (package.parent/name).read_bytes()==z.read(name),name
proof={'wheel':str(WHEEL),'wheel_sha256':EXPECTED,'package_files_byte_identical':len(names),
       'python':sys.executable,'nexus_import':okto_nexus.__file__,'core_import':nexus_connector_core.__file__,
       'versions':{x:metadata.version(x) for x in ['okto-nexus','okto-nexus-connector','okto-nexus-connector-core','mcp','pytest']},
       'shared_environment_modified':False}
proof_text=json.dumps(proof,indent=2)+'\n'
if (reports/'installed-inputs.json').exists():
    assert (reports/'installed-inputs.json').read_text(encoding='utf-8')==proof_text
else:
    (reports/'installed-inputs.json').write_text(proof_text,encoding='utf-8')
attempt=sys.argv[1] if len(sys.argv)>1 else 'initial'
out=reports/attempt;out.mkdir(exist_ok=False)
env={k:v for k,v in os.environ.items() if not(k.startswith('OKTO_') or k in {'PYTHONPATH','PYTHONHOME'})}
env.update(PYTHONDONTWRITEBYTECODE='1',PYTHONUTF8='1',SVC_EVIDENCE_DIR=str(out),PYTEST_DISABLE_PLUGIN_AUTOLOAD='1')
tests=sys.argv[2:] or ['tests/test_service_failure_boundaries.py',
    'tests/test_serve_lock.py::test_failed_bootstrap_releases_both_locks',
    'tests/test_serve_lock.py::test_unavailable_lock_storage_reports_failure_without_bootstrap']
cmd=[sys.executable,'-I','-X','utf8','-m','pytest','-c',str(candidate/'pytest.ini'),
     '-p','no:cacheprovider','--basetemp',str(out/'pytest-temp'),'-q','--tb=short',
     '--junitxml',str(out/'tests.xml'),*tests]
before={str(p.relative_to(candidate)):sha(p) for p in candidate.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
(out/'input-hashes.json').write_text(json.dumps(before,indent=2)+'\n',encoding='utf-8')
with (out/'stdout-private.txt').open('wb') as log:
    result=subprocess.run(cmd,cwd=candidate,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,timeout=240)
after={str(p.relative_to(candidate)):sha(p) for p in candidate.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
assert before==after
cases=[]
if (out/'tests.xml').exists():
    for c in ET.parse(out/'tests.xml').iter('testcase'):
        status='failed' if c.find('failure') is not None else 'error' if c.find('error') is not None else 'skipped' if c.find('skipped') is not None else 'passed'
        cases.append({'classname':c.get('classname'),'name':c.get('name'),'status':status})
summary={'exit':result.returncode,'command':cmd,'cwd':str(candidate),'source_files_unchanged':before,
         'cases':cases,'counts':{s:sum(c['status']==s for c in cases) for s in ['passed','failed','error','skipped']},
         'raw_xml_sha256':sha(out/'tests.xml') if (out/'tests.xml').exists() else None}
(out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'directory':str(out),'exit':result.returncode,'counts':summary['counts'],'failed_cases':[c['name'] for c in cases if c['status'] in ['failed','error']]},indent=2))

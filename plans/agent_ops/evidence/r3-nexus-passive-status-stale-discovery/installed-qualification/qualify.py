from pathlib import Path
import asyncio,base64,csv,hashlib,importlib,importlib.metadata,io,json,re,subprocess,sys,zipfile
HERE=Path(__file__).resolve().parent
REPO=Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
OLD=Path('C:/Users/jpamb/AppData/Local/Temp/r3-core-consumer-integration-h_elhexb/wheels/okto_nexus-0.3.3-py3-none-any.whl')
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def pin(p): return {'path':p.relative_to(HERE).as_posix(),'sha256':sha(p),'bytes':p.stat().st_size}
assert Path(sys.prefix).resolve()==(HERE/'venv').resolve()
packages=[('okto-nexus','okto_nexus','0.3.3'),('okto-nexus-connector','okto_nexus_connector','0.0.12'),('okto-nexus-connector-core','nexus_connector_core','0.0.14')]
origins={}; payload_count=0; record_count=0
for distribution,module,version in packages:
    assert importlib.metadata.version(distribution)==version
    package=Path(importlib.import_module(module).__file__).resolve().parent
    assert package.is_relative_to(Path(sys.prefix).resolve())
    wheel=HERE/'wheels'/(distribution.replace('-','_')+'-'+version+'-py3-none-any.whl')
    with zipfile.ZipFile(wheel) as z:
        record=next(n for n in z.namelist() if n.endswith('.dist-info/RECORD'))
        for name,digest,size in csv.reader(io.StringIO(z.read(record).decode())):
            if not digest: assert name==record; continue
            algorithm,expected=digest.split('=',1); assert algorithm=='sha256'
            data=z.read(name)
            assert base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b'=').decode()==expected
            assert len(data)==int(size); record_count+=1
        for name in z.namelist():
            if name.startswith(module+'/') and not name.endswith('/'):
                assert (package/name.split('/',1)[1]).read_bytes()==z.read(name); payload_count+=1
    origins[module]={'path':str(package),'version':version,'wheel_sha256':sha(wheel)}
nexus=HERE/'wheels/okto_nexus-0.3.3-py3-none-any.whl'
static_prefix='okto_nexus/adapters/inbound/http/static/'
with zipfile.ZipFile(OLD) as old,zipfile.ZipFile(nexus) as new:
    def backend(z): return {n:z.read(n) for n in z.namelist() if n.startswith('okto_nexus/') and not n.startswith(static_prefix) and not n.endswith('/')}
    previous,current=backend(old),backend(new)
    changed={name for name in set(previous)|set(current) if previous.get(name)!=current.get(name)}
    assert changed=={'okto_nexus/bootstrap/local_discovery.py','okto_nexus/adapters/inbound/cli/service.py'}
    source=HERE/'nexus-source/src'
    source_files={p.relative_to(source).as_posix():p for p in (source/'okto_nexus').rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    wheel_files={n for n in new.namelist() if n.startswith('okto_nexus/') and not n.endswith('/')}
    assert set(source_files)==wheel_files
    for name,p in source_files.items(): assert p.read_bytes()==new.read(name)
    static={n:new.read(n) for n in wheel_files if n.startswith(static_prefix)}
    assert static and any(n.endswith('.sql') for n in wheel_files)
subprocess.run(['rtk','proxy','git','-C',str(REPO),'diff','--exit-code','d3713c435ab2b853a2bb54feb77dc2161f28270b','2c59abf1a06804dadfc32a789b7cdd5add79d4ba','--','src/okto_nexus/adapters/inbound/http/static'],check=True,capture_output=True)
package=Path(origins['okto_nexus']['path']); static_root=package/'adapters/inbound/http/static'
index=(static_root/'index.html').read_text()
refs=re.findall(r'(?:src|href)="(/[^"?#]+)"',index)
assert any(p.endswith('.js') for p in refs) and any(p.endswith('.css') for p in refs)
async def resource_checks():
    from starlette.staticfiles import StaticFiles
    app=StaticFiles(directory=static_root,html=True)
    results=[]
    for path in ['index.html',*[p.lstrip('/') for p in refs]]:
        response=await app.get_response(path,{'type':'http','method':'GET','path':'/'+path,'headers':[]})
        assert response.status_code==200 and Path(response.path).resolve()==(static_root/path).resolve()
        assert Path(response.path).is_file()
        results.append({'path':path,'status':response.status_code,'media_type':response.media_type,'sha256':sha(Path(response.path))})
    from starlette.exceptions import HTTPException
    try:
        missing=await app.get_response("assets/nonexistent-qualification.js",{"type":"http","method":"GET","path":"/assets/nonexistent-qualification.js","headers":[]})
    except HTTPException as exc:
        assert exc.status_code==404
    else:
        assert missing.status_code==404
    return results
resources=asyncio.run(resource_checks())
import xml.etree.ElementTree as ET
case_nodes=ET.parse(HERE/'installed.xml').getroot().findall('.//testcase')
assert len(case_nodes)==12 and all(not any(c.find(n) is not None for n in ('failure','error','skipped')) for c in case_nodes)
actual=json.loads((HERE/'real-status-projection.json').read_text())
assert actual['exit_code']==0 and actual['state']=='stopped' and actual['reason'] in {'NO_SERVICE_OWNER','SHUTDOWN_COMPLETE'} and actual['context_unchanged']
qualification={'installed_focal_cases':12,'real_status_projection_sha256':sha(HERE/'real-status-projection.json'),'format':1,'status':'OFFLINE_COMPOSITION_QUALIFIED','origins':origins,'payloads_equal':payload_count,'record_hashes_equal':record_count,
 'nexus_source_payloads_equal':len(source_files),'backend_payloads_equal_to_prior_qualified_wheel':len(current)-len(changed),'expected_backend_delta':sorted(changed),'prior_nexus_wheel_sha256':sha(OLD),
 'home_static_payloads':len(static),'home_static_equals_qualified_commit':'d3713c435ab2b853a2bb54feb77dc2161f28270b',
 'static_resources':resources,'missing_static_resource_status':404,'build_provenance_sha256':sha(HERE/'build-provenance.json'),
 'scope':'Byte/resource/origin composition verification only. StaticFiles in process; no application bootstrap, services, provider, credentials, campaign writes or activated successor plan. Separate canonical CLI status against the stopped owned home is read-only with context bytes unchanged.',
 'inherited_qualification':'Prior installed qualification: 98 unique cases = 48 Core + 44 Nexus + 6 Connector. Current Connector qualification: 46 unique source cases and 24 installed cases (a subset), with overlap with historical cases; these counts are not additive. Home: 41 source and synthetic UI cases. No broad regression suite rerun; new12case focal installed suite is reported separately. No new acceptance claimed.',
 'command':'rtk proxy '+str(HERE/'venv/Scripts/python.exe')+' -I -B -X utf8 '+str(HERE/'qualify.py')}
(HERE/'qualification.json').write_text(json.dumps(qualification,indent=2)+'\n',encoding='utf-8')
installation={'format':1,'prefix':str(HERE/'venv'),'python':str(HERE/'venv/Scripts/python.exe'),'wheels':[pin(p) for p in sorted((HERE/'wheels').glob('*.whl'))],'origins':origins,'qualification_sha256':sha(HERE/'qualification.json'),'prospective_only':True}
(HERE/'installation.json').write_text(json.dumps(installation,indent=2)+'\n',encoding='utf-8')
files=['status_readonly-initial.py','status-classification-note.json','build.py','qualify.py','build-provenance.json','home-review.json','home-manifest.json','qualification.json','installation.json','run_installed.py','installed.xml','status_readonly.py','real-status-projection.json']
(HERE/'public-allowlist.json').write_text(json.dumps({'files':[pin(HERE/n) for n in files]},indent=2)+'\n',encoding='utf-8')
print(json.dumps({'status':qualification['status'],'payloads':payload_count,'qualification_sha256':sha(HERE/'qualification.json'),'installation_sha256':sha(HERE/'installation.json'),'allowlist_sha256':sha(HERE/'public-allowlist.json')}))

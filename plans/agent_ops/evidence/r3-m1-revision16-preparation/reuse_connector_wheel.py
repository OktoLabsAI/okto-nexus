"""Bind unchanged installed payload to the prior immutable Connector ZIP, retaining build history."""
from pathlib import Path
import hashlib,json,zipfile
H=Path(__file__).resolve().parent;P=H/'package';OLD=H.with_name('work-revision15')/'package'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())
def save(p,v):p.write_text(json.dumps(v,indent=2)+'\n',encoding='utf-8')
name='okto_nexus_connector-0.0.12-py3-none-any.whl'
source=OLD/'wheels'/name;assert sha(source)=='f9864f13db4c5e6e5afdfd8f28ca5384512a17a1f8efb1897cb3a4d810d43cf4'
installed=read(P/'installation.json');built=read(P/'build-provenance.json')
prior=installed['wheels'][name];assert sha(Path(prior['path']))==prior['sha256']
checked=0
with zipfile.ZipFile(source) as z:
    for member in z.namelist():
        if member.endswith('/') or member.endswith('.dist-info/RECORD'):continue
        path=P/'venv/Lib/site-packages'/member
        assert path.resolve().is_relative_to((P/'venv/Lib/site-packages').resolve())
        assert path.read_bytes()==z.read(member),member;checked+=1
for filename in ('installation.json','build-provenance.json'):
    target=P/('initial-'+filename);assert not target.exists();target.write_bytes((P/filename).read_bytes())
(P/'wheels'/name).write_bytes(source.read_bytes())
installed['pip_installed_wheels_before_equivalence_binding']={k:dict(v) for k,v in installed['wheels'].items()}
installed['pip_installed_wheels_before_equivalence_binding'][name]['path']=str(P/'built-wheels'/name)
installed['wheels'][name]['sha256']=sha(source)
installed['reused_connector_payload_qualification']={'source':str(source),'sha256':sha(source),'verified_payloads':checked,
 'initial_installation_sha256':sha(P/'initial-installation.json'),'initial_build_provenance_sha256':sha(P/'initial-build-provenance.json'),
 'pip_reexecuted':False,'installed_payloads_changed':False,'zip_metadata_identity_not_assumed':True}
save(P/'installation.json',installed)
built['wheels'][name]=sha(source);built['installation_sha256']=sha(P/'installation.json')
built['initial_build_provenance_sha256']=sha(P/'initial-build-provenance.json')
built['unchanged_connector_reused']=installed['reused_connector_payload_qualification']
save(P/'build-provenance.json',built)
print(json.dumps({'connector_sha256':sha(source),'payloads_verified':checked,'installation_sha256':sha(P/'installation.json')}))

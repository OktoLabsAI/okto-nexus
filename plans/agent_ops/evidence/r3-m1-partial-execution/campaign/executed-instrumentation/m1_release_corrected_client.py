from pathlib import Path
import hashlib,json,time
from okto_nexus.adapters.outbound.terminal_http import LocalOperatorHTTP
from okto_nexus.application.terminal_connection import TerminalConnection
root=Path('C:/Users/jpamb/AppData/Local/Temp/r3-campaign-refresh-0ssbo8pb/m1-campaign')
repo=Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
pin=json.loads((root/'public/client-runtime-pin.prepared.json').read_text())
source=Path(pin['python_prefix'])/'Lib/site-packages/okto_nexus/application/terminal_connection.py'
assert hashlib.sha256(source.read_bytes()).hexdigest()==pin['terminal_connection_sha256']
import okto_nexus,sys
assert Path(sys.prefix).resolve()==Path(pin['python_prefix']).resolve()
assert Path(okto_nexus.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())
profile=root/'nexus-home/terminal/profiles/m1-local.json'
original=profile.read_bytes(); doc=json.loads(original)
assert doc['state']=='done'
flow=TerminalConnection(LocalOperatorHTTP(host='127.0.0.1',port=64507,timeout=2),lambda _:(_ for _ in ()).throw(AssertionError('No profile writes')))
value=flow.observe(doc)
assert value['state']=='configured' and value['server_id']==doc['server_id'] and value['binding_id']==doc['result']['binding']['binding_id']
assert profile.read_bytes()==original
controller=json.loads((root/'private/controller.json').read_text())
assert len(controller['requests'])==1 and controller['requests']['m1-local-setup']['monitor']['high_water']==22775
assert controller['requests']['m1-local-setup']['settled'] and not controller['faults']
for name in ('qualification.json','package-proof.json'):
    p=repo/'plans/agent_ops/evidence/r3-m1-path-normalization'/name
    pin[name+'_sha256']=hashlib.sha256(p.read_bytes()).hexdigest()
pin.update(qualification_status='QUALIFIED',root_execution_release=True,released_at=time.time(),
           release_basis='Explicit root release after source14 and installed14 passed; original Server package retained.')
with (root/'public/client-runtime-pin.json').open('x') as f:json.dump(pin,f,indent=2)
report={'state':value['state'],'server_id':value['server_id'],'binding_id':value['binding_id'],
        'profile_bytes_unchanged':True,'recovery':'GET_ONLY','new_setup':False,'reservations':1,'observed_tokens':22775,'split_build':True}
(root/'public/corrected-client-readonly-resume.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report))

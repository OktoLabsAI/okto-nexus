from pathlib import Path
import json
from okto_nexus.adapters.outbound.terminal_http import LocalOperatorHTTP
from okto_nexus.application.terminal_connection import TerminalConnection
root=Path('C:/Users/jpamb/AppData/Local/Temp/r3-campaign-refresh-0ssbo8pb/m1-campaign')
doc=json.loads((root/'nexus-home/terminal/profiles/m1-local.json').read_text())
flow=TerminalConnection(LocalOperatorHTTP(host='127.0.0.1',port=64507,timeout=2),lambda _:None)
me=flow.api('GET','/connections/me')
assert me['server_id']==doc['server_id']
binding=doc['result']['binding']['binding_id']
value=flow.current('m1-local',binding)
match=next((r for r in value['connections'] if r['binding_id']==binding),None)
selected=doc['selection']
observed={'state':doc['state'],'server_id':me['server_id'],'binding_id':binding,
          'selection':{k:selected.get(k) for k in ('client','project','workspace_id','candidate_ref','provider_home')},
          'connection':match,'folders':value.get('folders'),
          'read_only':True,'new_provider_dispatch':False}
(root/'public/profile-drift-readonly.json').write_text(json.dumps(observed,indent=2))
print(json.dumps(observed))

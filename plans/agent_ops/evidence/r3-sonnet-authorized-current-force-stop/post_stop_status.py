from pathlib import Path
import json,time
from okto_nexus.adapters.outbound.service_manager.inspection import inspect_local_server
from okto_nexus_connector.daemon import manager

base=Path('C:/Users/jpamb/AppData/Local/Temp/m1-v12-bundle-bldo9qy7/campaign')
home=base/'nexus-home'
value={'observed_at':time.time(),'nexus':inspect_local_server(home=home,database=home/'nexus.db',host='127.0.0.1',port=58631,timeout=5),
       'connector':manager.status(base/'connector-state',timeout=5).to_json(),
       'provider_calls':0,'control_calls':0,'data_deletion':False}
out=Path(__file__).resolve().parent/'public/post-stop-status.json'
with out.open('x',encoding='utf-8') as f:json.dump(value,f,indent=2);f.write('\n')
print(json.dumps(value))

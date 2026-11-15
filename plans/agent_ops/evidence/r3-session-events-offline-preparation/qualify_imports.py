from pathlib import Path
import hashlib,inspect,json,sys
from okto_nexus.adapters.outbound.service_manager.installation import ServerInstallation
from okto_nexus.adapters.outbound.service_manager.inspection import inspect_local_server
from okto_nexus.adapters.outbound.service_manager.supervision import read_record
from okto_nexus_connector.platform.user_service import UserService
from okto_nexus_connector.platform.service_supervision import read_cycle
from okto_nexus_connector.daemon.manager import status
from nexus_connector_core.user_service_definition import windows_definition_digest
import win32security
HERE=Path(__file__).resolve().parent
P=json.loads((HERE/'plan.json').read_bytes())
assert Path(sys.prefix).resolve()==Path(P['python_prefix']).resolve()
items=[ServerInstallation,inspect_local_server,read_record,UserService,read_cycle,status,windows_definition_digest]
rows=[]
for value in items:
 p=Path(inspect.getsourcefile(value));assert p.is_relative_to(Path(sys.prefix))
 rows.append({'symbol':value.__name__,'source':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'signature':str(inspect.signature(value))})
assert callable(win32security.LsaGetLogonSessionData)
result={'status':'INSTALLED_IMPORT_SIGNATURES_CONFIRMED','python':sys.executable,'prefix':sys.prefix,'symbols':rows,
 'native_windows_calls':0,'services':0,'provider_calls':0,'qualification_limit':'Imports/signatures only, not real session-event execution.'}
with (HERE/'import-qualification.json').open('x',encoding='utf-8') as f:json.dump(result,f,indent=2)
print(json.dumps({'status':result['status'],'symbols':len(rows),'native_windows_calls':0}))

from pathlib import Path
import sys,json,hashlib,os,importlib.util,time
C=Path(__file__).resolve().parent
sys.path.insert(0,str(C))
from transfer_compat_context import TransferContext
X=TransferContext(C/'transfer-plan.json','e56ae6fc22d5af02adc9687aaa8ee476846c1d7e09e43c030109cf9ec71820cd')
from okto_nexus_connector.cli.main import build_parser
from okto_nexus_connector.cli.commands.connect_setup import _check_choices
from okto_nexus_connector.services import remote_setup as setup
from okto_nexus_connector.identity.vault import vault_backend_names
statepath=Path(X.P['paths']['connector_state'])/'state.json'
state=json.loads(statepath.read_bytes());record=state['preferences']['remote-setup.m1-sonnet-remote-setup-01']
hand=json.loads((C/'public/sonnet-host-handoff.json').read_bytes())
args=build_parser().parse_args(['--json','--state-dir',X.P['paths']['connector_state'],'connect','--setup-receipt',str(C/'public/sonnet-host-handoff.json'),'--alias','m1-sonnet-remote','--credential-stdin','--no-start-at-login'])
result={'method':'READ_ONLY_INSTALLED_PRE_KEY_VALIDATION_NO_VAULT_RESOLVE_NO_HTTP','stages':{},'identities_count':len(state['identities']),'bindings_count':len(state['bindings']),'setup_stage':record['stage'],'identity_alias_present':record['identity_alias'] is not None}
for name,fn in [('validate_handoff',lambda:setup.validate_handoff(hand,record)),('check_choices',lambda:_check_choices(args,record|{'handoff':hand})),('validate_local',lambda:setup.validate_local(record))]:
 started=time.monotonic()
 try:fn();result['stages'][name]={'status':'PASS'}
 except Exception as e:result['stages'][name]={'status':'REFUSED','error_type':type(e).__name__,'code':getattr(e,'code',None)}
 result['stages'][name]['elapsed_seconds']=time.monotonic()-started
# Public backend capability names only; no vault open, key read/write, or namespace enumeration.
result['vault_backend_names']=vault_backend_names()
result['fallback_approved']=bool(state['preferences'].get('vault.fallback_file.approved',False))
result['consumer_env_forces_file_vault']='OKTO_NEXUS_CONNECTOR_VAULT' in X.connector_env()
result['source_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
(C/'transfer-prekey-diagnosis.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))

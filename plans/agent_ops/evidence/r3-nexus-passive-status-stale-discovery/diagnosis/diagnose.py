from pathlib import Path
import hashlib,json,traceback
from okto_nexus.adapters.inbound.cli.service import resolve_local_service
from okto_nexus.adapters.outbound.service_manager.context import read_json,validate_context
HOME=Path('C:/Users/jpamb/AppData/Local/Temp/m1-v12-bundle-bldo9qy7/campaign/nexus-home')
OUT=Path(__file__).resolve().parent
def error_projection(exc):
    return {'class':type(exc).__name__,'code':str(getattr(exc,'code','UNCLASSIFIED')),
        'frames':[{'file':Path(f.filename).name,'function':f.name,'line':f.lineno} for f in traceback.extract_tb(exc.__traceback__)]}
result={'scope':'resolve_only_no_inspect_or_control','home_exists':HOME.is_dir()}
p=HOME/'service-context.json'
result['context_exists']=p.is_file()
if p.is_file():
    result['context_sha256']=hashlib.sha256(p.read_bytes()).hexdigest()
    try:
        value=read_json(p); validate_context(value,require_paths=False)
        result['context_validation']='PASS'
        result['context_revision']=value['revision']
        result['upgrade_pending']=bool(value.get('upgrade_pending'))
        result['argument_flag_names']=[x for x in value['arguments'] if x.startswith('--')]
        result['paths_exist']={key:Path(value[key]).exists() for key in ('executable','environment_prefix','cwd')}
    except Exception as exc: result['context_validation']=error_projection(exc)
try:
    resolve_local_service(['--home',str(HOME)],action='status')
    result['resolve']='PASS'
except Exception as exc: result['resolve']=error_projection(exc)
(OUT/'diagnosis.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result))

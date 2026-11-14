from pathlib import Path
from types import SimpleNamespace
import hashlib,json,sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from request_context import gate
amendment=HERE/'amendment.json';digest=hashlib.sha256(amendment.read_bytes()).hexdigest()
context=gate(SimpleNamespace(amendment=str(amendment),expected_amendment_sha256=digest))
assert Path(context.installed['python_prefix'])==HERE/'package/venv'
assert context.P['request_ids']['work']==['m1v14-local-work-12','m1v14-local-work-13']
assert context.P['controller_preparation']['policy']['carry_in_tokens']==272648
assert context.P['controller_preparation']['policy']['carry_in_admissions']==11
assert not context.PUBLIC.exists() and not context.PRIVATE.exists()
result={'status':'COMPOSED_GATE_PASS','amendment_sha256':digest,'python':sys.executable,'prefix':sys.prefix,
    'payloads':context.installed['payload_count'],'policy':context.P['controller_preparation']['policy'],
    'runtime_controller_created':False,'service_actions':0,'provider_calls':0,'grant_changes':0}
with (HERE/'gate-qualification.json').open('x',encoding='utf-8') as output:json.dump(result,output,indent=2)
print(json.dumps(result))

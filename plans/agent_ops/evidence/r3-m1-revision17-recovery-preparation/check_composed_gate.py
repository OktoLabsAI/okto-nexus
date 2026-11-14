"""Read-only composed entry and exact work-import prefix qualification."""
from pathlib import Path
from types import SimpleNamespace
import ast,hashlib,json,sys
H=Path(__file__).resolve().parent
sys.path.insert(0,str(H))
from request_context import gate
path=H/'amendment.json';digest=hashlib.sha256(path.read_bytes()).hexdigest()
context=gate(SimpleNamespace(amendment=str(path),expected_amendment_sha256=digest))
sys.path.insert(0,str(context.modules))
import controller,independent_controller,legacy_controller
assert controller.POLICY==independent_controller.POLICY==legacy_controller.POLICY==context.amendment['policy']
# Execute the exact work module prefix through the once-broken facade import.
# Stop before runtime setup, service construction, controller construction or handlers.
source=(H/'local_work.py').read_text(encoding='utf-8');tree=ast.parse(source)
prefix=[]
for node in tree.body:
    prefix.append(node)
    if isinstance(node,ast.ImportFrom) and node.module=='controller':break
else:raise AssertionError('FACADE_IMPORT_NOT_FOUND')
namespace={'__file__':str(H/'local_work.py'),'__name__':'qualification_prefix'}
exec(compile(ast.Module(body=prefix,type_ignores=[]),str(H/'local_work.py'),'exec'),namespace)
assert namespace['X'] is context and namespace['POLICY']==context.amendment['policy']
assert not context.PUBLIC.exists() and not context.PRIVATE.exists()
value={'status':'COMPOSED_GATE_AND_REAL_WORK_FACADE_IMPORT_PASS','amendment_sha256':digest,
 'python':sys.executable,'prefix':sys.prefix,'payloads':context.installed['payload_count'],
 'policy':context.amendment['policy'],'work_import_prefix_executed':True,'handler_executed':False,
 'runtime_controller_created':False,'service_actions':0,'provider_calls':0,'grant_changes':0,
 'runtime_namespace_created':False,'remote_selectors_enabled':False}
with (H/'gate-qualification.json').open('x',encoding='utf-8') as f:json.dump(value,f,indent=2)
print(json.dumps(value))

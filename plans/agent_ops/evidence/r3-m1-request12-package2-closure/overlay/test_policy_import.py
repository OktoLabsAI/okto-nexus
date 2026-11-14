"""Actual module imports reproduce the missed facade assertion and qualify the one-line overlay."""
from pathlib import Path
import ast,hashlib,json,sys
H=Path(__file__).resolve().parent
B=Path('C:/Users/jpamb/AppData/Local/Temp/m1-v12-bundle-bldo9qy7/successor14/work-request12-package2')
sys.path.insert(0,str(B/'modules'))
import legacy_controller,independent_controller
try:
    import controller
except AssertionError:
    old_facade_failed=True
else:raise AssertionError('Original mismatch not reproduced')
assert legacy_controller.POLICY==independent_controller.POLICY==json.loads((B/'amendment.json').read_bytes())['policy']
source=(B/'local_work.py').read_bytes();overlay=(H/'local_work.py').read_bytes()
assert overlay==source.replace(b'from controller import POLICY',b'from legacy_controller import POLICY')
statement=next(node for node in ast.parse(overlay.decode()).body if isinstance(node,ast.ImportFrom) and node.module=='legacy_controller')
namespace={};exec(compile(ast.Module(body=[statement],type_ignores=[]),'<real-policy-import>','exec'),namespace)
assert namespace['POLICY']==legacy_controller.POLICY
value={'status':'PASS','tests':1,'original_facade_assertion_reproduced':old_facade_failed,
    'actual_overlay_policy_import_passed':True,'policy':namespace['POLICY'],
    'work_source_exact_one_line_delta':True,'controller_created':False,'model_calls':0,'service_actions':0,
    'original_module_sha256':hashlib.sha256((B/'modules/controller.py').read_bytes()).hexdigest(),
    'overlay_sha256':hashlib.sha256(overlay).hexdigest()}
with (H/'qualification.json').open('x',encoding='utf-8') as out:json.dump(value,out,indent=2)
print(json.dumps(value))

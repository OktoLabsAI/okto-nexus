"""Inspect only the selected W12 package; never select upgrade/service effects."""
import hashlib
import json
from pathlib import Path
import sys
import time

HERE=Path(__file__).resolve().parent
W=Path('C:/Users/jpamb/AppData/Local/Temp/m1-v12-bundle-bldo9qy7/successor14/work-request12')
EXPECTED=W/'package/venv/Scripts/python.exe'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def error_info(error):
    out={'type':type(error).__name__}
    for key in ('errno','winerror','timeout','returncode'):
        value=getattr(error,key,None)
        if type(value) in (int,float):out[key]=value
    filename=getattr(error,'filename',None)
    if filename:
        try:out['selected_package_relative_file']=str(Path(filename).resolve().relative_to(W.resolve()))
        except ValueError:out['file_outside_selected_package']=True
    return out

def main():
    assert sys.flags.isolated and sys.flags.dont_write_bytecode and sys.flags.utf8_mode
    assert Path(sys.executable).resolve()==EXPECTED.resolve()
    from okto_nexus import service_environment as module
    assert Path(module.__file__).resolve().is_relative_to((W/'package/venv').resolve())
    source_hash=sha(module.__file__)
    plan_path=W/'private/environment-upgrade-plan.json'
    plan=json.loads(plan_path.read_bytes());candidate=plan['plan']['candidate']
    stages=[];original=module._distribution
    def measured(name,package):
        start=time.monotonic()
        try:
            value=original(name,package)
        except BaseException as error:
            stages.append({'distribution':name,'elapsed_seconds':time.monotonic()-start,'error':error_info(error)})
            raise
        stages.append({'distribution':name,'elapsed_seconds':time.monotonic()-start,'status':'OK','version':value['version'],'digest':value['digest']})
        return value
    module._distribution=measured
    started=time.monotonic()
    result={'mode':'DIRECT_SNAPSHOT_NO_UPGRADE','plan_sha256':sha(plan_path),'source_sha256':source_hash,
        'isolated':True,'dont_write_bytecode':True,'utf8_mode':True,'services_started':False,'providers_accessed':False}
    try:
        value=module.snapshot()
        result.update(status='SNAPSHOT_OK',matches_reviewed_candidate=value==candidate,
            snapshot_sha256=hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest())
    except BaseException as error:
        result.update(status='SNAPSHOT_ERROR',error=error_info(error))
    result['elapsed_seconds']=time.monotonic()-started;result['stages']=stages
    assert sha(module.__file__)==source_hash
    with (HERE/'snapshot-result.json').open('x',encoding='utf-8',newline='\n') as out:
        json.dump(result,out,indent=2);out.write('\n')
    print(json.dumps(result))

if __name__=='__main__':main()

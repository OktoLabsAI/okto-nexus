from pathlib import Path
import json, subprocess, sys, time
sys.path.insert(0,'C:/Users/jpamb/AppData/Local/Temp')
from m1_real_lifecycle import P,C,ROOT,env
argv=C['steps'][0]['argv'][:5]+['connect','--profile','m1-local','--client','codex','--project',P['paths']['local_project'],
    '--candidate-ref',P['native_selection']['candidate_ref'],'--provider-home',P['provider_context']['provider_home'],
    '--new-agent','m1-local','--plan','--json']+C['service_selection_args']
with (ROOT/'private'/'local-plan.stdout').open('xb') as out,(ROOT/'private'/'local-plan.stderr').open('xb') as err:
    started=time.time()
    child=subprocess.Popen(argv,cwd=ROOT,env=env(),stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
    code=child.wait()
value=json.loads((ROOT/'private'/'local-plan.stdout').read_text(encoding='utf-8'))
# The plan is a canonical no-secret review; no submitted key material exists.
(ROOT/'public'/'local-plan.json').write_text(json.dumps({'started':started,'finished':time.time(),'exit':code,'review':value},indent=2))
print(json.dumps({'exit':code,'review':value}))

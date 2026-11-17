from pathlib import Path
import json,shutil,hashlib
root=Path(__file__).resolve().parents[4];dest=Path(__file__).parent;out=root/'output/playwright/ui11-viewer-guard'
ctl=json.loads((out/'control.json').read_text())
shutil.copy2(Path(ctl['control'])/'ready.json',dest/'before-ready.json')
shutil.copy2(out/'auto-scroll-close.png',dest/'before-auto-scroll-close.png')
shutil.copy2(out/'probe.js',dest/'before-probe.js')
data={'status':'DEFECT_CONFIRMED_FIX_SOURCE_FROZEN_AWAITING_BUILT_BROWSER','before_bundle':'index-BXpHvePH.js','before_cli_tool':'10faee','bug':'Read-only Auto-scroll change fabricates captured draft dirty; Close prompts Discard unsaved changes','fix':'data-modal-passive on SessionExecutionPanel read-only section only','node_tests':{'passed':11,'failed':0,'tool':'d4dc1d','files':['uiSessionInspection.test.mjs','modalChanges.test.mjs'],'limit':'SSR boundary plus canonical sibling markup and pure dirty guards; browser after build pending'},'cleanup':{'browser_pid':57300,'close_exit':0,'fixture_session':71905,'fixture_exit':0,'pid_absent':True,'listener51714_absent':True,'shared_wss_lifespan_factory':'CLOSED'}}
(dest/'before-qualification.json').write_text(json.dumps(data,indent=2),encoding='utf-8')
print(hashlib.sha256((dest/'before-qualification.json').read_bytes()).hexdigest())

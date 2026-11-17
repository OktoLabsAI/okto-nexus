from pathlib import Path
import json
import shutil

here=Path(__file__).resolve().parent
root=here.parents[3]
out=root/'output/playwright/r3-harness-board'
control=Path('C:/Users/jpamb/AppData/Local/Temp/nexus-r3-harness-control-l4urvcyp')
dest=here/'antecedent-expired-phase2'
dest.mkdir(exist_ok=True)
for name in ('ready.json','actions.json','cleanup.json','peer-status.json','parallel-added.json'):
    shutil.copy2(control/name,dest/name)
for path in out.iterdir():
    if path.is_file() and path.name!='control.json':shutil.copy2(path,dest/path.name)
for name in ('phase1-cli.txt','phase1-complete-cli.txt','phase2-cli.txt'):
    shutil.copy2(here/name,dest/name)
(dest/'limit.json').write_text(json.dumps({'status':'PARTIAL_ANTECEDENT_NATIVE_REQUEST_EXPIRED_BEFORE_PHASE2','first_phase_checks_pass':5,'first_phase_completion_checks_pass':3,'first_phase_harness_error':'Expected /handoffs/id but actual canonical UI uses /handoffs?handoff_id=...; actual GET200 preserved.','second_phase':'Harness working/blocksfalse shown, but initial120second question expired before parallel read fact at04:13:24.503Z. No TTL/authority change or replay performed.','fixture_exit_code':0,'fixture_exit_tool':'621b15','physical_exit_tool':'8156c5','fixture58152_absent':True,'listener60106_absent':True,'browser':'Own existing named technical CLI retained for the next fresh origin; no concurrent extra browser.','provider_calls':0,'POST':0},indent=2),encoding='utf-8')
print(json.dumps({'preserved_files':sum(p.is_file() for p in dest.iterdir())}))

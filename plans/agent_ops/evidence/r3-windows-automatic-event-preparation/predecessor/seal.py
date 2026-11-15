from pathlib import Path
import hashlib,json,ast
HERE=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(name,value):
    with (HERE/name).open('x',encoding='utf-8',newline='\n') as f:json.dump(value,f,indent=2,sort_keys=True);f.write('\n')
sources=['automation_contract.py','collect.py','select_event.py','prepare_artifacts.py','run_tests.py','test_contract.py','test_collect.py','seal.py']
for name in sources:ast.parse((HERE/name).read_text(encoding='utf-8'))
test=json.loads((HERE/'test-result.json').read_bytes());assert (test['tests'],test['failures'],test['errors'])==(8,0,0)
plan=json.loads((HERE/'plan-template.json').read_bytes());assert plan['selected_event'] is None and plan['reviewed_for_execution'] is False
for pin in plan['read_only_dependencies']:assert sha(Path(pin['path']))==pin['sha256']
assert not (HERE/'selections').exists()
save('qualification.json',{'status':'OFFLINE_PREPARATION_QUALIFIED_UNSELECTED','test_result':test,'tests_tool':'435b60',
    'command':'rtk proxy C:/Users/jpamb/AppData/Local/Temp/r3-status-fixed-campaign-package-ddwnb5vx/venv/Scripts/python.exe -I -B -X utf8 '+str(HERE/'run_tests.py'),
    'read_only_capability_tool':'3d5237','read_only_capability_exit':0,'wmi_release_warning_preserved':True,
    'runtime_sources':{n:sha(HERE/n) for n in sources},'plan_sha256':sha(HERE/'plan-template.json'),
    'native_marker_or_window_created':False,'task_registered':False,'os_events_executed':0,'service_controls':0,'provider_calls':0,
    'late_added_selector_scope':'Syntax/pins reviewed only; no real selection/SID XML materialization or task registration executed',
    'live_event_qualification':False,'fresh_before_exists':False,'acceptance_promoted':False})
names=sources+['REVIEW.md','test-result.json','capabilities.json','powercfg-available.txt','powercfg-wake-policy.txt','plan-template.json','qualification.json']
save('public-allowlist.json',{'files':[{'path':str(HERE/n),'sha256':sha(HERE/n),'bytes':(HERE/n).stat().st_size} for n in names],
    'excludes':'No selected task XML/SID, credentials, raw environment, task XML from service, runtime/private data or OS event receipt'})
print(json.dumps({n:sha(HERE/n) for n in ['plan-template.json','qualification.json','public-allowlist.json']}))

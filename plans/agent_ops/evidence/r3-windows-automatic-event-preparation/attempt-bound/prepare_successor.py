"""Offline copy/materialize only. No observer, task, OS or service is invoked."""
from pathlib import Path
import hashlib,json
HERE=Path(__file__).resolve().parent
OLD=Path('C:/Users/jpamb/AppData/Local/Temp/r3-windows-automation-supplement-9x8m6_1p')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(n,v):
    with (HERE/n).open('x',encoding='utf-8') as f:json.dump(v,f,indent=2,sort_keys=True)
sources={n:sha(OLD/n) for n in ('automation_contract.py','collect.py','select_event.py','plan-template.json','qualification.json','public-allowlist.json')}
with (HERE/'automation_contract.py').open('xb') as f:f.write((OLD/'automation_contract.py').read_bytes())
text=(OLD/'collect.py').read_text(encoding='utf-8')
text=text.replace('from automation_contract import EVENTS, classify_event, require, validate_window',
    'from automation_contract import EVENTS, classify_event, require, validate_window\nfrom attempt_contract import before_after_reserve')
text=text.replace("    # A logon task can run again. Existing evidence is never overwritten.",
    "    attempt=before_after_reserve(P,old,old_sha,plan_sha,directory)\n    if attempt is None:return {'status':'NO_SELECTED_EVENT_ATTEMPT_NO_AFTER_RESERVATION'}\n    # A logon task can run again. Existing evidence is never overwritten.")
text=text.replace("'current':current,'samples':samples,'history':history,'assessment':assessment,",
    "'current':current,'samples':samples,'history':history,'assessment':assessment,'event_attempt_pin':attempt,")
text=text.replace("        pin=O.save(directory/'before.json',value)",
    "        validate_window(P['window'],datetime.now(timezone.utc),value['own_session']['principal_sha256'])\n        pin=O.save(directory/'before.json',value)")
with (HERE/'collect.py').open('x',encoding='utf-8') as f:f.write(text)
text=(OLD/'select_event.py').read_text(encoding='utf-8')
text=text.replace("'event':event_command(a.event,r'C:\\Windows\\System32'),",
    "'derived_command_for_review_only':event_command(a.event,r'C:\\Windows\\System32'),\n        'execute_once':[plan['python'],'-I','-B','-X','utf8',str(HERE/'execute_event.py'),'--plan',str(selected),'--sha256',sha,'--execute-selected-event'],")
assert 'execute_once' in text
with (HERE/'select_event.py').open('x',encoding='utf-8') as f:f.write(text)
plan=json.loads((OLD/'plan-template.json').read_bytes())
plan.update(root=str(HERE),status='OFFLINE_ATTEMPT_BOUND_SUCCESSOR_UNSELECTED',reviewed_for_execution=False,selected_event=None,
    ancestor_automation_plan={'path':str(OLD/'plan-template.json'),'sha256':sources['plan-template.json']},
    event_attempt_required_before_after_reservation=True,event_execution_implemented=True,
    os_actions_implemented=True,execution_selected=False,event_command_templates_only=False)
external=[p for p in plan['read_only_dependencies'] if Path(p['path']).parent!=OLD]
plan['read_only_dependencies']=external+[{'path':str(HERE/n),'sha256':sha(HERE/n)} for n in
    ('automation_contract.py','collect.py','select_event.py','attempt_contract.py','execute_event.py')]
save('plan-template.json',plan)
save('ancestry.json',{'original_sources':sources,'original_root':str(OLD),'originals_untouched':all(sha(OLD/n)==v for n,v in sources.items()),
                    'effects_executed':0})
print(json.dumps({'status':'OFFLINE_SUCCESSOR_MATERIALIZED','plan_sha256':sha(HERE/'plan-template.json')}))

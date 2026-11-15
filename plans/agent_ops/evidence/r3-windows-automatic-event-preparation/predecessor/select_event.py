"""Prepare ONE reviewed event's immutable files. Does not register/trigger tasks/events."""
from datetime import datetime,timezone
import argparse
import hashlib
import json
from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from automation_contract import EVENTS,require,recovery_task_xml,validate_window,event_command

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def save(path,value):
    with Path(path).open('x',encoding='utf-8',newline='\n') as f:json.dump(value,f,indent=2,sort_keys=True);f.write('\n')

def main():
    p=argparse.ArgumentParser();p.add_argument('--proposal-sha256',required=True);p.add_argument('--event',choices=EVENTS,required=True)
    p.add_argument('--not-before',required=True);p.add_argument('--expires',required=True);p.add_argument('--reviewed-event-window',action='store_true')
    a=p.parse_args();require(a.reviewed_event_window,'REVIEWED_WINDOW_REQUIRED')
    require(digest(HERE/'plan-template.json')==a.proposal_sha256,'PROPOSAL_CHANGED')
    plan=json.loads((HERE/'plan-template.json').read_bytes())
    require(Path(sys.prefix).resolve()==Path(plan['python_prefix']).resolve(),'PREFIX_CHANGED')
    for pin in plan['read_only_dependencies']:require(digest(pin['path'])==pin['sha256'],'DEPENDENCY_CHANGED')
    import win32api,win32con,win32security
    token=win32security.OpenProcessToken(win32api.GetCurrentProcess(),win32con.TOKEN_QUERY)
    try:sid=win32security.ConvertSidToStringSid(win32security.GetTokenInformation(token,win32security.TokenUser)[0])
    finally:token.Close()
    principal=hashlib.sha256(sid.encode()).hexdigest()
    window={'event_id':a.event,'not_before_utc':a.not_before,'expires_utc':a.expires,'principal_sha256':principal,
            'reviewed_event_selected':True,'no_force_apps':True,'automatic_next_event':False}
    validate_window(window,datetime.now(timezone.utc),principal)
    root=HERE/'selections'/a.event;root.mkdir(parents=True,exist_ok=False)
    plan.update(root=str(root),selected_event=a.event,reviewed_for_execution=True,window=window)
    selected=root/'plan.json';save(selected,plan);sha=digest(selected)
    xml=recovery_task_xml(sid,plan['pythonw'],str(HERE/'collect.py'),str(selected),sha)
    with (root/'recovery-task.xml').open('x',encoding='utf-8') as f:f.write(xml)
    task='Okto-M1-Observation-'+sha[:16]
    save(root/'commands.json',{'task_name':task,'task_xml':str(root/'recovery-task.xml'),
        'before':[plan['python'],'-I','-B','-X','utf8',str(HERE/'collect.py'),'--plan',str(selected),'--sha256',sha,'--action','before'],
        'after':[plan['python'],'-I','-B','-X','utf8',str(HERE/'collect.py'),'--plan',str(selected),'--sha256',sha],
        'event':event_command(a.event,r'C:\Windows\System32'),
        'task_registration_not_executed':True,'event_not_executed':True,
        'registration_contract':'Refuse existing exact task name; Register-ScheduledTask with XML; no Force/password; verify exact XML/action/principal before event',
        'cleanup_contract':'After observer completes, unregister only this exact task iff XML/action/principal still match; do not stop running observer'})
    print(json.dumps({'status':'SELECTED_FILES_ONLY_NO_EVENT_OR_TASK','plan_sha256':sha,'directory':str(root)}))

if __name__=='__main__':main()

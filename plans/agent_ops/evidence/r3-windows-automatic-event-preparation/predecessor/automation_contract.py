"""Pure command/task construction. Importing this module has no Windows effect."""
from datetime import datetime, timezone
from pathlib import PureWindowsPath
import re
import subprocess
import xml.etree.ElementTree as ET

EVENTS=('01-suspend-resume','02-sign-out-logon','04-restart-logon')
NS='http://schemas.microsoft.com/windows/2004/02/mit/task'

def require(ok,code):
    if not ok: raise ValueError(code)

def event_command(event,system_directory):
    require(event in EVENTS,'EVENT_NOT_SELECTED')
    root=PureWindowsPath(system_directory)
    require(root.is_absolute(),'ABSOLUTE_SYSTEM_DIRECTORY_REQUIRED')
    if event==EVENTS[0]:
        return {'api':'powrprof.SetSuspendState','arguments':[False,False,False],
                'required_privilege':'SeShutdownPrivilege','hibernate':False,
                'wake_timer_guaranteed':False,'manual_wake_fallback':True}
    # A positive shutdown /t implies /f. Never use the default30 either.
    return [str(root/'shutdown.exe'),'/l'] if event==EVENTS[1] else [str(root/'shutdown.exe'),'/r','/t','0']

def validate_window(window,now,principal_sha256):
    require(window['event_id'] in EVENTS,'EVENT_NOT_SELECTED')
    start=datetime.fromisoformat(window['not_before_utc'])
    end=datetime.fromisoformat(window['expires_utc'])
    require(start.tzinfo is not None and end.tzinfo is not None,'UTC_WINDOW_REQUIRED')
    require(0<(end-start).total_seconds()<=1800,'FINITE_WINDOW_REQUIRED')
    require(start<=now<=end,'WINDOW_NOT_ACTIVE')
    require(window['principal_sha256']==principal_sha256,'OWN_PRINCIPAL_REQUIRED')
    require(window.get('reviewed_event_selected') is True,'EXPLICIT_EVENT_SELECTION_REQUIRED')
    require(window.get('no_force_apps') is True,'NO_FORCE_REQUIRED')
    require(window.get('automatic_next_event') is False,'NO_EVENT_CHAINING')
    return window['event_id']

def recovery_task_xml(sid,python,observer,plan,plan_sha):
    require(bool(re.fullmatch(r'S-1-5-(?:\d+-)*\d+',sid)),'OWN_SID_REQUIRED')
    require(bool(re.fullmatch(r'[a-f0-9]{64}',plan_sha)),'PLAN_PIN_REQUIRED')
    for path in (python,observer,plan): require(PureWindowsPath(path).is_absolute(),'ABSOLUTE_PATH_REQUIRED')
    ET.register_namespace('',NS)
    def child(parent,name,text=None):
        node=ET.SubElement(parent,'{'+NS+'}'+name)
        if text is not None: node.text=text
        return node
    root=ET.Element('{'+NS+'}Task',{'version':'1.4'})
    triggers=child(root,'Triggers'); trigger=child(triggers,'LogonTrigger')
    child(trigger,'Enabled','true'); child(trigger,'UserId',sid)
    principals=child(root,'Principals'); principal=child(principals,'Principal'); principal.set('id','OwnUser')
    child(principal,'UserId',sid); child(principal,'LogonType','InteractiveToken'); child(principal,'RunLevel','LeastPrivilege')
    settings=child(root,'Settings')
    for k,v in {'MultipleInstancesPolicy':'IgnoreNew','DisallowStartIfOnBatteries':'false',
                'StopIfGoingOnBatteries':'false','AllowHardTerminate':'false','StartWhenAvailable':'false',
                'RunOnlyIfNetworkAvailable':'false','Enabled':'true','Hidden':'true',
                'ExecutionTimeLimit':'PT0S','WakeToRun':'false'}.items(): child(settings,k,v)
    actions=child(root,'Actions'); actions.set('Context','OwnUser'); action=child(actions,'Exec')
    child(action,'Command',python)
    child(action,'Arguments',subprocess.list2cmdline(['-I','-B','-X','utf8',observer,'--plan',plan,'--sha256',plan_sha]))
    return ET.tostring(root,encoding='unicode',xml_declaration=True)

def classify_event(event,before,after,*,os_transition_observed=False):
    require(event in EVENTS,'EVENT_NOT_SELECTED')
    same_principal=bool(before.get('principal_sha256')) and before.get('principal_sha256')==after.get('principal_sha256')
    new_logon=bool(before.get('logon_authentication_id')) and bool(after.get('logon_authentication_id')) and before['logon_authentication_id']!=after['logon_authentication_id']
    new_boot=bool(before.get('last_boot_up_time_dmtf')) and bool(after.get('last_boot_up_time_dmtf')) and before['last_boot_up_time_dmtf']!=after['last_boot_up_time_dmtf']
    same_boot=bool(before.get('last_boot_up_time_dmtf')) and before.get('last_boot_up_time_dmtf')==after.get('last_boot_up_time_dmtf')
    same_logon=bool(before.get('logon_authentication_id')) and before.get('logon_authentication_id')==after.get('logon_authentication_id')
    observed=(same_principal and new_logon and same_boot) if event==EVENTS[1] else (same_principal and new_boot and new_logon) if event==EVENTS[2] else (same_principal and same_boot and same_logon and os_transition_observed is True)
    return {'event_id':event,'event_observed':observed,'status':'CORRELATED_EVENT_FACTS' if observed else 'EVENT_UNCONFIRMED',
            'new_logon':new_logon,'new_boot':new_boot,'command_success_is_event_proof':False,
            'physical_exit_inferred':False,'acceptance_automatically_promoted':False}

def automatic_wake_assessment(*,modern_standby,on_ac,wake_ac,wake_dc):
    enabled=(wake_ac if on_ac else wake_dc)==1
    return {'policy_enabled':enabled,'modern_standby':modern_standby,
            'automatic_wake_guaranteed':False,'manual_wake_must_be_available':True,
            'timer_attempt_eligible':enabled and not modern_standby,
            'reason':'MODERN_STANDBY_DESKTOP_WAKE_NOT_ESTABLISHED' if modern_standby else 'POLICY_DISABLED' if not enabled else 'HARDWARE_CONFIRMATION_STILL_REQUIRED'}

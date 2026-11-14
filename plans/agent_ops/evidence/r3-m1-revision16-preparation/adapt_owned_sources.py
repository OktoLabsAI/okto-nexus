"""Finite offline revision16 path/history delta; leaves all predecessor bytes intact."""
from pathlib import Path
H=Path(__file__).resolve().parent;OLD=H.with_name('work-revision15')
for name in ('adopt_local.py','authorize_local.py','cohort.py','driver_common.py','invoke_request.py',
             'lifecycle.py','m1_v14_observation.py','confirm_final_presence.py','upgrade_environment.py',
             'probe_new_package.py','check_composed_gate.py','request_entry.py'):
    data=(OLD/name).read_bytes()
    if name=='request_entry.py':data=data.replace(b'revision15 context',b'revision16 context')
    (H/name).write_bytes(data)
s=(OLD/'request_context.py').read_text(encoding='utf-8')
start=s.index('def verify_technical_predecessor(');end=s.index('\ndef gate(',start)
s=s[:start]+'''def verify_technical_predecessor(pin):
    proof=json.loads(pinned(pin).read_bytes())
    require(proof['status']=='CLOSED_REVISION15_WITH_CONTROL_RECEIPT_UNCONFIRMED'
        and Path(proof['root']).resolve()==CONTROL/'work-revision15','PREDECESSOR_SCOPE_CHANGED')
    for item in proof['files'].values():pinned(item)
    checkpoint=json.loads(pinned(proof['files']['checkpoint']).read_bytes())
    require(set(checkpoint['requests'])=={'m1v15-local-useful-13'}
        and checkpoint['requests']['m1v15-local-useful-13']['settled'] is True
        and checkpoint['requests']['m1v15-local-useful-13']['canonical_stage']=='CANCELLED'
        and checkpoint['faults']==['WORK_TERMINAL_FAILED'],'PREDECESSOR_CHECKPOINT_CHANGED')
    companion=json.loads(pinned(proof['files']['companion']).read_bytes())
    require(companion['cumulative_observed_tokens']==341276 and companion['charged_reservations']==13
        and companion['original_checkpoint_and_closure_untouched'] is True
        and companion['interrupt']['receipt_stage']=='SUBMITTED'
        and companion['interrupt']['completion_receipt_confirmed'] is False
        and companion['request14_selected'] is False,'PREDECESSOR_UNCERTAINTY_CHANGED')
    closure=json.loads(pinned(proof['files']['closure']).read_bytes())
    require(closure['status']=='CLOSED_NORMAL_CLEANUP_ACCEPTANCE_NOT_INFERRED'
        and closure['closed_without_force'] is True and closure['unsettled_requests']==0,
        'CLOSED_PREDECESSOR_REQUIRED')
    return True

'''+s[end:]
# Only current scope strings change; explicit predecessor validation above remains revision15.
for a,b in [
 ('Revision15 local13/14 executable; remote15/16 held','Revision16 local14/15 executable; remote16/17 held'),
 ('Revision15 local13/14 only; remote15/16 selectors held','Revision16 local14/15 only; remote16/17 selectors held'),
 ("'cumulative_model_admissions_max':16","'cumulative_model_admissions_max':17"),
 ("'okto.m1.v15.work-revision15'","'okto.m1.v16.work-revision16'"),
 ("HERE.name == 'work-revision15'","HERE.name == 'work-revision16'"),
 ("{'useful':'m1v15-local-useful-13','continuation':'m1v15-local-continuation-14',\n        'remote_useful':'m1v15-remote-useful-15','remote_continuation':'m1v15-remote-continuation-16'}",
  "{'useful':'m1v16-local-useful-14','continuation':'m1v16-local-continuation-15',\n        'remote_useful':'m1v16-remote-useful-16','remote_continuation':'m1v16-remote-continuation-17'}"),
 ("amendment['policy']['revision']==15 and amendment['policy']['max_cumulative_admissions']==16","amendment['policy']['revision']==16 and amendment['policy']['max_cumulative_admissions']==17"),
 ("amendment['policy']['carry_in_tokens']==295262 and amendment['policy']['carry_in_admissions']==12","amendment['policy']['carry_in_tokens']==341276 and amendment['policy']['carry_in_admissions']==13"),
 ("self.P['finite_work']['maximum_cumulative_admissions'] = 16","self.P['finite_work']['maximum_cumulative_admissions'] = 17"),
 ("self.P['finite_work']['historical_charged_reservations'] = 12","self.P['finite_work']['historical_charged_reservations'] = 13"),
 ('Twelve historical reservations and295262 observed tokens retained; four new finite IDs, maximum16 cumulative.',
  'Thirteen historical reservations and341276 observed tokens retained; four new finite IDs, maximum17 cumulative.'),
 ("== 'm1v14-local-work-12'","== 'm1v15-local-useful-13'"),
 ("'initial_cumulative_tokens': 295262, 'initial_cumulative_reservations': 12","'initial_cumulative_tokens': 341276, 'initial_cumulative_reservations': 13")]:
    assert a in s,a;s=s.replace(a,b)
start=s.index("    require(companion['status']=='FAILED_CAMPAIGN_NORMAL_CLEANUP_CONFIRMED'")
end=s.index('    original_context = ',start)
s=s[:start]+'''    require(companion['status']=='CANCELLED_WORK_NORMAL_CLOSURE_CONFIRMED_NO_M1_ACCEPTANCE'
        and companion['normal_cleanup']['all_three_retained_handles_exited'] is True
        and companion['normal_cleanup']['tasks_absent'] is True
        and companion['normal_cleanup']['force_used'] is False
        and companion['original_checkpoint_and_closure_untouched'] is True
        and companion['cumulative_observed_tokens']==341276 and companion['charged_reservations']==13,
        'CLOSED_PREDECESSOR_REQUIRED')
    predecessor=json.loads(pinned(amendment['technical_predecessor']).read_bytes())
    for name in ('physical_exit','cleanup_proof','uninstall','final_presence','closure'):
        pinned(predecessor['files'][name])
'''+s[end:]
compile(s,str(H/'request_context.py'),'exec');(H/'request_context.py').write_text(s,encoding='utf-8')
s=(OLD/'close_campaign.py').read_text(encoding='utf-8')
for a,b in [("policy['carry_in_admissions']==12 and policy['carry_in_tokens']==295262","policy['carry_in_admissions']==13 and policy['carry_in_tokens']==341276"),
 ("policy['max_cumulative_admissions']==16","policy['max_cumulative_admissions']==17"),
 ("{'m1v15-local-useful-13','m1v15-local-continuation-14',\n            'm1v15-remote-useful-15','m1v15-remote-continuation-16'}",
  "{'m1v16-local-useful-14','m1v16-local-continuation-15',\n            'm1v16-remote-useful-16','m1v16-remote-continuation-17'}"),
 ("history.get('historical_record_count')==3","history.get('historical_record_count')==4"),
 ("set(records)=={'m1v14-local-work-01','m1v14-local-work-11','m1v14-local-work-12'}",
  "set(records)=={'m1v14-local-work-01','m1v14-local-work-11','m1v14-local-work-12','m1v15-local-useful-13'}"),
 ("predecessor['requests']['m1v14-local-work-12']['settled'] is False",
  "records['m1v14-local-work-12']['settled'] is False\n        and predecessor['requests']['m1v15-local-useful-13']['settled'] is True")]:
    assert a in s,a;s=s.replace(a,b)
compile(s,str(H/'close_campaign.py'),'exec');(H/'close_campaign.py').write_text(s,encoding='utf-8')
print('Owned sources copied/adapted offline; no runtime directories or effects.')

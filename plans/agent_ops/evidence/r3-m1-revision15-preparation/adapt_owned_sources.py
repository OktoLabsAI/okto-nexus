"""Finite source deltas from immutable package2; never touches old runtime."""
from pathlib import Path
HERE=Path(__file__).resolve().parent
OLD=HERE.with_name('work-request12-package2')
def edit(name, replacements):
    source=(OLD/name).read_text(encoding='utf-8')
    for before,after in replacements:
        assert before in source,(name,before)
        source=source.replace(before,after)
    (HERE/name).write_text(source,encoding='utf-8')

old=(OLD/'request_context.py').read_text(encoding='utf-8')
start=old.index('def verify_technical_predecessor(')
end=old.index('\ndef gate(',start)
new='''def verify_technical_predecessor(pin):
    proof=json.loads(pinned(pin).read_bytes())
    require(proof['status']=='CLOSED_PACKAGE2_WITH_CONTROL_RECEIPT_UNCONFIRMED'
        and Path(proof['root']).resolve()==CONTROL/'work-request12-package2','PREDECESSOR_SCOPE_CHANGED')
    for item in proof['files'].values():pinned(item)
    checkpoint=json.loads(pinned(proof['files']['checkpoint']).read_bytes())
    require(set(checkpoint['requests'])=={'m1v14-local-work-12'}
        and checkpoint['requests']['m1v14-local-work-12']['settled'] is False
        and checkpoint['faults']==['API_OBSERVATION_UNKNOWN','CAMPAIGN_RUNNER_EXCEPTION'],
        'PREDECESSOR_CHECKPOINT_CHANGED')
    companion=json.loads(pinned(proof['files']['companion']).read_bytes())
    require(companion['observed_tokens']==295262 and companion['charged_reservations']==12
        and companion['original_checkpoint_untouched'] is True
        and companion['interrupt']['receipt_stage']=='SUBMITTED'
        and companion['interrupt']['completion_receipt_confirmed'] is False
        and companion['request13_selected'] is False,'PREDECESSOR_UNCERTAINTY_CHANGED')
    return True

'''
old=old[:start]+new+old[end:]
old=old.replace('"""Finite local12/13 amendment; historical authority and new package pins are distinct."""','"""Revision15 local13/14 executable; remote15/16 held behind separate qualification."""')
old=old.replace("Local12/13 only; historical command document is separately pinned.","Revision15 local13/14 only; remote15/16 selectors held, allocation retained.")
old=old.replace("'new_model_admissions_max':2,'cumulative_model_admissions_max':13","'new_model_admissions_max':4,'cumulative_model_admissions_max':16,'executable_local_admissions_max':2,'remote_selectors_enabled':False")
old=old.replace("'okto.m1.v14.work-request12'","'okto.m1.v15.work-revision15'").replace("HERE.name == 'work-request12-package2'","HERE.name == 'work-revision15'")
old=old.replace("{'useful': 'm1v14-local-work-12', 'continuation': 'm1v14-local-work-13'}","{'useful':'m1v15-local-useful-13','continuation':'m1v15-local-continuation-14',\n        'remote_useful':'m1v15-remote-useful-15','remote_continuation':'m1v15-remote-continuation-16'}")
old=old.replace("    verify_technical_predecessor(amendment['technical_predecessor'])", """    plan=json.loads(pinned(amendment['execution_plan']).read_bytes())
    require(amendment['policy']==plan['policy'] and amendment['remote_execution_enabled'] is False
        and amendment['policy']['revision']==15 and amendment['policy']['max_cumulative_admissions']==16
        and amendment['policy']['carry_in_tokens']==295262 and amendment['policy']['carry_in_admissions']==12,
        'SELECTED_TECHNICAL_POLICY_CHANGED')
    verify_technical_predecessor(amendment['technical_predecessor'])""")
start=old.index("    require(companion['status'] == 'CLOSED_AFTER_AUTHORIZED_FORCE")
end=old.index('    original_context = ',start)
old=old[:start]+'''    require(companion['status']=='FAILED_CAMPAIGN_NORMAL_CLEANUP_CONFIRMED'
        and companion['normal_cleanup']['all_three_retained_handles_exited'] is True
        and companion['normal_cleanup']['tasks_absent'] is True
        and companion['normal_cleanup']['force_used'] is False
        and companion['original_checkpoint_untouched'] is True
        and companion['observed_tokens']==295262 and companion['charged_reservations']==12,
        'CLOSED_PREDECESSOR_REQUIRED')
    for name in ('physical_exit','cleanup_proof','uninstall','final_presence','primary_database_preservation'):
        pinned(companion['normal_cleanup'][name])
'''+old[end:]
old=old.replace("== 'm1v14-local-work-11'","== 'm1v14-local-work-12'")
old=old.replace("'initial_cumulative_tokens': 272648, 'initial_cumulative_reservations': 11","'initial_cumulative_tokens': 295262, 'initial_cumulative_reservations': 12")
(HERE/'request_context.py').write_text(old,encoding='utf-8')

edit('confirm_final_presence.py',[("previous['physical_exit_confirmed'] is True and previous['nexus_task_absent'] is True\n        and previous['canonical_owner_absent'] is True", "previous['normal_cleanup']['all_three_retained_handles_exited'] is True\n        and previous['normal_cleanup']['tasks_absent'] is True and previous['normal_cleanup']['force_used'] is False")])
edit('cohort.py',[("row['generation'] > 6", "row['generation'] > context.amendment['predecessor_connection_generation']")])
edit('request_entry.py',[("explicitly derived v14 context", "explicitly derived revision15 context"),("'LOCAL_RESUME_ONLY'","'REMOTE_SELECTORS_HELD_LOCAL_ONLY'")])
print('Owned source deltas prepared; no runtime effect.')

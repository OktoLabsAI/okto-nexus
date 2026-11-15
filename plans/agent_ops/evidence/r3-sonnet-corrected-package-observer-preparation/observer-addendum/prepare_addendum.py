from pathlib import Path
import hashlib,json
H=Path(__file__).resolve().parent;OLD=H.parent;R=OLD.parent
def ref(path):
    p=Path(path);return {'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size}
def save(name,value):
    with (H/name).open('x',encoding='utf-8') as f:json.dump(value,f,indent=2);f.write('\n')
original=json.loads((OLD/'force-proposal-current.json').read_bytes())
selected=json.loads((OLD/'public/connector-owner-selection.json').read_bytes())
pins={'original_proposal':ref(OLD/'force-proposal-current.json'),'selection':ref(OLD/'public/connector-owner-selection.json'),
      'expired_observation':ref(OLD/'public/connector-exit-watch-timeout.json'),
      'original_observer_started':ref(OLD/'public/connector-exit-watch-started.json'),
      'lifecycle':ref(R/'lifecycle-plan.json'),'context':ref(R/'recovery_context.py'),
      'observation':ref(R/'recovery_observation.py'),'connector':ref(R/'recovery_connector.py'),
      'installation':ref(R/'package/installation.json'),'observer':ref(H/'observe.py')}
save('addendum.json',{'status':'PREPARED_READONLY_OBSERVER_NOT_STARTED_FORCE_PENDING_AUTHORIZATION',
    'purpose':'Replace expired observer22718 evidence with new exact query/synchronize handles; original proposal/timeout preserved.',
    'pins':pins,'cohort':selected['cohort'],'canonical_force_argv':original['argv'],
    'max_canonical_force_calls_unchanged':1,'observation_seconds':3600,
    'observer_control_calls':0,'observer_provider_calls':0,'observer_has_terminate_right':False,
    'authorization_created':False,'force_executed':False,
    'force_effect_record':'Separate root receipt of actual one-off canonical command; never inferred from observer exit proof.',
    'result_namespace':str(H/'public'),'original_files_changed':False})
addendum=ref(H/'addendum.json')
save('commands.json',{'status':'NOT_EXECUTED',
    'watch_readonly':['rtk','proxy',original['argv'][0],'-I','-B','-X','utf8',str(H/'observe.py'),
        '--expected-addendum-sha256',addendum['sha256']],
    'canonical_force_once_only_after_actual_authorization_and_fresh_handshake':['rtk','proxy',*original['argv']],
    'sequence':['Root confirms actual specific user authorization before force; the observer itself does not authorize or dispatch it.',
        'Start this foreground watcher only when needed, retain its tool session, wait for watch-started.json/EXACT_THREE_HANDLES_RETAINED.',
        'Confirm new observer identity remains live and has no timeout/failure/exit record; recheck exact canonical generation/cycle/task before dispatch.',
        'Use one root-owned exclusive force reservation and the unchanged canonical argv. Never resend an unknown/pending result.',
        'Record actual canonical result and force-effect provenance separately; wait for this observer exit-proof.json for all three roles.',
        'Timeout/failure is not physical exit; no restart/uninstall follows without actual proof and canonical cleanup.'],
    'old_observer22718_current':False})
save('qualification.json',{'status':'OFFLINE_OBSERVER_PREPARATION_ONLY','tests':{'unique_passed':2,'seconds':.035,'tool':'2d8ef8',
    'argv':['rtk','proxy',original['argv'][0],'-I','-B','-X','utf8',str(H/'test_observe.py')],
    'scope':'Synthetic handles only; birth mismatch, timeout not exit, exact three exits, no force attribution.'},
    'original_proposal':pins['original_proposal'],'expired_observer':pins['expired_observation'],
    'addendum':addendum,'observer':ref(H/'observe.py'),'test':ref(H/'test_observe.py'),
    'live_observation_started':False,'services_mutated':False,'force_authorized_by_this_addendum':False,
    'provider_calls':0,'original_receipts_preserved':True})
public=['observe.py','test_observe.py','prepare_addendum.py','addendum.json','commands.json','qualification.json','README.md']
save('public-allowlist.json',{'source_root':str(H),'files':[{'path':n,'sha256':ref(H/n)['sha256'],'bytes':(H/n).stat().st_size} for n in public]})
print(json.dumps({n:ref(H/n) for n in ('observe.py','addendum.json','commands.json','qualification.json','public-allowlist.json')}))

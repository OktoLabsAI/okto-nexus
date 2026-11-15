from pathlib import Path
import json,hashlib
H=Path(__file__).parent
def read(p):return json.loads(Path(p).read_bytes())
def ref(p):
 p=Path(p);return {'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size}
def save(p,v):
 with Path(p).open('x',encoding='utf8') as f:json.dump(v,f,indent=2);f.write('\n')
c=read(H/'candidate.json');L=Path(c['lifecycle_plan']['path']);life=read(L)
python=life['python'];base=[python,'-I','-B','-X','utf8']
work=base+['-m','okto_nexus.adapters.inbound.cli.main','work','authorize','--home',life['paths']['operator_home'],
 '--profile','m1-sonnet-remote-recovery02','--operator-profile','m1-sonnet-human','--project',life['campaign_root'],'--readiness-timeout','5','--json']
commands={'status':'FUTURE_ROOT_SELECTION_ONLY_NO_EXECUTION','prefix_shell_commands_with':'rtk',
 'lifecycle_commands':ref(L.parent/'commands.json'),
 'grant_review':work+['--minutes','60','--actions','3'],
 'grant_issue_once_after_exact_review':work+['--review','<EXACT_FRESH_REVIEW_REVISION>'],
 'materialize_after_actual_answer_and_fresh_receipts':base+[str(H/'materialize.py'),'--authorization-record',str(H/'authorization-record.json')],
 'native_manual_selector':base+[str(H/'fast_approval.py'),'--public',str(H/'paid-work/public/fast-native-question.json'),
 '--root-view',str(H/'paid-work/private/native-command-root-view.json'),'--scope',str(H/'paid-work/private/native-scope.json'),
 '--root-ready',str(H/'paid-work/private/root-manually-ready.json'),'--destination',str(H/'paid-work/private/native-decision.json'),
 '--approval-id','<ACTUAL_ID>','--review-revision','<ACTUAL_REVISION>','--reviewed-command-sha256','<ACTUAL_REVIEWED_COMMAND_SHA>','--decision','<ROOT_APPROVE_OR_DENY>'],
 'no_auto_grant_or_native_decision':True,'paid_commands_generated_only_after_materialization':True}
save(H/'future-commands.json',commands)
for name in H.glob('*.py'):compile(name.read_bytes(),str(name),'exec')
assert all(not (H/n).exists() for n in ('authorization-record.json','work-plan.json','budget-seed-approved.json','paid-work'))
qual={'status':'OFFLINE_MATERIALIZABLE_CANDIDATE_AUTHORIZATION_PENDING','candidate':ref(H/'candidate.json'),
 'tests':[{'tool':'e41172','passed':3,'seconds':.090,'scope':'Pending authorization blocks plan/seed; in-memory conversion preserves3history; empty pages refreshpendingcallback'},
 {'tool':'a7dc8b','passed':1,'seconds':.023,'scope':'Positive dashboard state only; missing/unknown neverTrue'}],
 'test_source':ref(H/'test_pending_composition.py'),'all_python_syntax':'PASS',
 'scope':'No new installed constructor claim: paidplan intentionally absent. Existing Q/runtime and FAST supplement qualifications retained as provenance.',
 'fast_supplement':c['fast_approval_allowlist'],'lifecycle':c['lifecycle_plan'],
 'actual_authorization_record':False,'paid_plan_created':False,'new_seed5_created':False,'service_effects':0,'provider_calls':0,'os_events':0,
 'notes':['Native07 consumed; previousfaultedcheckpoint remains unchanged','Native5/Server6 and continuation1x are pending explicit new user answer','No repeat SVC09 hook selected in future plan','Oldgrant3fbf cannot meet future600swindow; canonicalreview/issue required afterL3READY']}
save(H/'qualification.json',qual)
names=[p.name for p in H.glob('*.py')]+['candidate.json','task-prompts.json','typed-denial05.json','HANDOFF.md','future-commands.json','qualification.json']
save(H/'public-allowlist.json',{'source_root':str(H),'files':[{'path':n,'sha256':ref(H/n)['sha256'],'bytes':(H/n).stat().st_size} for n in names]})
print(json.dumps({'root':str(H),'qualification':ref(H/'qualification.json'),'commands':ref(H/'future-commands.json'),'allowlist':ref(H/'public-allowlist.json')}))

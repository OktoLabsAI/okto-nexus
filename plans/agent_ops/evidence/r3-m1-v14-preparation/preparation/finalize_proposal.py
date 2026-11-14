from pathlib import Path
import hashlib,json,shutil,sys
S=Path(__file__).parent;D=S/'draft';candidate=Path(sys.argv[1])
sha=lambda f:hashlib.sha256(Path(f).read_bytes()).hexdigest()
freeze=candidate/'qualification/runtime-pins.json'
manifest=json.loads(freeze.read_bytes());target=S/'root-drivers';target.mkdir(exist_ok=True)
for key,entry in manifest['files'].items():
    source=Path(entry['path']);assert sha(source)==entry['sha256'];dest=target/source.name
    if dest.exists():assert dest.read_bytes()==source.read_bytes()
    else:shutil.copyfile(source,dest)
    assert sha(dest)==entry['sha256']
pfile=D/'m1-codex-campaign-proposal-v14.json';p=json.loads(pfile.read_bytes())
for key,entry in manifest['files'].items():
    p['execution_bundle']['files'][key]={'path':str(target/Path(entry['path']).name),'sha256':entry['sha256']}
recipefile=D/'remote-canonical-recipe.json';recipe=json.loads(recipefile.read_bytes())
recipe['status']='FROZEN_QUALIFIED';recipe['proposal_revision']=14
recipe['operator_bootstrap']['implementation_status']='FROZEN_V14_DRIVER_QUALIFIED'
recipe['operator_bootstrap']['executor'].update(p['execution_bundle']['files']['root_driver_operator_bootstrap'])
recipefile.write_text(json.dumps(recipe,indent=2)+'\n',encoding='utf-8',newline='\n')
planning=D/'planning-commands.json';plan=json.loads(planning.read_bytes());plan['status']='FROZEN_QUALIFIED'
planning.write_text(json.dumps(plan,indent=2)+'\n',encoding='utf-8',newline='\n')
for entry in p['execution_bundle']['files'].values():entry['sha256']=sha(entry['path'])
assert len(p['execution_bundle']['files'])==47
e=p['execution_bundle'];e['status']='FROZEN_QUALIFIED';e['commands']['sha256']=sha(e['commands']['path'])
e['qualification_scope']='V14 affected34 unique cases: initial32PASS/2FAIL identified wrapper timestamp shadowing; corrected wrapper and multi-decision recovery5PASS. Other passing cases retain identical source bytes. Peer driver focused qualification pinned separately. Fresh final origins and negative entry gates accompany curation; prior v13 suites are historical, not recounted.'
p['status']='FROZEN_QUALIFIED_OFFLINE_WORK_SUCCESSOR';p['final_proposal']=True
p['qualification_status']='OFFLINE_AFFECTED_DELTA_QUALIFIED_REAL_WORK_PENDING'
p['blocking_preconditions']=['Root reviews exact final freeze and binds standing authorization truthfully','Owned task/port and immutable adoption proofs verified before lifecycle','Adopt closed predecessor work snapshot; canonical grant review selects available budget or explicit expired replacement; never replay setup/oldturn']
p['operator_bootstrap']['implementation_status']='FROZEN_V14_DRIVER_BOUND_OFFLINE_QUALIFIED'
p['scope_qualification']['status']='OFFLINE_V14_INSTALLED_CLI_AFFECTED_DELTA_QUALIFIED_REAL_WORK_PENDING'
c=p['controller_preparation'];c['status']='OFFLINE_WORK_SUCCESSOR_QUALIFIED';c['qualification_status']='AFFECTED34_UNIQUE_PASS_WITH_RETAINED_FIXED_FAILURES'
c['observation_contract']['productive_deadline_seconds']=600
c['controller_sha256']=sha(D/'controller/controller.py');c['collector_sha256']=sha(D/'controller/token_collector.py');c['observer_sha256']=sha(D/'controller/independent_controller.py')
c['affected_composition']={'initial_xml':str(S/'affected-001/results.xml'),'initial_xml_sha256':sha(S/'affected-001/results.xml'),'initial_tests':34,'initial_passed':32,'initial_failed':2,'final_wrapper_xml':str(S/'affected-wrapper-fix/results.xml'),'final_wrapper_xml_sha256':sha(S/'affected-wrapper-fix/results.xml'),'final_wrapper_passed':5,'unique_qualified_cases':34,'delta':'Wrapper variable shadowing fixed; targeted wrapper/recovery rerun. No runtime timing relaxation.'}
p['root_driver_preparation']={'candidate':str(candidate),'freeze':str(freeze),'freeze_sha256':sha(freeze),'qualification':str(candidate/'qualification/qualification.json'),'qualification_sha256':sha(candidate/'qualification/qualification.json'),'scope':'Copied frozen peer runtime exactly; focused changed-driver fixtures, previous suites explicitly historical.'}
p['execution_authorized']=False;p['authorization']['execution_authorized']=False
pfile.write_text(json.dumps(p,indent=2)+'\n',encoding='utf-8',newline='\n')
print(json.dumps({'proposal_sha256':sha(pfile),'files':len(e['files'])}))

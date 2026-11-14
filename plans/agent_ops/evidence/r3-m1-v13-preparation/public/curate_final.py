"""Curate explicit source/metadata evidence only; runtime CONTROL/public stays absent."""
from pathlib import Path
import hashlib,json,shutil,xml.etree.ElementTree as ET
from datetime import datetime,timezone
S=Path(__file__).resolve().parent;D=S/'draft';C=Path('C:/Users/jpamb/AppData/Local/Temp/m1-v13-driver-candidate-l5h1djy4');OUT=S/'public-artifacts'
assert not OUT.exists();OUT.mkdir()
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
write=lambda p,v:p.write_text(json.dumps(v,indent=2,ensure_ascii=False)+'\n',encoding='utf-8',newline='\n')
pfile=D/'m1-codex-campaign-proposal-v13.json';p=json.loads(pfile.read_bytes())
assert json.loads((S/'final-entry-gates/result.json').read_bytes())['exit_code']==0
assert not (S/'public').exists() and not (S/'private').exists()
groups={'affected-composition':S/'affected-final/results.xml','threshold-delta':S/'threshold-delta/results.xml','drivers':C/'qualification/final.xml','entry-guards':S/'final-entry-gates/results.xml'}
cases={};groups_out={}
for name,path in groups.items():
    root=ET.parse(path).getroot();entries=list(root.iter('testcase'))
    assert all(t.find('failure') is None and t.find('error') is None and t.find('skipped') is None for t in entries)
    keys={t.attrib.get('classname','')+'::'+t.attrib['name'] for t in entries}
    cases[name]=keys
    groups_out[name]={'tests':len(entries),'xml':str(path),'sha256':sha(path),'failures':0,'errors':0}
union=set().union(*cases.values())
runtime={key:{'path':v['path'],'sha256':sha(v['path'])} for key,v in p['execution_bundle']['files'].items()}
write(S/'runtime-freeze.json',{'format':'m1-v13-final-runtime-freeze','proposal_sha256':sha(pfile),'files':runtime,'policy':p['controller_preparation']['policy'],'real_effects_executed':False})
qualification={'format':'m1-v13-offline-successor-qualification','status':'PASS','generated_at_utc':datetime.now(timezone.utc).isoformat(),'proposal_sha256':sha(pfile),'runtime_manifest_sha256':sha(S/'runtime-freeze.json'),'groups':groups_out,'unique_passed':len(union),'summed_group_cases':sum(len(x) for x in cases.values()),'deduplication':'Exact pytest classname plus parametrized test name; threshold-delta repeats related cases already present in affected-composition. Historical64/73/121 suites are component references and are not added.','overlaps':{a+' / '+b:len(cases[a]&cases[b]) for i,a in enumerate(cases) for b in list(cases)[i+1:] if cases[a]&cases[b]},'coverage_basis':'69-case composition passed before threshold change; reviewed scalar-only delta in controller/legacy/collector/EffectFence was then covered by8 focal cases. Other runtime modules remain byte-identical to that composition.10drivers copied byte-for-byte from119PASS peer freeze; no117/119 rerun. Final origins and21 denied entries check actual composed paths.','historical_attempts':[{'path':str(S/'affected-001/results.xml'),'sha256':sha(S/'affected-001/results.xml'),'status':'58PASS2FAIL','reason':'Two inherited assertions expected no max-allocation reason at final slot; runtime completed four work intents. Updated expectations only; no limit relaxation.'},{'path':str(C/'qualification/antecedent-117pass-1fail.xml'),'sha256':sha(C/'qualification/antecedent-117pass-1fail.xml'),'status':'117PASS1FAIL','reason':'Inherited no-controller fixture expected old89473 instead of111651; peer qualifier preserves exact history.'}],'invariants':{'carry_in_reservations':8,'carry_in_tokens':111651,'new_reservations':4,'maximum_cumulative':12,'preventive_tokens':500000,'tolerance_tokens':700000,'deadline_seconds':120,'init_ms':250,'read_ms':250,'poll_ms':600,'freshness_ms':1000,'prior_setup_replayed':False,'old_tokens_counted_twice':False,'predecessor_checkpoint_mutated':False,'new_installation':False,'actual_user_receipt_created':False,'service_provider_credentials_effects':False},'adopted_installation':{'revision':12,'payloads':983,'interpreter_plus_payload_pins':984,'original_install_timing_preserved':True},'acceptance':{'M1':False,'DX39_DX40_AC11':False,'BASE06_first_useful_measured':False,'billing_final':False},'limitations':['Offline correctness is not real campaign or billing acceptance.','Windows latency bounds are fail-closed contracts, not guaranteed availability; earlier source timing failures remain historical.','Existing qualified wheels precede later SVC-T19 diagnostic patches.','No literal console-window/dashboard closure is inferred from installed parser/handler invocation.','An insufficient available grant window refuses work; no automatic repeat review/issuance.']}
write(S/'qualification.json',qualification)
selections=[]
def add(src,rel):
    source=Path(src);dest=OUT/rel;assert source.is_file() and not dest.exists()
    dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,dest)
    assert sha(source)==sha(dest)
    selections.append({'path':str(Path(rel).as_posix()),'source_path':str(source),'source_sha256':sha(source),'artifact_sha256':sha(dest),'bytes':dest.stat().st_size})
for key,entry in p['execution_bundle']['files'].items():
    source=Path(entry['path'])
    if source.is_relative_to(S) and source.suffix in ('.py','.json'):add(source,source.relative_to(S))
add(pfile,'m1-codex-campaign-proposal-v13.json')
add(D/'proposed-commands.json','draft/proposed-commands.json')
for name in ('runtime-freeze.json','qualification.json','test_control_adoption.py','test_lifecycle_cleanup.py','test_successor_entries.py','qualify_affected.py','qualify_affected_final.py','qualify_threshold.py','verify_final.py','finalize_proposal.py','curate_final.py'):
    add(S/name,name)
for name in ('test_independent.py','test_v11_allocation.py','test_work_wrapper.py','test_observation_budget.py','canonical_fixture.py'):
    add(D/'controller'/name,'tests/controller/'+name)
for name in ('test_remote_setup_composition.py','test_remote_transfer_monitor.py'):add(D/name,'tests/'+name)
for folder in ('affected-001','affected-final','threshold-delta','final-entry-gates'):
    for name in ('results.xml','result.json','module-origins.json'):
        source=S/folder/name
        if source.exists():add(source,'evidence/'+folder+'/'+name)
allow=json.loads((C/'qualification/public-allowlist.json').read_bytes())
for entry in allow['files']:
    source=C/entry['relative_path'];assert sha(source)==entry['sha256']
    add(source,'peer-driver-freeze/'+entry['relative_path'])
add(C/'qualification/public-allowlist.json','peer-driver-freeze/qualification/public-allowlist.json')
for name in ('m1-codex-campaign-proposal-v12.json','closure.json','installation-result.json'):
    source=D/'history-v12'/name
    if source.exists():add(source,'history-v12/'+name)
manifest={'format':'m1-v13-curated-artifact-manifest','generated_at_utc':datetime.now(timezone.utc).isoformat(),'proposal_sha256':sha(pfile),'qualification_sha256':sha(S/'qualification.json'),'artifacts':selections,'excluded':'No binaries, product payloads, personal credentials/config/transcripts, runtime homes/database/vaults, real approval receipt or raw provider logs.'}
write(OUT/'artifact-manifest.json',manifest)
print(json.dumps({'public':str(OUT),'artifacts':len(selections),'unique_passed':len(union),'proposal_sha256':sha(pfile),'manifest_sha256':sha(OUT/'artifact-manifest.json'),'qualification_sha256':sha(OUT/'qualification.json')},indent=2))

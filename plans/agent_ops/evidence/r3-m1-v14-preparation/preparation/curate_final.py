"""Explicit allowlist of offline sources/evidence, with historical failures retained."""
from pathlib import Path
import hashlib,json,shutil,xml.etree.ElementTree as ET
from datetime import datetime,timezone
S=Path(__file__).parent;D=S/'draft';OUT=S/'public-artifacts'
sha=lambda f:hashlib.sha256(Path(f).read_bytes()).hexdigest()
def write(f,v):f.write_text(json.dumps(v,indent=2,ensure_ascii=False)+'\n',encoding='utf-8',newline='\n')
pfile=D/'m1-codex-campaign-proposal-v14.json';p=json.loads(pfile.read_bytes())
C=Path(p['root_driver_preparation']['candidate'])
assert json.loads((S/'final-entry-gates/result.json').read_bytes())['exit_code']==0
assert not OUT.exists() and not (S/'public').exists() and not (S/'private').exists();OUT.mkdir()
runtime={k:{'path':v['path'],'sha256':sha(v['path'])} for k,v in p['execution_bundle']['files'].items()}
assert all(v['sha256']==p['execution_bundle']['files'][k]['sha256'] for k,v in runtime.items())
write(S/'runtime-freeze.json',{'format':'m1-v14-final-runtime-freeze','proposal_sha256':sha(pfile),'files':runtime,'policy':p['controller_preparation']['policy'],'real_effects_executed':False})
groups={'affected-first':S/'affected-001/results.xml','wrapper-fix':S/'affected-wrapper-fix/results.xml',
 'drivers':C/'qualification/final.xml','drivers-prior-done':C/'qualification/prior-done-checkpoint.xml',
 'entry-guards':S/'final-entry-gates/results.xml'}
latest={};report={}
for name,path in groups.items():
    cases=list(ET.parse(path).getroot().iter('testcase'));failures=0
    for case in cases:
        key=case.attrib.get('classname','')+'::'+case.attrib['name']
        passed=all(case.find(tag) is None for tag in ('failure','error','skipped'))
        if not passed:failures+=1
        latest[key]={'passed':passed,'latest_group':name}
    report[name]={'xml':str(path),'sha256':sha(path),'tests':len(cases),'failed_or_skipped':failures}
assert all(v['passed'] for v in latest.values())
qualification={
 'format':'m1-v14-offline-successor-qualification','status':'PASS',
 'generated_at_utc':datetime.now(timezone.utc).isoformat(),'proposal_sha256':sha(pfile),
 'runtime_manifest_sha256':sha(S/'runtime-freeze.json'),'groups':report,
 'unique_passed':len(latest),'deduplication':'Exact pytest classname and parametrized test name; latest affected rerun supersedes only the same cases. First failed attempt remains evidence.',
 'coverage_basis':'V14 affected34 unique cases qualify carry9/134199,4new/max13,600s, explicit new local session,3 decisions/lane and individual decision recovery. Initial32PASS2FAIL found timestamp-variable shadowing; corrected wrapper/recovery5PASS. Peer final focuses changed drivers; v13 historical suites are not added to actual v14 counts. Final fresh installed origins/pins plus negative entry gates run against composed sources.',
 'historical_reference':{'v13_qualification_path':str(S.parent/'successor13/qualification.json'),
  'sha256':sha(S.parent/'successor13/qualification.json'),'not_counted_as_v14_run':True},
 'post_gate_prose_amendment':{'path':str(S/'final-prose-amendment.json'),'sha256':sha(S/'final-prose-amendment.json'),
  'scope':'Root requested one counter-semantics sentence corrected after gates; all47 runtime/dependency pins unchanged. No new executable behavior.'},
 'invariants':{'carry_in_reservations':9,'carry_in_tokens':134199,'new_reservations':4,'maximum_cumulative':13,
  'preventive_tokens':500000,'tolerance_tokens':700000,'deadline_seconds':600,'native_decisions_per_lane':3,
  'init_ms':250,'read_ms':250,'poll_ms':600,'freshness_ms':1000,
  'prior_setup_replayed':False,'prior_turn_replayed':False,'old_tokens_counted_twice':False,
  'predecessor_checkpoint_mutated':False,'new_installation':False,'actual_user_receipt_created':False,
  'service_provider_credentials_effects':False},
 'adopted_installation':{'revision':12,'payloads':983,'interpreter_plus_payload_pins':984,'original_install_timing_preserved':True},
 'acceptance':{'M1':False,'DX39_DX40_AC11':False,'BASE06_first_useful_measured':False,'billing_final':False},
 'limitations':['Offline qualification is not real campaign/billing acceptance.','SQL/poll/freshness bounds fail closed and do not guarantee Windows availability; earlier timing failures remain historical.','Adopted wheels predate later SVC-T19,DX-T34 and CLI-drain source fixes; no live wheel substitution.','Installed CLI parser/handler execution does not prove a literal console/window/dashboard close.','Grant reuse/expiry replacement remains canonical and explicitly selected; historical consumption is never reset.']}
write(S/'qualification.json',qualification)
items=[];seen=set()
def add(src,rel):
    src=Path(src);rel=str(Path(rel).as_posix())
    if rel in seen:return
    seen.add(rel);dest=OUT/rel;assert src.is_file() and not dest.exists()
    dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dest);assert sha(src)==sha(dest)
    items.append({'path':rel,'source_path':str(src),'source_sha256':sha(src),'artifact_sha256':sha(dest),'bytes':dest.stat().st_size})
for pin in p['execution_bundle']['files'].values():
    src=Path(pin['path'])
    if src.is_relative_to(S) and src.suffix in ('.py','.json'):
        add(src,src.relative_to(S))
add(pfile,'m1-codex-campaign-proposal-v14.json');add(D/'proposed-commands.json','draft/proposed-commands.json')
for name in ('runtime-freeze.json','qualification.json','test_control_adoption.py','test_successor_entries.py',
 'qualify_affected.py','qualify_wrapper_fix.py','verify_final.py','finalize_proposal.py','curate_final.py','update_metadata.py','final-prose-amendment.json'):
    add(S/name,name)
for name in ('test_independent.py','test_v11_allocation.py','test_v14_delta.py','test_cli_flow.py','test_work_wrapper.py','canonical_fixture.py'):
    add(D/'controller'/name,'tests/controller/'+name)
for folder in ('affected-001','affected-wrapper-fix','final-entry-gates'):
    for name in ('results.xml','result.json','module-origins.json'):
        src=S/folder/name
        if src.exists():add(src,'evidence/'+folder+'/'+name)
allowpath=C/'public-allowlist.json';allow=json.loads(allowpath.read_bytes())
for entry in allow['files']:
    rel=entry.get('relative_path',entry.get('path'));src=C/rel
    assert sha(src)==entry['sha256'];add(src,'peer-driver-freeze/'+rel)
add(allowpath,'peer-driver-freeze/qualification/public-allowlist.json')
for key in ('predecessor_closure_pin','predecessor_companion_pin','predecessor_checkpoint_pin'):
    entry=p['adoption'][key];add(entry['path'],'history-v13/'+Path(entry['path']).name)
write(OUT/'artifact-manifest.json',{'format':'m1-v14-curated-artifact-manifest','generated_at_utc':datetime.now(timezone.utc).isoformat(),
 'proposal_sha256':sha(pfile),'qualification_sha256':sha(S/'qualification.json'),'artifacts':items,
 'excluded':'No binaries, product payloads, personal credentials/config/transcripts, runtime homes/databases/vaults, actual approval receipt or raw provider logs.'})
print(json.dumps({'public':str(OUT),'artifacts':len(items),'unique_passed':len(latest),'proposal_sha256':sha(pfile),
 'manifest_sha256':sha(OUT/'artifact-manifest.json'),'qualification_sha256':sha(OUT/'qualification.json')},indent=2))

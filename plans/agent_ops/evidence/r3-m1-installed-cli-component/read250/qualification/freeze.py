"""Preserve the sole final qualification and its predecessor evidence."""
from pathlib import Path
import hashlib,json,shutil,xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1];Q=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,value):
    with p.open('x',encoding='utf-8') as f:json.dump(value,f,indent=2)
previous=Path('C:/Users/jpamb/AppData/Local/Temp/m1-v11-cli-candidate-_892mowb')
manifest_path=previous/'qualification/runtime-freeze.json'
assert sha(manifest_path)=='167f5f3f1e62dad1db0018afe23eb174f9d36a10ef5ce677ef92a4e2b14312b3'
old=json.loads(manifest_path.read_text())
assert all(sha(previous/item['path'])==item['sha256'] for item in old['runtime']+old['tests'])
sources=json.loads((Q/'final-run-sources.json').read_text())
assert all(sha(ROOT/name)==digest for name,digest in sources.items()),'SOURCE_CHANGED_AFTER_TEST'
runtime=sorted([p for p in (ROOT/'controller').glob('*.py') if not p.name.startswith('test_')]+[ROOT/name for name in ('m1_v11_work.py','publication.py','response_loss.py')])
tests=sorted((ROOT/'controller').glob('test_*.py'))
changed=[item['path'] for item in old['runtime'] if sha(ROOT/item['path'])!=item['sha256']]
assert set(changed)=={'controller/independent_journal.py','controller/independent_controller.py'}
s=ET.parse(Q/'final.xml').getroot().find('testsuite')
result={'tests':int(s.get('tests')),'failures':int(s.get('failures')),'errors':int(s.get('errors')),'skipped':int(s.get('skipped')),'seconds':float(s.get('time')),
        'failed_cases':[c.get('name') for c in s.findall('testcase') if c.find('failure') is not None or c.find('error') is not None]}
result['passed']=result['tests']-result['failures']-result['errors']-result['skipped']
classification='FINAL_OFFLINE_SUITE_PASS_READ250' if not result['failures'] and not result['errors'] else 'READ250_FINAL_OFFLINE_SUITE_HAS_FAILURES'
shutil.copyfile(previous/'qualification/final.xml',Q/'predecessor-cli-final.xml')
shutil.copyfile(previous/'qualification/timing-failure-projection.json',Q/'predecessor-timing-failures.json')
real=next((Q/'final-tmp').glob('test_real_closed*/real-reader-evidence.json'))
shutil.copyfile(real,Q/'real-closed-db-evidence.json');real_data=json.loads(real.read_text())
db=Path('C:/Users/jpamb/AppData/Local/Temp/m1-v10-bundle-pscf18t5/campaign/nexus-home/nexus.db')
assert sha(db)==real_data['source_db_sha256']=='a1e7b0afee7aee41c00917ed5fa302b502324d70bc45c3e37e3220b9d2276a8b'
report={'classification':classification,'final_suite':result,'complete_suite_attempts':1,
 'scope':'Offline harness read-budget calibration only; no service, provider, real credentials, product/wheel mutation or real M1 execution.',
 'runtime_changes':changed,'change':'ReadOnly default/maximum local read budget100→250ms; controller diagnostic metadata100→250. SQLite connect/busy timeout follows the same local budget.',
 'unchanged':{'initialization_ms':250,'aggregate_poll_ms':600,'freshness_ms':1000,'deadline_seconds':120,
    'preventive_tokens':200000,'tolerance_tokens':700000,'policy_revision':11,'carry_in_admissions':6,'carry_in_tokens':89473,
    'max_new_admissions':5,'max_cumulative_admissions':11,'persistence':'unchanged','deduplication':'none added','poll_loop':'unchanged','pty_cadence':'unchanged'},
 'tests':'Existing100ms rollback and pre-snapshot path tests specify100ms explicitly. Existing40ms interrupt override remains. Added default250ms accepts211ms/refuses251ms test. Global600ms/freshness/120s/fence tests remain unchanged.',
 'predecessor_failures':'Preserved original61/63CLI-composition run with100ms read failures at211.2865ms and153.5869ms; not relabeled as passes.',
 'poll740_review':'maximum_previous_poll_ms covers the entire poll including fault persistence/containment after fence. The retained case already had READ_BUDGET_EXCEEDED and denied useful success; it is not evidence of an accepted740ms cycle. Cleanup duration was not separately measured, so the entire excess cannot be attributed to cleanup.',
 'limits':'600ms remains the aggregate acceptance budget and1s the effect freshness boundary. OS IO/scheduling are not preemptible; no physical wall-clock or statistical tail-latency guarantee is asserted.',
 'proposal_metadata_required':{'snapshot_ms':250,'read_budget_ms':250,'schema_initialization_ms':250,'aggregate_poll_ms':600,'freshness_ms':1000},
 'authorization_boundary':'Root preparation approval and final real-M1 execution approval are separate. This artifact neither grants execution authorization nor satisfies real DX-T39/T40/AC11 acceptance.',
 'predecessor_freeze_sha256':sha(manifest_path),'predecessor_final_xml_sha256':sha(Q/'predecessor-cli-final.xml'),
 'final_xml_sha256':sha(Q/'final.xml'),'module_origins_sha256':sha(Q/'module-origins.json'),'changelog_sha256':sha(ROOT/'CHANGELOG.md'),
 'real_closed_database_sha256':sha(db),'prior_freeze_sources_verified_unchanged':True}
write(Q/'qualification.json',report)
manifest={'classification':classification,'policy_revision':11,'read_budget_ms':250,
 'runtime':[{'path':p.relative_to(ROOT).as_posix(),'sha256':sha(p)} for p in runtime],
 'tests':[{'path':p.relative_to(ROOT).as_posix(),'sha256':sha(p)} for p in tests],
 'qualification_sha256':sha(Q/'qualification.json'),'predecessor_freeze_sha256':sha(manifest_path)}
write(Q/'runtime-freeze.json',manifest)
public=Q/'public-allowlist';public.mkdir();items=[]
artifacts=runtime+tests+[ROOT/'CHANGELOG.md',ROOT/'predecessor-cli-freeze.json']+[Q/name for name in (
 'final.xml','predecessor-cli-final.xml','predecessor-timing-failures.json','real-closed-db-evidence.json',
 'final-run-sources.json','module-origins.json','qualification.json','runtime-freeze.json','run_final.py','freeze.py')]
for p in artifacts:
    relative=p.relative_to(ROOT);out=public/relative;out.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,out)
    items.append({'path':relative.as_posix(),'sha256':sha(out),'bytes':out.stat().st_size})
write(Q/'public-allowlist.json',{'files':items,'excludes':['database files','private fixture ledgers','credentials','real stdout','venv','pycache']})
print(json.dumps({'classification':classification,'result':result,'runtime_freeze_sha256':sha(Q/'runtime-freeze.json'),
                  'public_allowlist_sha256':sha(Q/'public-allowlist.json'),'qualification_sha256':sha(Q/'qualification.json'),'files':len(items)},indent=2))

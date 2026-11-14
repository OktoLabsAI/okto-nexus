"""Freeze offline qualification; never start services or provider processes."""
from pathlib import Path
import hashlib,json,shutil,xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1];Q=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,value):
    with p.open('x',encoding='utf-8') as f:json.dump(value,f,indent=2)
run=json.loads((Q/'final-run-sources.json').read_text())
assert all(sha(ROOT/name)==digest for name,digest in run.items()),'SOURCE_CHANGED_DURING_FINAL_TEST'
prior=Path('C:/Users/jpamb/AppData/Local/Temp/m1-v11-reader-candidate-tk7v4a1v')
assert sha(prior/'qualification-final-20261114/runtime-freeze.json')=='a41f818035ce3ccbc77e6cae9bc6c96fb4cc08d1d2081001f8b0439f49b589ef'
old=json.loads((ROOT/'predecessor-freeze.json').read_text())
assert all(sha(prior/item['path'])==item['sha256'] for item in old['runtime']+old['tests'])
attempts=[]
for p in sorted(Q.glob('*.xml')):
    s=ET.parse(p).getroot().find('testsuite')
    attempts.append({'path':p.name,'sha256':sha(p),'tests':int(s.get('tests')),'failures':int(s.get('failures')),
        'errors':int(s.get('errors')),'seconds':float(s.get('time')),
        'failed_cases':[c.get('name') for c in s.findall('testcase') if c.find('failure') is not None or c.find('error') is not None]})
final=next(x for x in attempts if x['path']=='final.xml')
real_path=next((Q/'final-tmp').glob('test_real_closed*/real-reader-evidence.json'))
real=json.loads(real_path.read_text());shutil.copyfile(real_path,Q/'real-closed-db-evidence.json')
db=Path('C:/Users/jpamb/AppData/Local/Temp/m1-v10-bundle-pscf18t5/campaign/nexus-home/nexus.db')
assert sha(db)==real['source_db_sha256']=='a1e7b0afee7aee41c00917ed5fa302b502324d70bc45c3e37e3220b9d2276a8b'
profile=json.loads((Q/'phase-profile.json').read_text())
runtime=sorted([p for p in (ROOT/'controller').glob('*.py') if not p.name.startswith('test_')]+[ROOT/name for name in ('m1_v10_work.py','publication.py','response_loss.py')])
tests=sorted((ROOT/'controller').glob('test_*.py'))
classification='FINAL_OFFLINE_SUITE_PASS_WITH_HISTORICAL_TIMING_LIMITATIONS' if not final['failures'] and not final['errors'] else 'FINAL_OFFLINE_SUITE_HAS_FAILURES_NOT_QUALIFIED'
report={'classification':classification,'scope':'Offline harness candidate only; no product mutations, services, provider, credentials or frozen-v10 changes.',
 'limits':{'schema_initialization_ms':250,'snapshot_ms':100,'aggregate_poll_ms':600,'effect_observation_freshness_ms':1000,
           'request_deadline_seconds':120,'preventive_tokens':200000,'tolerance_tokens':700000},
 'contract':[
   'Canonical schema initialization precedes admission; Core and setup lazy initialization is separately bounded250ms and charged to the same600ms poll.',
   'Public Canonical/Core observation and setup poll measure path and identity checks, projection, final identity validation, rollback and successful return. Only separately measured schema initialization time is deducted from the100ms observation budget.',
   'ReadOnly.open cached validation/path/SQL/rollback is also checked at100ms. No persistent transaction between polls. Legitimate DDL can reprepare inside the read budget.',
   'SQLite progress callbacks check aggregate600ms as well as local budgets; explicit clock checks follow IO. Windows IO and scheduler stalls cannot be preempted:600ms/100ms are fail-closed acceptance budgets, not physical wall-time guarantees.',
   'A complete poll publishes freshness based on poll START plus1s, only after final persistence and fresh-clock deadline checks. A faulted or interrupted poll does not renew freshness.',
   'Every real effect boundary in the serial API worker checks current clock for freshness, in-progress poll budget,120s deadline and token threshold. The first setup receives a successful empty poll before reservation and a fence check immediately before its dispatch callback.',
   'Usage updates reach the shared effect fence before durable persistence can block. Every fault closes the fence before its persistence.',
   'Aggregate-only exhaustion preserves a safely rolled-back reader for subsequent late observations. Any cleanup failure discards connections while preserving the original exception.',
   'All settled requests remain observed for late usage. No stream deduplication or persistence redesign was introduced. Cadence faults concern unsettled work; idle history does not imply active execution.',
   'Containment and failure persistence can outlast the observation budget after the fence is closed; selected normal-stop action is not proof of native exit.'
 ],
 'attempts':attempts,'final_run_sources_sha256':sha(Q/'final-run-sources.json'),
 'preserved_first_v2_failures':['WinError5 replacing controller.json; a synthetic worker reads the ledger concurrently, but the precise Windows handle blocker was not established. No retry added.',
   'Four-work case observed poll1203.96ms and cadence1419.20ms, correctly fenced and denied successful final publication. This remains evidence of a possible latency tail.'],
 'profile':{'path':'phase-profile.json','sha256':sha(Q/'phase-profile.json'),'runs':1,'four_work_passed':profile['exit_code']==0,
   'polls':len(profile['polls']),'maximum_poll_ms':max(x['elapsed_ms'] for x in profile['polls']),'totals':profile['totals'],
   'note':'Nested phase timings overlap. Profile used loaded modules before the final post-persist deadline guard was added; the final complete suite separately covers frozen bytes. No tail-latency robustness claim.'},
 'real_closed_database':{'sha256':sha(db),'schema_initialization_ms':real['schema_preparation']['initializations'][0]['elapsed_ms'],
    'warm_read_min_ms':min(real['warm_read_ms']),'warm_read_max_ms':max(real['warm_read_ms']),
    'cold_definition':'New connection/schema cache; OS cache not purged.'},
 'independent_review':'v11_preparation reviewed cleanup, public observation timing, freshness, pre-fsync token fence, first setup and final deadline checks; no remaining blocker reported.',
 'composition_requirement':'Policy and ancestry remain comparison-v10. Preparation owner must compose revision11, carry6 admissions/89473 tokens, maximum5 new/11 cumulative, and separately qualify installed composition.',
 'conclusion':'Use the final suite result for functional status. Retain all failures and the explicit IO/preemption/tail-latency limitations; do not describe this as statistical availability qualification.'}
write(Q/'qualification.json',report)
manifest={'classification':classification,'runtime':[{'path':p.relative_to(ROOT).as_posix(),'sha256':sha(p)} for p in runtime],
          'tests':[{'path':p.relative_to(ROOT).as_posix(),'sha256':sha(p)} for p in tests],
          'qualification_sha256':sha(Q/'qualification.json'),'predecessor_freeze_sha256':sha(ROOT/'predecessor-freeze.json')}
write(Q/'runtime-freeze.json',manifest)
sources=runtime+tests+[ROOT/'predecessor-freeze.json']+sorted(Q.glob('*.xml'))+[Q/name for name in ('qualification.json','runtime-freeze.json','real-closed-db-evidence.json','phase-profile.json','final-run-sources.json','profile_four_work.py','freeze.py')]
public=Q/'public-allowlist';public.mkdir();items=[]
for p in sources:
    relative=p.relative_to(ROOT);out=public/relative;out.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,out)
    items.append({'path':relative.as_posix(),'sha256':sha(out),'bytes':out.stat().st_size})
write(Q/'public-allowlist.json',{'files':items,'excludes':['databases','private fixture ledgers','credentials','venv','test temp roots','pycache']})
print(json.dumps({'classification':classification,'final':final,'runtime_freeze_sha256':sha(Q/'runtime-freeze.json'),
                  'allowlist_sha256':sha(Q/'public-allowlist.json'),'public_files':len(items)},indent=2))

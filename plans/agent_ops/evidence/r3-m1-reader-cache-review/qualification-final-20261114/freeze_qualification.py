"""Offline evidence packaging. No services, provider, credentials or database writes."""
from pathlib import Path
import hashlib,json,shutil,xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
Q=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,value):
    with p.open('x',encoding='utf-8') as f:json.dump(value,f,indent=2)

source=json.loads((ROOT/'frozen-source-hashes.json').read_text())
assert all(sha(Path(p))==h for p,h in source.items()),'FROZEN_V10_SOURCE_CHANGED'
runtime=sorted([p for p in (ROOT/'controller').glob('*.py') if not p.name.startswith('test_')]+[ROOT/n for n in ('m1_v10_work.py','publication.py','response_loss.py')])
tests=sorted((ROOT/'controller').glob('test_*.py'))
xmls=sorted(ROOT.glob('tests-*.xml'))+sorted(Q.glob('tests-*.xml'))
attempts=[]
for p in xmls:
    s=ET.parse(p).getroot().find('testsuite')
    attempts.append({'path':p.relative_to(ROOT).as_posix(),'sha256':sha(p),'tests':int(s.get('tests')),
        'failures':int(s.get('failures')),'errors':int(s.get('errors')),'seconds':float(s.get('time')),
        'failed_cases':[c.get('name') for c in s.findall('testcase') if c.find('failure') is not None or c.find('error') is not None]})
real_path=next((Q/'test-tmp-qualified').glob('test_real_closed*/real-reader-evidence.json'))
real=json.loads(real_path.read_text())
closed=Path('C:/Users/jpamb/AppData/Local/Temp/m1-v10-bundle-pscf18t5/campaign/nexus-home/nexus.db')
assert sha(closed)==real['source_db_sha256']=='a1e7b0afee7aee41c00917ed5fa302b502324d70bc45c3e37e3220b9d2276a8b'
ledger=json.loads(next((Q/'test-tmp-qualified').glob('test_one_global*/controller.json')).read_text())
failure={'faults':ledger['faults'],'request_error':ledger['requests']['setup-remote']['first_observation_error'],
         'independent_observation':ledger['independent_observation']}
write(Q/'timing-failure-safe-projection.json',failure)
shutil.copyfile(real_path,Q/'real-closed-db-evidence.json')
diagnosis=Path('C:/Users/jpamb/AppData/Local/Temp/m1-v10-sqlite-reader-diagnosis-qa6r8kmw/diagnosis.json')
report={
 'classification':'FUNCTIONAL_PASS_WITH_OBSERVED_TIMING_FAILURES_NOT_ROBUST_REAL_CAMPAIGN_QUALIFICATION',
 'scope':'Offline candidate only. No provider, credentials, services, product mutations, commits, or frozen v10 changes.',
 'runtime_changed_this_resumption':False,
 'test_change':'Parameterized final-error publication for snapshot_read and schema_initialization; asserts safe metadata, primary error, zero POST and zero reservation.',
 'attempts':attempts,
 'latest_full_composition':{'passed':36,'failed':2,'total':38,'interpretation':'Two temporal failures; no claim of an all-green complete run.'},
 'targeted_followup':{'passed':2,'failed':0,'repetitions':1,'interpretation':'Both timing failures passed once in isolation with identical runtime and limits. Does not establish availability under load.'},
 'additional_publication_test':{'passed':2,'phases':['snapshot_read','schema_initialization']},
 'infrastructure_error':'First resumption attempt had38 fixture setup errors: missing parent of --basetemp. No test body ran. XML retained unchanged; directory creation fixed invocation only.',
 'budget_contract':{
   'origin':'40ms was inherited from the campaign harness;100ms is the candidate explicit initialization ceiling. No product/API latency SLA or empirical tail guarantee was established.',
   'initialization_ms':100,'snapshot_ms':40,
   'initialization_inside':'safe_path and identity validation; SQLite connect and pragmas; sqlite_schema count and schema_version; identity revalidation and rollback; elapsed check before cache admission.',
   'initialization_outside':'ReadOnly constructor root resolution and CanonicalIntentReader prechecks precede prepare; diagnostics/cache bookkeeping after elapsed check; cleanup after failure.',
   'snapshot_inside':'After prepare and extra Path.resolve: identity validation, BEGIN, schema_version and legitimate DDL reprepare, yielded projection/scope validation, final elapsed check.',
   'snapshot_outside':'Cached prepare safe_path/identity checks and Path.resolve precede snapshot timer; final identity revalidation and rollback follow elapsed check. Thus40ms is not an end-to-end read wall-clock ceiling.',
   'preemption_limit':'SQLite progress callback every200 VM instructions and elapsed checks cannot preempt Windows filesystem IO/scheduler stalls. Busy timeout is40ms; failure latches reader and closes caches; no hidden retry.',
   'remaining_setup_reader':'setup_journal remains unchanged: fresh connection each poll,40ms SQLite progress budget; its separate timing failure remains relevant.'},
 'observed_timings':{'real_full_schema_initialization_ms':real['schema_preparation']['initializations'][0]['elapsed_ms'],
   'real_warm_read_end_to_end_min_ms':min(real['warm_read_ms']),'real_warm_read_end_to_end_max_ms':max(real['warm_read_ms']),
   'failed_core_initialization':'Exceeded100ms, SQLITE_INTERRUPT during sqlite_schema count; exact elapsed was not serialized by that failing test. Cannot report a measured maximum.',
   'failed_setup_reader':'SQLITE_INTERRUPT9 during setup-remote observation; no phase timing retained. Controller persisted OBSERVATION_UNKNOWN and selected containment.',
   'cold_definition':'New connection and schema cache; OS filesystem cache was not purged.'},
 'verified_behaviors':['real closed DB hash unchanged before/after','cached connection reused with fresh rollback-delimited transaction',
   'WAL writer and checkpoint progress between reads','fail closed on identity/path/schema rollback and40ms/100ms exhaustion',
   'legitimate late Core DDL on same connection','owner-thread enforcement and explicit connection closure',
   'CONTROLLER_CLOSED before reader IO/reservation','final blocked public snapshot on read or initialization failure with primary exception retained'],
 'causal_diagnosis':{'path':str(diagnosis),'sha256':sha(diagnosis),'summary':'Prior native sqlite3_prepare_v2 interrupted at41.08ms before sqlite3_step. Warm prepared queries were fast; causal mechanism supports persistent schema cache, not retrospective exact timing of the original failure.'},
 'real_closed_db_sha256':sha(closed),'frozen_source_hashes_verified':True,
 'environment':{'python':'3.13 reference qualification venv','pytest':'9.2.0','products':'Imported from reference venv site-packages','autoload_plugins':False},
 'runtime_rebase_required':'Candidate policy/controller ancestry and wrapper identifiers intentionally remainv10 for comparison. Preparation owner must rebase carry6/89473/maxnew5/maxcum11 and qualify composedv11 independently.',
 'recommendation':'Freeze these bytes for review. Do not describe timing availability as qualified. Root must explicitly choose any future budget revision against observation cadence/freshness; retain fail-closed and bounded work semantics.'}
write(Q/'qualification.json',report)
manifest={'classification':report['classification'],'runtime':[{'path':p.relative_to(ROOT).as_posix(),'sha256':sha(p)} for p in runtime],
          'tests':[{'path':p.relative_to(ROOT).as_posix(),'sha256':sha(p)} for p in tests],
          'qualification_sha256':sha(Q/'qualification.json'),'frozen_v10_verified':True}
write(Q/'runtime-freeze.json',manifest)
public=Q/'public-allowlist';public.mkdir()
sources=runtime+tests+xmls+[ROOT/'frozen-source-hashes.json',Q/'qualification.json',Q/'runtime-freeze.json',Q/'timing-failure-safe-projection.json',Q/'real-closed-db-evidence.json',Path(__file__).resolve()]
items=[]
for p in sources:
    relative=p.relative_to(ROOT)
    out=public/relative;out.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,out)
    items.append({'path':relative.as_posix(),'sha256':sha(out),'bytes':out.stat().st_size})
write(Q/'public-allowlist.json',{'files':items,'excludes':['databases','credentials','private fixture ledgers','venv','test temp roots','pycache'],'source_root':str(ROOT)})
print(json.dumps({'runtime_freeze':str(Q/'runtime-freeze.json'),'sha256':sha(Q/'runtime-freeze.json'),'public_allowlist_sha256':sha(Q/'public-allowlist.json'),'files':len(items),'classification':report['classification']},indent=2))

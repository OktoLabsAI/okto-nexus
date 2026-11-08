"""Own closed campaign DB only: read-only, allowlisted metadata projections."""
from pathlib import Path
import hashlib,json,sqlite3,time,sys

D=Path(__file__).parent
DB=Path('C:/Users/jpamb/AppData/Local/Temp/m1-v10-bundle-pscf18t5/campaign/nexus-home/nexus.db')
SQL=("SELECT operation_id,json_extract(resolved_json,'$.client_intent_id') AS intent,"
 "json_extract(resolved_json,'$.scope') AS scope,json_extract(initial_turn_json,'$.operation_id') AS initial_turn "
 "FROM execution_client_intents WHERE server_id=? AND actor_agent_id=? AND client_intent_id=? LIMIT 2")
PARAMS=('diagnostic-own-empty-table','diagnostic-own-empty-table','m1v10-local-work-01')
def stamp():return time.perf_counter_ns()
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def error_meta(error):return {'type':type(error).__name__,'sqlite_errorcode':getattr(error,'sqlite_errorcode',None),'sqlite_errorname':getattr(error,'sqlite_errorname',None)}
def open_db():
 db=sqlite3.connect(DB.as_uri()+'?mode=ro',uri=True,timeout=.04)
 db.execute('PRAGMA query_only=ON');db.execute('PRAGMA busy_timeout=40')
 return db
before=digest(DB)
reports=[]
def run_one(index,connection=None,budget=.04,prewarm=False):
 own=connection is None;started=stamp();timings={};progress=[];traces=[];phase=['connect']
 db=connection or sqlite3.connect(DB.as_uri()+'?mode=ro',uri=True,timeout=.04)
 timings['connect_ms']=(stamp()-started)/1e6
 def measured(label,fn):
  phase[0]=label;t=stamp()
  try:return fn()
  finally:timings[label+'_ms']=(stamp()-t)/1e6
 try:
  measured('query_only',lambda:db.execute('PRAGMA query_only=ON'))
  measured('busy_timeout',lambda:db.execute('PRAGMA busy_timeout=40'))
  if prewarm:
   measured('schema_prewarm',lambda:db.execute("SELECT count(*) FROM sqlite_schema").fetchone())
   started=stamp() # explicit comparative experiment, never the frozen production path
  def progress_cb():
   elapsed=(stamp()-started)/1e9
   progress.append({'phase':phase[0],'elapsed_ms':elapsed*1000,'after_trace':bool(traces)})
   return int(elapsed>=budget)
  db.set_progress_handler(progress_cb,200)
  def trace(_sql):traces.append({'phase':phase[0],'elapsed_ms':(stamp()-started)/1e6})
  db.set_trace_callback(trace)
  measured('begin',lambda:db.execute('BEGIN'))
  traces.clear()
  cursor=measured('prepare_and_first_step',lambda:db.execute(SQL,PARAMS))
  rows=measured('fetch',cursor.fetchall)
  # No selected row body is emitted. This campaign never admitted a work intent.
  assert rows==[], 'Unexpected own intent record; stop projection'
  result={'status':'EMPTY_INTENT_CONFIRMED','count':len(rows)}
 except sqlite3.Error as error:result={'status':'SQLITE_ERROR',**error_meta(error)}
 finally:
  elapsed=(stamp()-started)/1e6
  db.set_progress_handler(None,0);db.set_trace_callback(None)
  measured('rollback',db.rollback)
  if own:measured('close',db.close)
 reports.append({'index':index,'mode':'new_connection_prewarmed' if prewarm else 'new_connection' if own else 'reused_connection',
  'budget_ms':budget*1000,'timings':timings,'read_elapsed_ms':elapsed,'progress_calls':len(progress),
  'first_progress':progress[0] if progress else None,'last_progress':progress[-1] if progress else None,
  'target_trace':traces,'result':result})

for i in range(20):run_one(i)
with open_db() as db:
 for i in range(10):run_one(i,db)
for i in range(5):run_one(i,prewarm=True)
# Bounded diagnostic metadata and query plan, not a changed production budget.
with open_db() as db:
 deadline=time.monotonic()+1
 db.set_progress_handler(lambda:int(time.monotonic()>=deadline),200)
 metadata={
  'sqlite_version':sqlite3.sqlite_version,'python_version':sys.version.split()[0],
  'db_bytes':DB.stat().st_size,
  'schema_counts':dict(db.execute('SELECT type,count(*) FROM sqlite_schema GROUP BY type').fetchall()),
  'selected_table_counts':{name:db.execute('SELECT count(*) FROM '+name).fetchone()[0] for name in
    ('execution_client_intents','execution_operations','execution_sessions','execution_receipts')},
  'intent_columns':[{'name':row[1],'type':row[2],'primary_key':row[5]} for row in db.execute('PRAGMA table_info(execution_client_intents)')],
  'intent_indexes':[{'name':row[1],'unique':row[2],'origin':row[3]} for row in db.execute('PRAGMA index_list(execution_client_intents)')],
  'query_plan':[list(row) for row in db.execute('EXPLAIN QUERY PLAN '+SQL,PARAMS)],
 }
after=digest(DB)
assert before==after
result={'status':'READ_ONLY_DIAGNOSTIC','db_sha256_before':before,'db_sha256_after':after,
 'db_path':str(DB),'predicate_basis':'All selected work tables confirmed empty; diagnostic parameter values avoid auth/profile reads.',
 'cold_definition':'New SQLite connection/schema cache. OS filesystem cache is uncontrolled and file hashing itself reads pages.',
 'metadata':metadata,'samples':reports}
(D/'probe.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'report':str(D/'probe.json'),'sha256':digest(D/'probe.json'),'db_unchanged':before==after,
 'metadata':metadata,'summaries':[{'mode':mode,'count':len(items),'failures':sum(s['result']['status']=='SQLITE_ERROR' for s in items),
   'min_ms':min(s['read_elapsed_ms'] for s in items),'max_ms':max(s['read_elapsed_ms'] for s in items),
   'first':items[0]} for mode in ('new_connection','reused_connection','new_connection_prewarmed') if (items:=[s for s in reports if s['mode']==mode])]}))

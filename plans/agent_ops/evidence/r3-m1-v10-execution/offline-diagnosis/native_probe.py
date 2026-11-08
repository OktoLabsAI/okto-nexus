"""Separate SQLite C prepare/step timings; read-only closed own DB only."""
from pathlib import Path
import ctypes as C
import hashlib,json,time

D=Path(__file__).parent
DB=Path('C:/Users/jpamb/AppData/Local/Temp/m1-v10-bundle-pscf18t5/campaign/nexus-home/nexus.db')
DLL=Path('C:/Python313/DLLs/sqlite3.dll')
lib=C.CDLL(str(DLL))
def signature(name,args,result):
 fn=getattr(lib,name);fn.argtypes=args;fn.restype=result;return fn
ptr=C.c_void_p;integer=C.c_int;chars=C.c_char_p
initialize=signature('sqlite3_initialize',[],integer)
assert initialize()==0
open_v2=signature('sqlite3_open_v2',[chars,C.POINTER(ptr),integer,chars],integer)
close=signature('sqlite3_close_v2',[ptr],integer)
prepare=signature('sqlite3_prepare_v2',[ptr,chars,integer,C.POINTER(ptr),C.POINTER(chars)],integer)
step=signature('sqlite3_step',[ptr],integer)
finalize=signature('sqlite3_finalize',[ptr],integer)
bind=signature('sqlite3_bind_text',[ptr,integer,chars,integer,ptr],integer)
busy=signature('sqlite3_busy_timeout',[ptr,integer],integer)
progress_type=C.CFUNCTYPE(integer,ptr)
progress=signature('sqlite3_progress_handler',[ptr,integer,progress_type,ptr],None)
version=signature('sqlite3_libversion',[],chars)
NULL_CB=progress_type()
SQL=("SELECT operation_id,json_extract(resolved_json,'$.client_intent_id') AS intent,"
 "json_extract(resolved_json,'$.scope') AS scope,json_extract(initial_turn_json,'$.operation_id') AS initial_turn "
 "FROM execution_client_intents WHERE server_id=? AND actor_agent_id=? AND client_intent_id=? LIMIT 2").encode()
PARAMS=(b'diagnostic-own-empty-table',b'diagnostic-own-empty-table',b'm1v10-local-work-01')
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def now():return time.perf_counter_ns()
def execute(db,sql):
 statement=ptr();code=prepare(db,sql,len(sql),C.byref(statement),None)
 if code:raise RuntimeError('DIAGNOSTIC_PREPARE_'+str(code))
 try:
  while (code:=step(statement))==100:pass # never read arbitrary selected values
  if code!=101:raise RuntimeError('DIAGNOSTIC_STEP_'+str(code))
 finally:finalize(statement)
before=digest(DB);samples=[]
def sample(index,db=None,prewarm=False):
 own=db is None;db=db or ptr();times={};phase=['open'];started=now();calls=[]
 if own:
  code=open_v2((DB.as_uri()+'?mode=ro').encode(),C.byref(db),1|64,None)
  assert code==0
 times['open_ms']=(now()-started)/1e6
 phase[0]='query_only';t=now();execute(db,b'PRAGMA query_only=ON');times['query_only_ms']=(now()-t)/1e6
 phase[0]='busy_timeout';t=now();assert busy(db,40)==0;times['busy_timeout_ms']=(now()-t)/1e6
 if prewarm:
  phase[0]='schema_prewarm';t=now();execute(db,b'SELECT count(*) FROM sqlite_schema');times['schema_prewarm_ms']=(now()-t)/1e6
  started=now()
 @progress_type
 def handler(_):
  elapsed=(now()-started)/1e6;calls.append({'phase':phase[0],'elapsed_ms':elapsed})
  return int(elapsed>=40)
 progress(db,200,handler,None)
 statement=ptr();status={}
 try:
  phase[0]='begin';t=now();execute(db,b'BEGIN');times['begin_ms']=(now()-t)/1e6
  phase[0]='prepare';t=now();code=prepare(db,SQL,len(SQL),C.byref(statement),None);times['prepare_ms']=(now()-t)/1e6
  status={'prepare_code':code,'step_code':None,'returned_rows':0}
  if code==0:
   phase[0]='bind';t=now()
   for i,value in enumerate(PARAMS,1):assert bind(statement,i,value,len(value),None)==0
   times['bind_ms']=(now()-t)/1e6
   phase[0]='step';t=now();code=step(statement);times['step_ms']=(now()-t)/1e6
   status['step_code']=code
   assert code!=100,'Unexpected own intent record'
 finally:
  elapsed=(now()-started)/1e6
  if statement:finalize(statement)
  progress(db,0,NULL_CB,None)
  execute(db,b'ROLLBACK')
  if own:assert close(db)==0
 samples.append({'index':index,'mode':'new_connection_prewarmed' if prewarm else 'new_connection' if own else 'reused_connection',
  'timings':times,'read_elapsed_ms':elapsed,'progress_calls':len(calls),
  'first_progress':calls[0] if calls else None,'last_progress':calls[-1] if calls else None,'status':status})

for i in range(12):sample(i)
db=ptr();assert open_v2((DB.as_uri()+'?mode=ro').encode(),C.byref(db),1|64,None)==0
try:
 for i in range(8):sample(i,db)
finally:assert close(db)==0
for i in range(4):sample(i,prewarm=True)
after=digest(DB);assert before==after
result={'status':'READ_ONLY_C_API_INSTRUMENTATION','sqlite_version':version().decode(),
 'db_sha256_before':before,'db_sha256_after':after,'library':str(DLL),'library_sha256':digest(DLL),
 'cold_definition':'New SQLite connection/schema cache; no OS cache purge performed.',
 'samples':samples}
(D/'native-probe.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'report':str(D/'native-probe.json'),'sha256':digest(D/'native-probe.json'),
 'summaries':[{'mode':mode,'samples':len(items),'prepare_failures':sum(s['status']['prepare_code']!=0 for s in items),
  'prepare_min_ms':min(s['timings']['prepare_ms'] for s in items),'prepare_max_ms':max(s['timings']['prepare_ms'] for s in items),
  'step_max_ms':max((s['timings'].get('step_ms',0) for s in items)),
  'first':items[0]} for mode in ('new_connection','reused_connection','new_connection_prewarmed') if (items:=[s for s in samples if s['mode']==mode])]}))

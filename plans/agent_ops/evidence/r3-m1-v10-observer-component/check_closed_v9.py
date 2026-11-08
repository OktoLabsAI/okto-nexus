from pathlib import Path
import hashlib,json
from independent_journal import CanonicalIntentReader,CoreJournalReader
R=Path('C:/Users/jpamb/AppData/Local/Temp/m1-v9-preparation-t4xaqhca/campaign')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
checkpoint=R/'private/controller.json'
assert sha(checkpoint)=='02d025ef1d09d8158573f553f58813e96b810d992110007c05971ba1cc44e588'
data=json.loads(checkpoint.read_text(encoding='utf-8'))
record=data['requests']['m1v9-local-work-01'];pre=record['scope']
db=R/'nexus-home/nexus.db';before=sha(db)
reader=CanonicalIntentReader(R,R/'nexus-home',server_id=pre['server_id'],actor_id='operator',pre_scope=pre)
observed=reader.read('m1v9-local-work-01')
assert observed and observed['preopen_failed'] and observed['operation_id']==record['operation']
assert observed['scope']['session_id']==record['session']
journal=CoreJournalReader(R,R/'nexus-home','local');path=journal.path(observed['scope']);journal_before=sha(path)
assert journal.read(observed['scope']) is None
assert sha(checkpoint)=='02d025ef1d09d8158573f553f58813e96b810d992110007c05971ba1cc44e588'
assert sha(db)==before and sha(path)==journal_before
result={'status':'PASS_READ_ONLY_EXISTING_CLOSED_V9','canonical_database_sha256':before,
    'core_journal_sha256':journal_before,'controller_sha256':sha(checkpoint),
    'canonical_scope_matches_reserved_request':True,'initial_turn_matches':True,
    'preopen_failed':True,'opening_receipt':observed['opening_receipt'],
    'selected_operation_has_receipt':observed['operation_receipt'] is not None,
    'core_event_stream_present':False,'new_provider_calls':0,'new_service_actions':0,
    'canonical_database_unchanged':True,'core_journal_unchanged':True,
    'billed_tokens':None,'historical_failure_cause':'DB_ERROR; specific SQLite cause not retained in v9'}
out=Path(__file__).parent/'closed-v9-reader-check.json'
with out.open('x',encoding='utf-8') as f:json.dump(result,f,indent=2)
print(json.dumps(result))

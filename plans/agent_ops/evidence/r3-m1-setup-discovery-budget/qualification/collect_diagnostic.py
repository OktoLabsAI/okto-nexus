"""Read only allowlisted v11 evidence and SQL metadata; export closed projections."""
from pathlib import Path
import hashlib
import json
import sqlite3

Q=Path(__file__).resolve().parent
B=Path('C:/Users/jpamb/AppData/Local/Temp/m1-v11-bundle-racan37z')
C=B/'campaign'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
read=lambda p:json.loads(p.read_bytes())
public_names=['local-setup-dispatch.json','local-setup-result.json','lifecycle-nexus-stop.json',
    'lifecycle-nexus-stop-result.json','nexus-exit-proof.json','cleanup-nexus.json']
sources={name:sha(C/'public'/name) for name in public_names}
service_log=C/'nexus-home/logs/service.jsonl'
service_events=[{k:row.get(k) for k in ['timestamp','component','code','generation','state','error_code']}
    for row in map(json.loads,service_log.read_text().splitlines())]
proof=read(C/'public/nexus-exit-proof.json')
assert proof['exit_confirmed'] is True and proof['force_used'] is False
result=read(C/'public/local-setup-result.json')
dispatch=read(C/'public/local-setup-dispatch.json')
stop=read(C/'public/lifecycle-nexus-stop.json')
checkpoint=read(C/'private/controller.json')
request=checkpoint['requests']['m1v11-local-setup']
error=request['first_observation_error']
profile=read(C/'nexus-home/terminal/profiles/m1v11-local.json')
candidate=profile['request']['candidate_ref']
db_path=C/'nexus-home/nexus.db'
assert not list(db_path.parent.glob('nexus.db-*')), 'Refuse immutable view with possible WAL/SHM'
queries={
    'version_observation':'SELECT candidate_ref,version,platform,observed_at FROM execution_local_observations WHERE candidate_ref=?',
    'snapshot_metadata':'SELECT publication_sequence,inventory_revision,received_at,observation_age_ms FROM execution_inventory_snapshots ORDER BY publication_sequence',
    'candidate_state':'SELECT s.publication_sequence,json_extract(j.value,?),json_extract(j.value,?),json_extract(j.value,?) FROM execution_inventory_snapshots s,json_each(s.canonical_projection,?) j WHERE s.publication_sequence=(SELECT MAX(publication_sequence) FROM execution_inventory_snapshots) AND json_extract(j.value,?)=?',
}
with sqlite3.connect(db_path.as_uri()+'?mode=ro&immutable=1',uri=True) as db:
    observations=db.execute(queries['version_observation'],(candidate,)).fetchall()
    snapshots=db.execute(queries['snapshot_metadata']).fetchall()
    state=db.execute(queries['candidate_state'],('$.adapter_id','$.state','$.version',
        '$.availability.availability','$.candidate_ref',candidate)).fetchall()
projection={
    'first_observation_error':{'exception_type':error['exception_type'],'reason':error['reason'],
        'reader':{k:error['reader'][k] for k in ['phase','budget_ms','elapsed_ms']}},
    'faults':checkpoint['faults'],
    'profile':{'state':profile['state'],'version_check_required':profile['version_check_required']},
    'version_observations':observations,'inventory_snapshots':snapshots,'final_candidate_state':state,
    'connection_tests_directory_exists':(C/'nexus-home/connection-tests').exists(),
    'setup_monitor':{k:result['monitor'][k] for k in ['started','journal','high_water','usage_seen','terminal']},
    'accounting':{k:result['summary'][k] for k in ['reserved_requests','new_reserved_requests',
        'known_observed_tokens','new_observed_tokens','carry_in_tokens','final_or_billed_usage']},
    'observer_maximum_poll_ms':checkpoint['independent_observation']['budgets']['maximum_previous_poll_ms'],
    'cli':{k:result[k] for k in ['cli_exit','reported_state','reported_code','maximum_poll_start_interval_seconds','poll_count']},
}
encoded=json.dumps(projection,sort_keys=True,separators=(',',':')).encode()
site=B/'draft/installation/venv/Lib/site-packages/okto_nexus'
source_paths=[B/'draft/controller/setup_journal.py',B/'draft/controller/independent_journal.py',
    B/'draft/controller/independent_controller.py',B/'draft/controller/api_worker.py',
    site/'application/terminal_connection.py',site/'application/execution_local_observations.py',
    site/'bootstrap/embedded_inventory.py']
output={
    'classification':'SANITIZED_V11_POST_EXIT_READONLY_DIAGNOSIS_NOT_M1_ACCEPTANCE',
    'public_source_sha256':sources,
    'own_service_log_sha256':sha(service_log),'service_events':service_events,
    'source_code_sha256':{str(p.relative_to(B)):sha(p) for p in source_paths},
    'private_projection_sha256':hashlib.sha256(encoded).hexdigest(),
    'projection_hash_encoding':'JSON sort_keys=True,separators=comma-colon,UTF8; projection below only',
    'projection':projection,'immutable_sql_queries':queries,
    'timeline':[
        {'event':'setup_cli_dispatched','epoch':dispatch['time'],'utc':'2026-11-14T14:34:58.652596Z'},
        {'event':'last_inventory_published_NOT_PROBED','utc':'2026-11-14T14:36:03.591Z','publication_sequence':15},
        {'event':'normal_stop_reserved','epoch':stop['time'],'utc':'2026-11-14T14:36:09.876649Z'},
        {'event':'version_0_157_0_observation_committed','utc':'2026-11-14T14:36:14.521306Z'},
        {'event':'service_DRAINED_and_EXIT_reported','utc':'2026-11-14T14:36:22Z'},
        {'event':'setup_wrapper_result_recorded','epoch':result['finished'],'utc':'2026-11-14T14:37:04.611052Z'},
    ],
    'established':['First recorded observer failure was SETUP_READ_BUDGET_EXCEEDED:317.696ms against250ms, phase snapshot_read.',
        'The wrapper applied a SQL-labelled whole-poll budget even when discovery returned without a journal or SQL query.',
        'The independent controller caught JournalUnknown, retained first_observation_error, selected OBSERVATION_UNKNOWN and normal stop.',
        'A durable version observation succeeded for the selected candidate, but the last inventory publication remained NOT_PROBED.',
        'The terminal profile remained check_submitted; CLI confirmation requires fresh READY_FOR_RUNTIME, which was not observed.',
        'No setup journal, turn start or new token usage was observed; this is not a zero-billing assertion.'],
    'uncertainty':['No timing breakdown proves that hashing, discovery cache, process startup or version subprocess caused the76-second pre-observation delay.',
        'Stop before a fresh version publication is consistent with the timeline; exact internal refresh-versus-stop order is not persisted.',
        'The first observation error does not carry a per-error timestamp; stop reservation is a later public effect boundary.'],
    'safety':{'private_database_copied':False,'raw_transcript_auth_or_private_payload_exported':False,
        'provider_or_service_executed':False,'checkpoint_or_reservation_modified':False,
        'sqlite_mode':'ro&immutable=1 after verified physical exit; no WAL/SHM present'},
}
with (Q/'v11-diagnosis-final.json').open('x',encoding='utf-8',newline='\n') as stream:
    json.dump(output,stream,indent=2);stream.write('\n')
print(json.dumps({'diagnosis_sha256':sha(Q/'v11-diagnosis-final.json')}))

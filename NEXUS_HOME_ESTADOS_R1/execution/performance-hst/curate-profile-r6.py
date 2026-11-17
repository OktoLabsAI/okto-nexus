"""Curate completed diagnostics; no imports of application modules or new GET."""
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent


def main():
    raw=HERE/'candidate-r6-100-v2-diagnostics.json'
    data=json.loads(raw.read_text(encoding='utf-8'))
    launch=json.loads((HERE/'profile-r6-launch.json').read_text(encoding='utf-8'))
    owned=launch['owned_command']
    assert owned['success'] and owned['exit_code']==0 and not owned['timed_out'] and not owned['force_used']
    assert not owned['remaining_known_processes'] and not owned['remaining_listeners'] and not launch['pins_drift']
    assert data['productive_drift']==[] and not data['payload_drift'] and data['schema_unchanged']
    assert data['source_seed_unchanged'] and data['source_dataset_unchanged']
    assert all(data[k]['http_status']==200 and data[k]['status']=='ready' for k in ('cprofile','sql_diagnostic','main_transport_diagnostic'))
    out=HERE/'profile-r6-final'
    out.mkdir(exist_ok=False)
    (out/'worker.log').write_bytes((Path(launch['own_driver'])/'profile.log').read_bytes())
    report={'status':'DIAGNOSTIC_COMPLETE_NOT_P95','get_count':3,'source_commit':data['source_commit'],
        'wheel_sha256':data['wheel_sha256'],'payload_files':data['payload_files'],'package_modules':data['package_modules'],
        'transport':data['transport'],'dataset_sha256':data['dataset_sha256'],'seed_db_sha256':data['seed_db_sha256'],
        'guarded_scope':'Own pristine mixed100/1000activities/100000history clone, installed-I-B, controlledclock, no lifespan/provider/native process/TCP.',
        'first_get_ms':{'http':data['cprofile']['http_elapsed_ms'],'service':data['cprofile']['service_ms'],
                        'json_render':data['cprofile']['render_ms'],'outside_service_render':data['cprofile']['transport_routing_auth_outside_service_and_other_ms']},
        'service_top20':data['cprofile']['service_functions'][:20],
        'serialization_top20':data['cprofile']['serialization_functions'][:20],
        'sql_get_ms':{'http':data['sql_diagnostic']['http_elapsed_ms'],'execute':data['sql_diagnostic']['execute_ms'],'fetch':data['sql_diagnostic']['fetch_ms']},
        'sql_top20':[{k:x[k] for k in ('template_sha256','calls','execute_ms','fetch_ms','explain_error')} for x in data['sql_diagnostic']['statements'][:20]],
        'transport_get_ms':data['main_transport_diagnostic']['http_elapsed_ms'],
        'transport_top20':data['main_transport_diagnostic']['functions'][:20],
        'raw_diagnostic':'../'+raw.name,'owned_launch':'../profile-r6-launch.json',
        'cleanup':{'normal_exit':True,'force':False,'timeout':False,'remaining_processes':[],'remaining_listeners':[],
                   'pins_drift':[],'payload_productive_schema_seed_dataset_drift':False},
        'limits':['Each diagnostic GET is separate, not nested profiling, not a p95 sample and not a new SLO PASS.',
                  'cProfile cumulative times and SQL UDF execute/fetch times overlap; do not add them.',
                  'First GET includes cold routing/auth/import initialization. Third GET includes service execution in the main event-loop profile; await/select wall cost is not independent CPU cost.',
                  'SQL plans contain templates only, no bound parameters or expanded SQL; EXPLAIN instrumentation overhead is separate from execute/fetch timers.',
                  'The final10 measurement verdict remains FAIL for all six100-connection cuts. No optimization or threshold change was performed.',
                  owned['observation_limit']]}
    (out/'qualification.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    rows=['# R6 installed diagnostic — not p95','',
          'Three separate persistent-ASGI GETs completed HTTP200/ready on a pristine original mixed100 seed clone. No nested profiler, product change or timing-target waiver. All owned processes exited normally; no remaining listener, force, timeout or immutability drift.','',
          f"First GET: HTTP {report['first_get_ms']['http']:.3f}ms; service {report['first_get_ms']['service']:.3f}ms; render {report['first_get_ms']['json_render']:.3f}ms; outside those scopes {report['first_get_ms']['outside_service_render']:.3f}ms. This last quantity is not all transport or all product.",'',
          f"Second GET: SQL execute {report['sql_get_ms']['execute']:.3f}ms plus fetch {report['sql_get_ms']['fetch']:.3f}ms (UDF/projection work overlaps). Third GET HTTP {report['transport_get_ms']:.3f}ms; its main-loop profile includes service.read itself, so do not call the event-loop total external overhead.",'',
          '| Service function | Calls | Own ms | Cumulative ms |','|---|---:|---:|---:|']
    for x in report['service_top20']:
        rows.append(f"| {Path(x['file']).name}:{x['line']} {x['function']} | {x['calls']} | {x['own_ms']:.3f} | {x['cumulative_ms']:.3f} |")
    rows+=['','| SQL template SHA256 | Calls | Execute ms | Fetch ms |','|---|---:|---:|---:|']
    for x in report['sql_top20']:
        rows.append(f"| {x['template_sha256']} | {x['calls']} | {x['execute_ms']:.3f} | {x['fetch_ms']:.3f} |")
    rows+=['',*report['limits'],'',
           'Primary measured candidates for Root review: combined Work/Results read (~401ms execute/fetch in the separate SQL GET), canonical serialization/fingerprints (12,253 canonical calls;7,264 digests under service cProfile) and full relation/page processing. JSON response rendering itself is small. No claim is made that any isolated change will reach500ms; the raw top100 functions and SQL templates/EXPLAIN are preserved in the diagnostic JSON.', '']
    (out/'report.md').write_text('\n'.join(rows),encoding='utf-8')
    files=list(out.iterdir())+[raw,HERE/'profile-r6-launch.json',HERE/'profile-r6-worker.py',HERE/'profile-r6-launch.py',Path(__file__)]
    manifest={'files':[{'path':p.relative_to(HERE).as_posix(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size} for p in sorted(files)]}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'qualification':str(out/'qualification.json'),'sha256':hashlib.sha256((out/'qualification.json').read_bytes()).hexdigest()}))


if __name__=='__main__':main()

from pathlib import Path
import hashlib
import json

p=Path(__file__).resolve().parent
root=p.parents[3]
sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
write=lambda f,d:f.write_text(json.dumps(d,indent=2)+'\n',encoding='utf8')
final=p/'final-relation'
ready=json.loads((final/'ready.json').read_text())
a=ready['snapshot'];b=json.loads((final/'after-read.json').read_text());c=json.loads((final/'after-seen.json').read_text())
sql_pin=next(v for k,v in ready['source_sha256'].items() if k.replace('\\','/')=='src/okto_nexus/adapters/outbound/sqlite/home.py')
q=dict(status='SCOPED_RESULTS_QUALIFICATION_WITH_READER_FIX',scenarios={
    'T-RESULT-01':'PASS_HISTORICAL_FACT_HTTP_AND_BROWSER_CUT',
    'T-RESULT-02':'PASS_PASSIVE_VERIFYING_BROWSER_CUT',
    'T-RESULT-03':'PARTIAL_MARK_SEEN_ONLY_NEW_REVISION_NOT_RUN',
    'T-RESULT-04':'PASS_NO_BULK_MARK_BROWSER_CUT',
    'T-RESULT-05':'PASS_NOT_TRACKED_UNKNOWN_COUNT_BROWSER_CUT',
    'T-HOME-09':'PASS_OLD_UNSEEN_DEFAULT_AND_RESULTS_BROWSER_CUT'},
    final_tests=dict(passed=6,seconds=17.97,handle='784e57',xml='artifact-final-workspace-six-tests.xml'),
    browser=dict(main='116ba7',completion='8455fc',explicit_verification='31dccc',mark_seen='77ffa3',
        legacy_watermark_null='6355e7',bundle='index-BGONNtiX.js',
        js_sha256='dfef7675dea3918117e0df676e3e6d1ef72dd03dec61086e0d24a1b91f6430c9',
        sql_pin_at_browser=sql_pin,final_workspace_fence_follows_browser=True),
    invariants=dict(selected_tables_unchanged_by_view=a==b,
        tables_changed_only_after_explicit_seen=[k for k in b if b[k]!=c[k]],
        preferences_before_after=[b['attention_preferences']['count'],c['attention_preferences']['count']],
        final_state_equals_explicit_preference_snapshot=c==json.loads((final/'final-db.json').read_text())['snapshot']),
    source_pins_at_final_qualification={str(f):sha(root/f) for f in map(Path,[
        'src/okto_nexus/adapters/outbound/sqlite/home.py','tests/home_evolution/test_home_result_artifact_grouping.py',
        'tests/ui_simplification/browser_result_fixture.py','tests/ui_simplification/browser_result_checks.js'])},
    limits=['Synthetic historical terminal facts do not form complete runtime receipt chains; operation.read500 retained',
        'No provider/native execution or application','No new result revision publication for RESULT03',
        'No artifact page/memory/latency guarantee; existing query budget applies',
        'Final workspace fence has HTTP tests, not a newly repeated browser run'],cleanup='cleanup.json')
write(p/'qualification.json',q)
write(p/'operation-read-limitation.json',dict(handle='9e0cf8',http_status=500,
    error=dict(code='DB_ERROR',stage='operation.read',message='Stored operation receipt history is invalid.',
        possible_effect=False,retry_safe=False,operation_id=None,action=''),
    boundary='Synthetic historical fixture; not provider execution proof'))
write(p/'manifest.json',dict(files={f.relative_to(p).as_posix():sha(f) for f in sorted(p.rglob('*')) if f.is_file() and f.name!='manifest.json'}))
print(json.dumps(dict(files=len(json.loads((p/'manifest.json').read_text())['files']),
    manifest_sha256=sha(p/'manifest.json'),qualification_sha256=sha(p/'qualification.json'),
    home_source_sha256=sha(root/'src/okto_nexus/adapters/outbound/sqlite/home.py'))))

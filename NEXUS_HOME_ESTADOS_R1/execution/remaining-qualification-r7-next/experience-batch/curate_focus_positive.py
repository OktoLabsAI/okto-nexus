"""Curate the unchanged R9 focus predicates and exact own Chrome birth exits."""
from pathlib import Path

HERE=Path(__file__).resolve().parent
source=(HERE/'curate_session_role.py').read_text()
source=source.replace("dest=HERE/'experience-r8-session-role'","dest=HERE/'focus-r9-positive'")
source=source.replace("names=['runtime-ready.json',","names=['chrome-process-capture.json','focus-host-predicate.json','experience-payload.json','runtime-ready.json',")
line=next(line for line in source.splitlines()if line.startswith('    before=json.loads('));source=source.replace(line,"    before={};after={}")
line=next(line for line in source.splitlines()if line.startswith('    qualification=dict('))
replacement="""    captured=json.loads((root/'chrome-process-capture.json').read_text());assert captured['status']=='CAPTURED_ACTUAL_OWN_CHROME'
    captured_alive=[]
    for record in captured['records']:
        try:
            process=psutil.Process(record['pid'])
            if abs(process.create_time()-record['birth'])<.01 and process.exe()==record['exe']:captured_alive.append(record['pid'])
        except psutil.NoSuchProcess:pass
    assert not captured_alive
    assert all(value['status']=='PASS_EXECUTED_SUBSET'for value in results.values())
    assert all(check['pass']for value in results.values()for check in value['checks'])
    qualification=dict(status='PASS_FOCAL_F07_I02_CANONICAL_MOVE_AND_FOCUS',source_commit=package['source_commit'],wheel_sha256=package['wheel_sha256'],results=results,summary=summary,interpretation='The same predicates that failed on R8 passed on R9: current/full A moved to Needs you with unchanged A2 pending request and exact succeeded A1 delivery; the same A2 panel survived; Escape closed it, focus returned to the same canonical A card or stable Home heading, and DOM contained A once in the new column.',scope_limits=['One canonical inert-protocol family, no real provider','No AT speech, native zoom or performance claim','Canonical close outcomes remain separate from physical process exit'],cleanup=cleanup,physical=dict(port=port,listeners=listeners,browser_profile_processes=processes,captured_chrome_births=len(captured['records']),captured_chrome_births_remaining=captured_alive,active_resources=False),payload_after=dict(files=count,mismatches=bad),browser_post_count=0,provider_invocations=0,canonical_close=dict(unknown=final['unknown'],sessions=[dict(session_id=s['session_id'],close_confirmed=s['closed'])for s in final['sessions']],failures={p.name:json.loads(p.read_text())for p in (root/'control').glob('close-failure-*.json')}),fixture_cas_redactions=redactions,cas_fingerprints=privacy.fingerprints(cas),withheld_private_images=withheld,curation=entries,original_root=str(root))"""
source=source.replace(line,replacement)
exec(compile(source,str(HERE/'curate_session_role.py'),'exec'))

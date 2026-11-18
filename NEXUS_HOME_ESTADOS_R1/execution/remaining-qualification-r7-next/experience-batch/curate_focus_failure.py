"""Preserve actual semantic move and failed focus return, with cleanup boundaries."""
from pathlib import Path

HERE=Path(__file__).resolve().parent
source=(HERE/'curate_session_role.py').read_text()
source=source.replace("dest=HERE/'experience-r8-session-role'","dest=HERE/'focus-r8-body-focus-failure'")
source=source.replace("names=['runtime-ready.json',","names=['owned-cli-cleanup.json','focus-host-predicate.json','runtime-ready.json',")
line=next(line for line in source.splitlines()if line.startswith('    before=json.loads('));source=source.replace(line,"    before={};after={}")
line=next(line for line in source.splitlines()if line.startswith('    qualification=dict('))
source=source.replace(line,"""    qualification=dict(status='FAIL_FOCUS_RETURN_BODY_AFTER_CANONICAL_MOVE',source_commit=package['source_commit'],wheel_sha256=package['wheel_sha256'],results=results,summary=summary,interpretation='Actual canonical current/full A in Needs you with unchanged A2 request and exact succeeded A1 delivery was received; the same A2 panel survived. Escape closed the panel and DOM moved A correctly, but focus stayed BODY through the bounded2.5s check. The F07/I02 focus requirement failed. Separate runner artifact collision prevented its automatic CLI close; explicit own-session close exit0 is preserved, without another browser test.',not_asserted=['AT speech','All canonical runtime.close operations settled'],cleanup=cleanup,physical=dict(port=port,listeners=listeners,browser_profile_processes=processes,active_resources=False),payload_after=dict(files=count,mismatches=bad),browser_post_count=0,provider_invocations=0,canonical_close=dict(unknown=final['unknown'],sessions=[dict(session_id=s['session_id'],close_confirmed=s['closed'])for s in final['sessions']],failures={p.name:json.loads(p.read_text())for p in (root/'control').glob('close-failure-*.json')}),fixture_cas_redactions=redactions,cas_fingerprints=privacy.fingerprints(cas),withheld_private_images=withheld,curation=entries,original_root=str(root))""")
exec(compile(source,str(HERE/'curate_session_role.py'),'exec'))

"""Preserve the host step-name collision without claiming the generated JS ran."""
from pathlib import Path

HERE=Path(__file__).resolve().parent
source=(HERE/'curate_session_role.py').read_text()
source=source.replace("dest=HERE/'experience-r8-session-role'","dest=HERE/'focus-r8-step-collision'")
line=next(line for line in source.splitlines()if line.startswith('    before=json.loads('))
source=source.replace(line,"    before={};after={}")
line=next(line for line in source.splitlines()if line.startswith('    qualification=dict('))
source=source.replace(line,"""    qualification=dict(status='INCOMPLETE_RUNNER_STEP_FILENAME_COLLISION',source_commit=package['source_commit'],wheel_sha256=package['wheel_sha256'],results=results,summary=summary,interpretation='initialize succeeded. run(open) attempted to reuse cli-experience-open.txt already reserved by the CLI browser launch, and the overwrite guard raised before any panel-opening JS executed. Generated experience-open.js is an unexecuted artifact. No F07/I02 assertion ran.',canonical_close=dict(unknown=final['unknown'],sessions=[dict(session_id=s['session_id'],close_confirmed=s['closed'])for s in final['sessions']],failures={f.name:json.loads(f.read_text())for f in root.glob('control/close-failure-*.json')}),cleanup=cleanup,physical=dict(port=port,listeners=listeners,browser_profile_processes=processes,active_resources=False),payload_after=dict(files=count,mismatches=bad),browser_post_count=0,provider_invocations=0,fixture_cas_redactions=redactions,cas_fingerprints=privacy.fingerprints(cas),withheld_private_images=withheld,curation=entries,original_root=str(root))""")
exec(compile(source,str(HERE/'curate_session_role.py'),'exec'))

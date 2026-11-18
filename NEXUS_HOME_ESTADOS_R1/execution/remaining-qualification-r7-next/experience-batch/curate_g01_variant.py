"""Reuse containment/payload curation with explicit G01 counterpart assertions."""
from pathlib import Path

HERE=Path(__file__).resolve().parent
source=(HERE/'curate_experience.py').read_text()
source=source.replace("a.tag=='experience-r8-first-oracle'","a.tag=='experience-r8-g01-variant'")
source=source.replace("'control/exp-base.json','control/final.json'","'control/exp-base.json','control/exp-base-after.json','control/exp-history.json','experience-history.js','cli-experience-history.txt','control/final.json'")
old="    assert naming['status']=='PASS_NAMING_PREFLIGHT'and base['status']=='INCOMPLETE'and base['checks']==[]"
new="""    assert naming['status']=='PASS_NAMING_PREFLIGHT'and base['status']=='PASS_EXECUTED_SUBSET'
    history=result(root/'cli-experience-history.txt')
    before=json.loads((root/'control/exp-base.json').read_text());after=json.loads((root/'control/exp-base-after.json').read_text())
    assert before['operations']==after['operations']and before['grant_digest']==after['grant_digest']
    assert history['status']=='INCOMPLETE'and history['posts']==[]and history['errors']==[]"""
assert old in source;source=source.replace(old,new)
line=next(line for line in source.splitlines()if line.startswith('    raw=(root/'))
source=source.replace(line,"    actual_target=next(c['actual']for c in base['checks']if c['id']=='G01-exact-target-not-latest');known=json.loads((root/'control/exp-base.json').read_text())['sessions'][0]['scope']")
line=next(line for line in source.splitlines()if line.startswith('    qualification=dict('))
source=source.replace(line,"""    qualification=dict(status='PARTIAL_G01_G04_POSITIVE_G02_ORACLE_INCOMPLETE',source_commit=package['source_commit'],wheel_sha256=package['wheel_sha256'],naming=naming,base=base,history=history,base_authority_invariants=dict(operations_unchanged=True,grant_digest_unchanged=True),interpretation='G01 exact direct target, entire RuntimeSession.scope and marker passed; G04 honest no-session context passed. G02 canonical preview1/total2/hasMore passed, but UI selector was not observed. Whether the displayed snapshot remained held is unproven without the missing DOM capture; no product defect is established.',observed_target=actual_target,preflight_exact_target_match=True,not_asserted=['G02 no-auto-selection and chooser','G03 meaningful titles and remaining later phases','Cause of missing selector after canonical preview response'],cleanup=cleanup,physical=dict(port=port,browser_profile_processes=processes,listeners=listeners,active_resources=False),payload_after=dict(files=count,mismatches=bad),provider_invocations=0,browser_post_count=0,original_root=str(root))""")
exec(compile(source,str(HERE/'curate_experience.py'),'exec'))

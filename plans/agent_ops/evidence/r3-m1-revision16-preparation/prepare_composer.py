from pathlib import Path
H=Path(__file__).resolve().parent
s=(H.with_name('work-revision15')/'compose_revision15.py').read_text(encoding='utf-8')
replacements=[
 ('revision15 composition','revision16 composition'),("OLD=H.with_name('work-request12-package2')","OLD=H.with_name('work-revision15')"),
 ('m1-next-work-plan-83_ksszr','m1-w16-selected-plan-a0xzgmki'),
 ('7af863dd3176df050ffcdfd9cd44f75adbf4314274e77c2cdf7fdf6f035c040a','1c7a64e3257c8b3ee0020528a1c0bfe4f080c04f94d392d0066b8ca5b473ecea'),
 ('70826adc11d41aba2ed84b56e8b673e0f8153d5a550c1d34ec7abfce515c5c37','05c09e7168f6251523e1d75a4c523792e12967a2ef0474264a8c754fe6eaf0d3'),
 ("companion=plan['basis']['closure'];accounting=plan['basis']['accounting']", "companion=pin(Path('D:/Projetos/Techridy/okto_labs_okto_nexus/plans/agent_ops/evidence/r3-m1-revision15-execution/closure-companion.json'))\naccounting=pin(Path('C:/Users/jpamb/AppData/Local/Temp/m1-v15-normal-interrupt-evdv8vdv/accounting-reconciliation.json'))"),
 ("closure['original_checkpoint_untouched']","closure['original_checkpoint_and_closure_untouched']"),
 ("usage['cumulative_observed_tokens']==295262 and usage['charged_reservations']==12","usage['cumulative_observed_tokens']==341276 and usage['charged_reservations']==13"),
 ('CLOSED_PACKAGE2_WITH_CONTROL_RECEIPT_UNCONFIRMED','CLOSED_REVISION15_WITH_CONTROL_RECEIPT_UNCONFIRMED'),
 ("'final_presence':pin(OLD/'public/final-presence.json')", "'final_presence':pin(OLD/'public/final-presence.json'),\n          'closure':pin(OLD/'public/closure.json'),'physical_exit':pin(OLD/'public/nexus-exit-proof.json'),\n          'cleanup_proof':pin(OLD/'public/cleanup-nexus.json'),'uninstall':pin(OLD/'public/lifecycle-nexus-uninstall-result.json')"),
 ('old_conditional13_selected','old_conditional14_selected'),('old_conditional13_eligible','old_conditional14_eligible'),
 ('opening for request12','opening for request13'),
 ('okto.m1.v15.work-revision15','okto.m1.v16.work-revision16'),
 ('initial_minimum_observed_tokens=295262,initial_cumulative_reservations=12,remaining_tolerance_tokens=404738',
  'initial_minimum_observed_tokens=341276,initial_cumulative_reservations=13,remaining_tolerance_tokens=358724'),
 ('Local useful13/new session then same-session continuation14 after success. Remote15/16 IDs allocated but selectors closed.',
  'Local useful14/new session then same-session continuation15 after success. Remote16/17 IDs allocated but selectors closed.'),
 ("predecessor_session_id='ses_7c8b77c2988e1645a0c9b6aefd6d80bc',predecessor_connection_generation=7",
  "predecessor_session_id='ses_86bf8a7f016fafe06e794ce5f0028611',predecessor_connection_generation=8"),
 ("'poll_seconds':17,'freshness_seconds':18","'poll_seconds':19,'freshness_seconds':20"),
 ("'cadence_seconds':22,'target_start_seconds':.2,'max_observed_requests':7","'cadence_seconds':24,'target_start_seconds':.2,'max_observed_requests':8"),
 ('3f322a5e7874bdca13a6c4d2cd4f6435','000516de38262af8bdf99dee1c5271bc'),
 ("'from':13,'to':16","'from':16,'to':17"),
 ('Request12 target CANCELLED','Request13 target CANCELLED'),('revision15 explicit paths','revision16 explicit paths'),
 ('m1-request12-normal-containment-h4c6sw5t/manifest.json','m1-v15-normal-interrupt-evdv8vdv/manifest.json')]
for a,b in replacements:
    assert a in s,a;s=s.replace(a,b)
s=s.replace("'predecessor_controller_freeze':pin(OLD/'runtime-freeze.json')}","'predecessor_controller_freeze':pin(OLD/'runtime-freeze.json'),\n               'predecessor_closure':plan['basis']['closure'],'native_refusal_diagnosis':plan['basis']['native_refusal_diagnosis']}")
compile(s,str(H/'compose_revision16.py'),'exec');(H/'compose_revision16.py').write_text(s,encoding='utf-8')
print('Composer16 prepared; not executed.')

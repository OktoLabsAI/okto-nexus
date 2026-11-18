"""Static I04 assembly. Never allocates/executes the app or browser."""
import ast
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent;REPO=HERE.parents[3];SOURCE=HERE.parent/'keyboard-app-r9-prepared'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(SOURCE/'run_v4.py')=='165238eb2fee9f0bd0fd64a42c4490dc1067d37245af8c6f5754488670653ec9'
runner=(SOURCE/'run_v4.py').read_text().replace('I01','I04').replace('i01','i04')
runner=runner.replace("HERE/'prepared-keyboard-v4.json'","HERE/'prepared-themes.json'")
runner=runner.replace("EXPERIENCE/'builder.py'","HERE/'reader_builder.py'")
runner=runner.replace("'keyboard-v4.js'","'themes.js'")
runner=runner.replace("window='ROOT_I04_KEYBOARD_APP_OPEN'","window='ROOT_I04_THEME_APP_OPEN'")
runner=runner.replace("        control('exp-start-active');active=", "        control('exp-b-history');history=snapshot('history')\n        control('exp-start-active');active=")
anchor="        write(root/'i04-public-preflight.json',exact)"
assert runner.count(anchor)==1
extra="""        failed=[item for item in active['board']['columns']['results']['items']if item['kind']=='delivery'and(item.get('delivery_semantics')or(item.get('result')or{}).get('delivery_semantics')or{}).get('execution_outcome')=='failed']
        assert len(failed)==1,'Expected exactly the canonical peer FAILED turn delivery'
        exact.update(phase='known',failedId=failed[0]['id'],failedTarget=failed[0]['result']['detail_target'])
"""
runner=runner.replace(anchor,extra+anchor)
old="        body('keyboard-case','themes.js',exact)"
new="""        body('theme-known','themes.js',exact)
        control('theme-facts-fail');fault=snapshot('theme-unknown')
        assert fault['board']['source_status']['operational_sessions']=='unavailable'
        body('theme-unknown','themes.js',dict(exact,phase='unknown'))
        control('theme-facts-restore')"""
assert runner.count(old)==1;runner=runner.replace(old,new)
ast.parse(runner);(HERE/'run.py').write_text(runner)
(HERE/'native100.js').write_text((SOURCE/'native100.js').read_text().replace('I01','I04'))
curator=(SOURCE/'curate.py').read_text().replace('I01','I04').replace('i01','i04')
curator=curator.replace("'keyboard-case.js'","'theme-*.js'")
curator=curator.replace("'keyboard-case'in cases and cases['keyboard-case']['status']=='PASS_I04_EXECUTED_SUBSET'","all(name in cases and cases[name]['status']=='PASS_I04_EXECUTED_SUBSET'for name in ['theme-known','theme-unknown'])")
curator=curator.replace('One desktop1440/native100 keyboard case; native calibration precedes the fixture question','I04 both UI themes, known and read-fault unknown phases; five meanings only')
curator=curator.replace("'control/exp-active.json'","'control/exp-active.json','control/exp-history.json','control/exp-theme-unknown.json','control/exp-theme-restored.json'")
ast.parse(curator);(HERE/'curate.py').write_text(curator)
for name in ['reader_builder.py','prepare.py']:ast.parse((HERE/name).read_text())
manifest=json.loads((SOURCE/'prepared-keyboard-v4.json').read_text())
prefix=SOURCE.relative_to(REPO).as_posix()
manifest['input_pins']={k:v for k,v in manifest['input_pins'].items()if not k.startswith(prefix)}
for name in ['run.py','themes.js','reader_builder.py','native100.js','curate.py','prepare.py','plan.md']:
    p=HERE/name;manifest['input_pins'][p.relative_to(REPO).as_posix()]=sha(p)
manifest['status']='I04_THEMES_PREPARED_NOT_EXECUTED'
manifest['scope']='UI light/dark meaning of Working, Idle, pending question, canonical FAILED turn and read-fault unconfirmed; no color-only assertion'
manifest['antecedent_manifest']=dict(path=(SOURCE/'prepared-keyboard-v4.json').relative_to(REPO).as_posix(),sha256=sha(SOURCE/'prepared-keyboard-v4.json'))
manifest['counterpart_changes']=['Canonical B history/FAILED turn before fresh A question','Same UI Application menu Light/Dark Mode toggles','Only fixture query _rows for operational-session SQL fails; no DTO/status/authority write','Known/unknown snapshots in both themes compared to real semantic IDs and visible AX/text']
(HERE/'prepared-themes.json').write_text(json.dumps(manifest,indent=2)+'\n')
gate=dict(approved=False,approved_by=None,scope='I04_APP_NATIVE_ZOOM',start_nexus=True,allow_fixture_canonical_admissions=True,cut_id='hst-native-zoom-r9-themes-1',deadline_seconds=300,allow_own_containment=True,manifest_sha256=sha(HERE/'prepared-themes.json'))
(HERE/'GATE.template.json').write_text(json.dumps(gate,indent=2)+'\n')
print(json.dumps(dict(status='PREPARED_NOT_EXECUTED',manifest_sha256=sha(HERE/'prepared-themes.json'),files={n:sha(HERE/n)for n in ['run.py','themes.js','reader_builder.py','curate.py']}),indent=2))

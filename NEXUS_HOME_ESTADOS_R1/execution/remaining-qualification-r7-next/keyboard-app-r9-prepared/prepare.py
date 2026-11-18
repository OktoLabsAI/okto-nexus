"""Static derivative only. No application/browser/process allocation."""
import ast
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
SOURCE=HERE.parent/'native-zoom-app-r9-prepared'
REPO=HERE.parents[3]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(SOURCE/'run_v2.py')=='9c0b7015d1fe4b3b71a0c75c0d12a2a8562d26d3667dd50726c74f92bb5f9d33'
text=(SOURCE/'run_v2.py').read_text()
text=text.replace('I05','I01').replace('i05','i01').replace("HERE/'prepared-app-v2.json'","HERE/'prepared-keyboard.json'")
text=text.replace("body('app-bootstrap','app-display-v2.js',bootstrap)","body('app-bootstrap','keyboard.js',bootstrap)")
text=text.replace("        # This is the ONLY application start, after native proof in this same profile.","        body('ui-native100','native100.js',dict(window='ROOT_I01_NATIVE_APP_OPEN'))\n        # Native100 UI calibration precedes app startup and original questions.")
text=text.replace("window='ROOT_I01_NATIVE_APP_OPEN',phase='bootstrap',url=fixture_ready['url'],nativeDpr200=result['observations']['zoomed']['devicePixelRatio']","window='ROOT_I01_KEYBOARD_APP_OPEN',phase='bootstrap',url=fixture_ready['url'],nativeDpr100=result['observations']['baseline']['devicePixelRatio']")
text=text.replace("a=next(item for item in cards", "card_a=next(item for item in cards")
text=text.replace("a['", "card_a['")
text=text.replace("window='ROOT_I01_NATIVE_APP_OPEN',phase='case'","window='ROOT_I01_KEYBOARD_APP_OPEN',phase='case'")
old="""        body('app-200','app-display-v2.js',dict(exact,caseName='native200-css360',requestedWidth=720,expectedDpr=result['observations']['zoomed']['devicePixelRatio']))
        body('ui-native100','native100.js',dict(window='ROOT_I01_NATIVE_APP_OPEN'))
        body('app-100','app-display-v2.js',dict(exact,caseName='native100-css360',requestedWidth=360,expectedDpr=result['observations']['baseline']['devicePixelRatio']))"""
assert text.count(old)==1
text=text.replace(old,"        body('keyboard-case','keyboard.js',exact)")
assert "        a=next(" not in text and "check(a.gate)" in text
ast.parse(text)
(HERE/'run.py').write_text(text)
(HERE/'native100.js').write_text((SOURCE/'native100.js').read_text().replace('I05','I01'))
curate=(SOURCE/'curate_v2.py').read_text().replace('I05','I01').replace('i05','i01')
curate=curate.replace("'app-*.js'","'app-*.js','keyboard-case.js'")
curate=curate.replace("all(name in cases and cases[name]['status']=='PASS_I01_EXECUTED_SUBSET'for name in ['app-200','app-100'])","'keyboard-case'in cases and cases['keyboard-case']['status']=='PASS_I01_EXECUTED_SUBSET'")
curate=curate.replace("Two actual app cases only: native200/requested720/CSS360 and native100/requested360/CSS360","One desktop1440/native100 keyboard case; native calibration precedes the fixture question")
curate=curate.replace("'No human, AT speech or I01 extension'","'No human or AT speech; only the asserted keyboard path'")
ast.parse(curate);(HERE/'curate.py').write_text(curate)
manifest=json.loads((SOURCE/'prepared-app-v2.json').read_text())
manifest['status']='I01_KEYBOARD_PREPARED_NOT_EXECUTED'
manifest['input_pins']={k:v for k,v in manifest['input_pins'].items() if not k.startswith(str(SOURCE.relative_to(REPO)).replace('\\','/'))}
manifest['antecedent_manifest']=dict(path=str((SOURCE/'prepared-app-v2.json').relative_to(REPO)).replace('\\','/'),sha256=sha(SOURCE/'prepared-app-v2.json'))
for name in ['run.py','keyboard.js','native100.js','curate.py','prepare.py','plan.md']:
    path=HERE/name;manifest['input_pins'][path.relative_to(REPO).as_posix()]=sha(path)
manifest['scope']='I01 desktop1440/native100 visible enabled controls, real keyboard path three categories; no decision/POST/AT'
manifest['counterpart_changes']=['Native100 UI before Nexus bootstrap and original question','One keyboard case only','Read-only AX names and real Tab/Enter/Escape with exact scope and return focus','Argparse namespace is not shadowed by card_a']
(HERE/'prepared-keyboard.json').write_text(json.dumps(manifest,indent=2)+'\n')
gate=dict(approved=False,approved_by=None,scope='I01_APP_NATIVE_ZOOM',start_nexus=True,allow_fixture_canonical_admissions=True,cut_id='hst-native-zoom-r9-keyboard-1',deadline_seconds=300,allow_own_containment=True,manifest_sha256=sha(HERE/'prepared-keyboard.json'))
(HERE/'GATE.template.json').write_text(json.dumps(gate,indent=2)+'\n')
print(json.dumps(dict(status='PREPARED_NOT_EXECUTED',manifest_sha256=sha(HERE/'prepared-keyboard.json'),files={n:sha(HERE/n)for n in ['run.py','keyboard.js','curate.py']}),indent=2))

"""Static reader/stack/comment counterpart; original prepared manifest is preserved."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
assert sha(HERE/'prepared-app.json')=='9b9194dcd72da07d7a274b39e52b45981f97ebbfb144c95ee5dd59d03ad7dbb6'
old=json.loads((HERE/'prepared-app.json').read_text());repo=HERE.parents[3]
def original(name):
    path=HERE/name;assert sha(path)==old['input_pins'][str(path.relative_to(repo)).replace('\\','/')];return path.read_text()
assert not any((HERE/name).exists()for name in ['run_v2.py','app-display-v2.js','curate_v2.py'])
runner=original('run.py')
runner=runner.replace('Gated browser-only native zoom proof. Never starts or imports Nexus.','Gated I05 application proof. Nexus starts only after native zoom qualifies.')
runner=runner.replace('Allocation copies fixture source but NEVER starts it. Only this static probe runs.','Allocation only copies fixture source here; Nexus start remains after native proof.')
runner=runner.replace('Normal close/stop FIRST. No retry and no next-stage application branch.','Normal close/stop FIRST. No retry, fallback or additional scenario branch.')
runner=runner.replace("HERE/'prepared-app.json'","HERE/'prepared-app-v2.json'")
runner=runner.replace("'app-display.js'","'app-display-v2.js'")
anchor='    def control(name):\n';assert runner.count(anchor)==1
runner=runner.replace(anchor,'    control_invalid_reads=[0]\n'+anchor)
needle="""            if path.exists()and name in json.loads(path.read_text()).get('done',[]):return
"""
replacement="""            invalid_read=None
            try:
                raw_control=path.read_bytes()
            except FileNotFoundError:
                invalid_read=dict(kind='missing',bytes=None,sha256=None)
            else:
                try:
                    observed=json.loads(raw_control)
                except json.JSONDecodeError:
                    invalid_read=dict(kind='invalid_json',bytes=len(raw_control),sha256=hashlib.sha256(raw_control).hexdigest())
                else:
                    if name in observed.get('done',[]):return
            if invalid_read is not None:
                with(root/'i05-control-invalid-reads.jsonl').open('a',encoding='utf-8')as audit:
                    audit.write(json.dumps(dict(marker=name,ordinal=control_invalid_reads[0]+1,**invalid_read))+'\\n')
                control_invalid_reads[0]+=1
"""
assert runner.count(needle)==1;runner=runner.replace(needle,replacement)
assert runner.count("(root/'control'/name).touch()") == original('run.py').count("(root/'control'/name).touch()") == 1
assert runner.count("control('exp-start-active')") == 1
assert 'end=min(action_deadline,time.monotonic()+35)'in runner
ast.parse(runner);(HERE/'run_v2.py').write_text(runner,encoding='utf-8')
browser=original('app-display.js')
needle="width:r.width,height:r.height};}));";assert browser.count(needle)==1
browser=browser.replace(needle,"width:r.width,height:r.height,bottom:r.bottom};}));")
needle="b.width>0&&b.width<=observations.geometry.innerWidth+1&&(!i||b.y>boxes[i-1].y)";assert browser.count(needle)==1
browser=browser.replace(needle,"b.width>0&&b.width<=observations.geometry.innerWidth+1&&Math.abs(b.x-boxes[0].x)<=1&&(!i||b.y>=boxes[i-1].bottom)")
(HERE/'app-display-v2.js').write_text(browser,encoding='utf-8')
curator=original('curate.py');needle="names=['native-zoom-run.private.json',";assert curator.count(needle)==1
curator=curator.replace(needle,"names=['i05-control-invalid-reads.jsonl','native-zoom-run.private.json',")
ast.parse(curator);(HERE/'curate_v2.py').write_text(curator,encoding='utf-8')
diff=''.join(''.join(difflib.unified_diff(original(a).splitlines(True),(HERE/b).read_text().splitlines(True),fromfile=a,tofile=b))for a,b in [('run.py','run_v2.py'),('app-display.js','app-display-v2.js'),('curate.py','curate_v2.py')])
(HERE/'variant-v2.diff').write_text(diff,encoding='utf-8')
print(json.dumps(dict(status='STATIC_PREPARED_NOT_EXECUTED',files={name:sha(HERE/name)for name in ['run_v2.py','app-display-v2.js','curate_v2.py']},diff_lines=len(diff.splitlines())),indent=2))

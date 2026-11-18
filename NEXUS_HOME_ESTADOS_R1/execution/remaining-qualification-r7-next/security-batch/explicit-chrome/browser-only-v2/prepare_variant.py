"""Static launch-option counterpart only; no runtime/browser invocation."""
import ast
import difflib
import hashlib
import json
from pathlib import Path
import shutil

HERE=Path(__file__).resolve().parent
OLD=HERE.parent/'browser-only'
original=(OLD/'run.py').read_text(encoding='utf-8')
anchor="""    assert json.loads((HERE/'playwright-cli.json').read_text())=={
        'browser':{'launchOptions':{'executablePath':manifest['chrome']}}}"""
assert original.count(anchor)==1
derived=original.replace(anchor,"    assert json.loads((HERE/'playwright-cli.json').read_text())==manifest['browser_config']",1)
ast.parse(derived)
if (HERE/'run.py').exists():
    assert (HERE/'run.py').read_text(encoding='utf-8')==derived
else:
    (HERE/'run.py').write_text(derived,encoding='utf-8')
if (HERE/'curate.py').exists():
    assert (HERE/'curate.py').read_bytes()==(OLD/'curate.py').read_bytes()
else:
    shutil.copyfile(OLD/'curate.py',HERE/'curate.py')
(HERE/'run.diff').write_text(''.join(difflib.unified_diff(original.splitlines(True),derived.splitlines(True),
    fromfile='browser-only/run.py',tofile='browser-only-v2/run.py')),encoding='utf-8')
source=HERE.parents[2]/'experience-batch/browser-launch-ro-r8.json'
evidence=json.loads(source.read_text())
launch=json.loads(json.dumps(evidence['stored_browser_config']['launchOptions']))
assert launch=={'channel':'chrome','headless':True,'chromiumSandbox':True,
    'args':['--disable-blink-features=AutomationControlled']}
launch['executablePath']='C:/Program Files/Google/Chrome/Application/chrome.exe'
config={'browser':{'browserName':evidence['stored_browser_config']['browserName'],'launchOptions':launch}}
assert config['browser']['browserName']=='chromium'
assert 'userDataDir' not in config['browser']
(HERE/'playwright-cli.json').write_text(json.dumps(config,indent=2)+'\n')
print(json.dumps({'status':'STATIC_PREPARED','evidence_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
    'browser_config':config,'own_profile_copied':False,'browser_started':False},indent=2))

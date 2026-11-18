"""Static exact derivation only; never runs the fixture/browser."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
BASE=HERE.parent


def replace(text, before, after):
    assert text.count(before)==1,before
    return text.replace(before,after,1)


original=(BASE/'run.py').read_text(encoding='utf-8')
text=replace(original,'HERE = Path(__file__).resolve().parent',
    'VARIANT = Path(__file__).resolve().parent\nHERE = VARIANT.parent')
text=replace(text,'    before = preflight.check(args.gate)  # Before allocation/process/browser.',
'''    instrument = load('explicit_chrome_validation', VARIANT/'validate.py')
    instrument_before = instrument.check(args.gate)
    before = preflight.check(args.gate)  # Before allocation/process/browser.
    instrument.claim(instrument_before)''')
text=replace(text,"    write(root/'security-guard-before.json', before)",
'''    write(root/'security-guard-before.json', before)
    explicit_config = root/'playwright-cli-explicit.json'
    assert not explicit_config.exists()
    explicit_config.write_bytes((VARIANT/'playwright-cli.json').read_bytes())
    assert hashlib.sha256(explicit_config.read_bytes()).hexdigest()==instrument_before['config_sha256']''')
text=replace(text,"cli('open','open','about:blank','--browser=chrome','--profile='+str(root/'browser-profile'))",
    "cli('open','open','about:blank','--browser=chrome','--profile='+str(root/'browser-profile'),'--config='+str(explicit_config))")
text=replace(text,'        helper_guarded = False','        helper_guarded = False\n        instrument_after = None')
text=replace(text,"            assert before==after, 'Root gate/source/payload guard changed during cut'",
    "            assert before==after, 'Root gate/source/payload guard changed during cut'\n            instrument_after = instrument.after(instrument_before, explicit_config)")
text=replace(text,"            'runtime_helper_guarded':helper_guarded,",
    "            'runtime_helper_guarded':helper_guarded,\n            'instrumentation':{'before':instrument_before,'after':instrument_after},")
ast.parse(text)
destination=HERE/'run.py'
assert not destination.exists()
destination.write_text(text,encoding='utf-8')
(HERE/'run.diff').write_text(''.join(difflib.unified_diff(original.splitlines(True),text.splitlines(True),
    fromfile='base/run.py',tofile='explicit-chrome/run.py')),encoding='utf-8')
binary=Path('C:/Program Files/Google/Chrome/Application/chrome.exe')
assert binary.is_file()
pin=hashlib.sha256(binary.read_bytes()).hexdigest()
assert pin=='5b835c10836045119334d9524e62437110e00e1bd20612c9072a0ae155f94a17'
config={'browser':{'launchOptions':{'executablePath':binary.as_posix()}}}
assert not (HERE/'playwright-cli.json').exists()
(HERE/'playwright-cli.json').write_text(json.dumps(config,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'status':'STATIC_VARIANT_CREATED','run_sha256':hashlib.sha256(destination.read_bytes()).hexdigest(),
    'config_sha256':hashlib.sha256((HERE/'playwright-cli.json').read_bytes()).hexdigest(),
    'browser_sha256':pin,'browser_started':False,'allocated':False}))

"""Static S2/R9 sibling; reuse proven S1 driver, no runtime/allocation."""
import ast
import difflib
import hashlib
import json
from pathlib import Path
import shutil

HERE=Path(__file__).resolve().parent
S1=HERE.parent/'security-r9-batch'
OLD=HERE.parent/'security-batch'
assert hashlib.sha256((S1/'prepared-manifest.json').read_bytes()).hexdigest()=='a4709ef7f680c8fb61e9ac53ba005dfdd5885c0eb12e44cce69ad20ba2a6a43d'


def replace(text,before,after):
    assert text.count(before)==1,before
    return text.replace(before,after,1)


for name in ('fixture_builder.py','security_controls.py','drift.py','assert_captures.py',
             'browser_driver.py','prepare.py'):
    assert not (HERE/name).exists()
    shutil.copyfile(S1/name,HERE/name)
shutil.copyfile(OLD/'s2-reported.js',HERE/'s2-reported.js')
shutil.copyfile(S1/'playwright-cli.json',HERE/'playwright-cli.json')
text=(S1/'preflight.py').read_text()
text=replace(text,"assert gate['case'] == 'S1' and gate['deadline_seconds'] == 180",
    "assert gate['case'] == 'S2' and gate['deadline_seconds'] == 180")
text=text.replace('First increment has no live question','S2 baseline has no live question')
(HERE/'preflight.py').write_text(text)
original=(S1/'run.py').read_text()
text=replace(original,"r'hst-security-r9-s1-[a-z0-9-]{1,80}'", "r'hst-security-r9-s2-[a-z0-9-]{1,80}'")
# No S1 branch can execute: the new preflight accepts only S2. Its native
# templates, authority, table proofs and controls are unchanged.
ast.parse(text)
(HERE/'run.py').write_text(text)
(HERE/'run-s1-s2.diff').write_text(''.join(difflib.unified_diff(original.splitlines(True),text.splitlines(True),
    fromfile='S1/R9/run.py',tofile='S2/R9/run.py')))
original=(S1/'curate.py').read_text()
text=replace(original,"'S1 revocation UI is canonical current control availability, not a stale decision submission or same-name successor',",
    "'S2 baseline has no occupied handoff claim/one-shot slot; H08 active-work clause remains partial',")
(HERE/'curate.py').write_text(text)
for path in HERE.glob('*.py'):
    ast.parse(path.read_text())
assert (HERE/'s2-reported.js').read_text().count('__CONFIG__')==1
print(json.dumps({'status':'STATIC_S2_R9_PREPARED','application_started':False,'browser_started':False}))

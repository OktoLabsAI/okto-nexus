"""Focused pure pin-regression check and existing entry denials only."""
from pathlib import Path
import contextlib
import hashlib
import io
import json
import runpy
import socket
import subprocess
import sys
from unittest.mock import patch

ROOT=Path(__file__).parent
assert Path(sys.prefix)==ROOT/'installation/venv'
sys.path.insert(0,str(ROOT))
sys.argv=[str(ROOT/'test_entry_guards.py')]
runpy.run_path(str(ROOT/'test_entry_guards.py'),run_name='__main__')
import campaign_context as context
import win32cred

proposal=json.loads((ROOT/'m1-codex-campaign-proposal-v9.json').read_text())
python=proposal['package_pins']['python']
pins={x['path']:x['sha256'] for x in proposal['package_pins']['files']}
assert len(pins)==983 and pins[python]==hashlib.sha256(Path(python).read_bytes()).hexdigest()
assert not Path(proposal['paths']['campaign_root']).exists()
# Isolate the per-command pin loop after a hypothetical installation receipt.
# No receipt for the real proposal is created: the synthetic document has a
# different hash/status and an explicitly synthetic quote. All effects denied.
proposal['package_pins']['status']='QUALIFIED_FINAL'
qa=ROOT/'pin-regression-synthetic-only'
qa.mkdir()
document=qa/'synthetic-proposal.json'
document.write_text(json.dumps(proposal),encoding='utf-8')
proposal_sha=hashlib.sha256(document.read_bytes()).hexdigest()
receipt=qa/'synthetic-receipt.json'
receipt.write_text(json.dumps({'status':'USER_APPROVED','proposal_revision':9,
 'proposal_sha256':proposal_sha,'campaign_root':proposal['paths']['campaign_root'],
 'policy':proposal['controller_preparation']['policy'],'ancestry':proposal['controller_preparation']['ancestry'],
 'user_quote':'SYNTHETIC PIN-LOOP TEST ONLY; NOT AUTHORIZATION'}),encoding='utf-8')
receipt_sha=hashlib.sha256(receipt.read_bytes()).hexdigest()
observed=[]
effects={'popen':0,'socket':0,'vault':0,'context_returned':0}
original_sha=context.sha
def simulated_payload_hash(path):
    value=str(path)
    if value in pins:
        observed.append(value)
        # Simulate wheel payloads unchanged but the launcher hash changed.
        return '0'*64 if value==python else pins[value]
    return original_sha(path)
def deny(name):
    def denied(*args,**kwargs):
        effects[name]+=1
        raise AssertionError('Effect forbidden in pure pin regression')
    return denied
out=io.StringIO()
with contextlib.ExitStack() as stack:
    stack.enter_context(patch.object(context,'sha',simulated_payload_hash))
    stack.enter_context(patch.object(context,'Context',deny('context_returned')))
    stack.enter_context(patch.object(subprocess,'Popen',deny('popen')))
    stack.enter_context(patch.object(socket,'socket',deny('socket')))
    for name in ('CredRead','CredWrite','CredDelete','CredEnumerate'):
        stack.enter_context(patch.object(win32cred,name,deny('vault')))
    stack.enter_context(patch.object(sys,'argv',['pin-test','--proposal',str(document),
        '--expected-proposal-sha256',proposal_sha,'--approval-path',str(receipt),'--approval-sha256',receipt_sha]))
    with contextlib.redirect_stdout(out):
        try: context.load()
        except SystemExit as error: assert error.code==2
        else: raise AssertionError('Mutated interpreter pin was accepted')
assert json.loads(out.getvalue())=={'status':'REFUSED_BEFORE_DISPATCH','code':'PRODUCT_PIN_CHANGED'}
assert len(observed)==983 and observed[-1]==python
assert not any(effects.values())
assert not Path(proposal['paths']['campaign_root']).exists()
result={'status':'PASS','focused_cases':1,'entry_denials':12,'pin_entries':983,'product_payloads':982,
 'changed_interpreter_refusal':'PRODUCT_PIN_CHANGED','effects':effects,
 'proposal_sha256':hashlib.sha256((ROOT/'m1-codex-campaign-proposal-v9.json').read_bytes()).hexdigest(),
 'scope':'Pure synthetic pin-loop regression, not installed product integration; 982 prospective payload hashes are simulated, changed interpreter is injected. No actual approval or dispatch.'}
(ROOT/'interpreter-pin-gates.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result))

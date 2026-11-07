"""Entry-only denial checks; never a synthetic approval or mocked campaign."""
from pathlib import Path
from unittest.mock import patch
import contextlib,hashlib,io,json,runpy,socket,subprocess,sys

ROOT=Path(__file__).parent
PROPOSAL=ROOT/'m1-codex-campaign-proposal-v8.json'
counts={'popen':0,'socket':0,'vault':0}
def deny(name):
    def refused(*args,**kwargs):
        counts[name]+=1
        raise AssertionError('Forbidden effect: '+name)
    return refused

def main():
    import win32cred
    proof=[]
    proposal=json.loads(PROPOSAL.read_text())
    campaign=Path(proposal['paths']['campaign_root'])
    assert not campaign.exists()
    for file in ROOT.glob('*.py'):compile(file.read_bytes(),str(file),'exec')
    wrong_receipt=ROOT/'guard-invalid-receipt.json'
    wrong_receipt.write_text('{}',encoding='utf-8')
    proposal_hash=hashlib.sha256(PROPOSAL.read_bytes()).hexdigest()
    with contextlib.ExitStack() as stack:
        stack.enter_context(patch.object(subprocess,'Popen',deny('popen')))
        stack.enter_context(patch.object(socket,'socket',deny('socket')))
        for name in ('CredRead','CredWrite','CredDelete','CredEnumerate'):
            stack.enter_context(patch.object(win32cred,name,deny('vault')))
        for script,selection in [('m1_v8_remote_setup.py',['transfer'])]:
            for case,expected in [('missing','AUTHORIZATION_REQUIRED'),('wrong_receipt','APPROVAL_SCOPE_MISMATCH'),('wrong_proposal','PROPOSAL_HASH_MISMATCH')]:
                args=[str(ROOT/script),'--proposal',str(PROPOSAL),'--expected-proposal-sha256',proposal_hash if case!='wrong_proposal' else '0'*64,*selection]
                if case=='wrong_receipt':
                    args+=['--approval-path',str(wrong_receipt),'--approval-sha256',hashlib.sha256(wrong_receipt.read_bytes()).hexdigest()]
                output=io.StringIO()
                with patch.object(sys,'argv',args),contextlib.redirect_stdout(output):
                    try:runpy.run_path(str(ROOT/script),run_name='__main__')
                    except SystemExit as error:assert error.code==2
                    else:raise AssertionError('Entry did not refuse')
                value=json.loads(output.getvalue())
                assert value=={'status':'REFUSED_BEFORE_DISPATCH','code':expected},value
                assert counts=={'popen':0,'socket':0,'vault':0} and not campaign.exists()
                proof.append({'script':script,'case':case,'refusal':expected,'dispatches':0})
    result={'status':'PASS_ENTRY_GUARDS_ONLY','unique_cases':len(proof),'cases':proof,
        'effects':counts,'campaign_root_remains_absent':not campaign.exists(),
        'static_compile':'PASS','synthetic_approval_created':False,'provider_calls':0,
        'scope':'No tests of approved execution, product integration, setup, services, or native behavior.',
        'inputs':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in ROOT.glob('*.py')}}
    (ROOT/'guard-result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':result['status'],'cases':len(proof),'effects':counts}))

if __name__=='__main__':main()

"""Finite recovery entry; no install or restart selectors."""
from pathlib import Path
import sys,json,argparse
sys.path.insert(0,str(Path(__file__).resolve().parent))
from request_context import require,sha
from transfer_compat_context import TransferContext
import connector_lifecycle_compat as lifecycle
from remote_onboarding import transfer
def main():
    p=argparse.ArgumentParser()
    p.add_argument('--expected-compat-sha256',required=True)
    p.add_argument('--plan',required=True);p.add_argument('--expected-plan-sha256',required=True)
    p.add_argument('action',choices=('select','watch','transfer','stop','cleanup','uninstall'))
    a=p.parse_args()
    require(sha(Path(__file__).parent/'transfer-compat-manifest.json')==a.expected_compat_sha256,'COMPAT_MANIFEST_CHANGED')
    X=TransferContext(a.plan,a.expected_plan_sha256)
    if a.action in ('stop','uninstall'):value=lifecycle.lifecycle(X,a.action)
    elif a.action=='select':value=lifecycle.select(X)
    elif a.action=='watch':value=lifecycle.watch(X)
    elif a.action=='transfer':value=transfer(X) or {'status':'REMOTE_PROFILE_DONE','provider_turns_selected':0}
    else:
        value=lifecycle.cleanup_valid(X);X.save('connector-cleanup.json',value)
    print(json.dumps(value,ensure_ascii=False))
    return 0 if value.get('returncode',0)==0 else 3
if __name__=='__main__':raise SystemExit(main())

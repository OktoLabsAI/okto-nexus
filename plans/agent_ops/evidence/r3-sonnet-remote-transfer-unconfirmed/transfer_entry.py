"""Explicit isolated-Python bootstrap, finite Connector transfer stage."""
from pathlib import Path
import json
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from transfer_context import load
import connector_lifecycle as lifecycle
from remote_onboarding import transfer

def main():
    X,action=load()
    if action in ('install','start','stop','uninstall'):value=lifecycle.lifecycle(X,action)
    elif action=='select':value=lifecycle.select(X)
    elif action=='watch':value=lifecycle.watch(X)
    elif action=='transfer':value=transfer(X) or {'status':'REMOTE_PROFILE_DONE','provider_turns_selected':0}
    else:
        value=lifecycle.cleanup_valid(X);X.save('connector-cleanup.json',value)
    print(json.dumps(value,ensure_ascii=False))
    return 0 if value.get('returncode',0)==0 else 3

if __name__=='__main__':raise SystemExit(main())

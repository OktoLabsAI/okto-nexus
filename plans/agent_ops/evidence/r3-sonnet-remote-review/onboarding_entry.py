"""Explicit isolated-Python bootstrap for the finite no-model stage."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from onboarding_context import load
from remote_onboarding import draft,plan

def main():
    X,action=load()
    (draft if action=='draft' else plan)(X)
    print('{"status":"CANONICAL_ONBOARDING_STAGE_CONFIRMED","provider_calls":0}')
    return 0

if __name__=='__main__':
    raise SystemExit(main())

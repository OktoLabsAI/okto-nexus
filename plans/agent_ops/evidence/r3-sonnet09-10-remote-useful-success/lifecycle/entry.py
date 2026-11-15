from pathlib import Path
import argparse,json,sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from recovery_context import RecoveryContext
from cohort_lifecycle import dispatch

def main():
    p=argparse.ArgumentParser();p.add_argument('--plan',required=True);p.add_argument('--expected-plan-sha256',required=True)
    p.add_argument('component',choices=('nexus','connector'));p.add_argument('action',choices=('prepare','start','select','watch','stop','cleanup'))
    a=p.parse_args();X=RecoveryContext(a.plan,a.expected_plan_sha256)
    result=dispatch(X,a.component,a.action);print(json.dumps(result))
    return 0 if result.get('returncode',0)==0 else 1

if __name__=='__main__':raise SystemExit(main())

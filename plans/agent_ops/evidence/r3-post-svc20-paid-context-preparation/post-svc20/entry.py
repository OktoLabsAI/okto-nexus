from pathlib import Path
import argparse,json,sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from post_context import Context
from post_lifecycle import dispatch

def main():
 p=argparse.ArgumentParser();p.add_argument('--plan',required=True);p.add_argument('--expected-plan-sha256',required=True)
 p.add_argument('action',choices=('start','select','watch','stop','cleanup','uninstall'));a=p.parse_args()
 value=dispatch(Context(a.plan,a.expected_plan_sha256),a.action)
 print(json.dumps(value));return 0
if __name__=='__main__':raise SystemExit(main())

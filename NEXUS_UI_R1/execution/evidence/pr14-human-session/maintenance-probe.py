"""Finite metadata-only canonical liveness read; no browser or mutations."""
import argparse,json,time
from pathlib import Path
from datetime import datetime,timezone
import httpx
p=argparse.ArgumentParser();p.add_argument('--ready',type=Path,required=True);p.add_argument('--report',type=Path,required=True);p.add_argument('--seconds',type=int,default=130);a=p.parse_args()
if not 1<=a.seconds<=140:p.error('1..140 seconds only')
ready=json.loads(a.ready.read_text());started=time.monotonic()
with httpx.Client() as client:
    def snapshot():
        r=client.get(ready['url']+'/api/v1/home/entries?workspace_id=ws&quick=all');d=r.json()['data']
        occurrences=[o for g in d['items'] for e in g['children'] for o in e['attention_preview'] if o['kind']=='native_question_pending']
        return {'at':datetime.now(timezone.utc).isoformat(),'http_status':r.status_code,'questions':[{'kind':o['kind'],'freshness':o['freshness'],'respond_native':'respond_native' in o['allowed_actions']} for o in occurrences]}
    initial=snapshot();print(json.dumps({'initial':initial}),flush=True)
    while time.monotonic()-started<a.seconds:time.sleep(min(2,a.seconds-(time.monotonic()-started)))
    final=snapshot()
result={'status':'PASS' if final['questions'] and all(o['freshness']=='current' and o['respond_native'] for o in final['questions']) else 'FAIL','elapsed_seconds':time.monotonic()-started,'initial':initial,'final':final,'scope':'Canonical question metadata current after >120s; no decision submitted or browser opened. Does not prove beyond original control-ticket expiry.','authority_times':ready['decision_authority_times'],'original_grants':ready['original_grants']}
a.report.write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result),flush=True)

"""Finite read-only log observer; never contacts or focuses the human browser."""
import argparse,json,time
from datetime import datetime,timezone
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--since',type=int,default=0);p.add_argument('--seconds',type=int,default=60);p.add_argument('--actions',type=Path,default=Path('C:/Users/jpamb/AppData/Local/Temp/nexus-ui043-human-control-se2az6t3/actions.json'));a=p.parse_args()
if not 1<=a.seconds<=60:p.error('finite1..60seconds')
path=a.actions;last=a.since;end=time.monotonic()+a.seconds
while time.monotonic()<end:
    try:rows=json.loads(path.read_text(encoding='utf-8'))
    except(json.JSONDecodeError,OSError):time.sleep(1);continue
    clicks=[r for r in rows if r['type']=='ui_action']
    if len(clicks)>last:
        print(json.dumps({'read_at':datetime.now(timezone.utc).isoformat(),'clicks':len(clicks),'new':clicks[last:],'non_get':[r for r in rows if r['type']=='http' and r['method']!='GET']}),flush=True);last=len(clicks)
    time.sleep(min(10,max(0,end-time.monotonic())))
print(json.dumps({'observer_finished':True,'clicks':last,'read_at':datetime.now(timezone.utc).isoformat()}),flush=True)

"""One offline four-work measurement; output is durations/counts only."""
from pathlib import Path
from contextlib import contextmanager
import json,os,sys,time
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'controller'))
os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD']='1'
import pytest
import independent_controller as c
import independent_journal as j

totals={};polls=[]
def add(name,elapsed):
    item=totals.setdefault(name,{'calls':0,'total_ms':0,'max_ms':0})
    item['calls']+=1;item['total_ms']+=elapsed;item['max_ms']=max(item['max_ms'],elapsed)
def wrap(obj,name,label):
    original=getattr(obj,name)
    def measured(*args,**kwargs):
        began=time.perf_counter()
        try:return original(*args,**kwargs)
        finally:add(label,(time.perf_counter()-began)*1000)
    setattr(obj,name,measured)
for obj,name,label in [(c.Controller,'persist','durable_persist'),(j,'safe_path','safe_path_nested'),
                       (j.ReadOnly,'prepare','prepare_including_nested_path'),
                       (j.CanonicalIntentReader,'read','canonical_read'),(j.CoreJournalReader,'read','core_read')]:wrap(obj,name,label)
original_poll=c.Controller.poll
def poll(self):
    before={key:dict(value) for key,value in totals.items()};began=time.perf_counter()
    try:return original_poll(self)
    finally:
        phases={key:{'calls':value['calls']-before.get(key,{}).get('calls',0),
                     'total_ms':value['total_ms']-before.get(key,{}).get('total_ms',0)} for key,value in totals.items()}
        polls.append({'elapsed_ms':(time.perf_counter()-began)*1000,'requests':len(self.data['requests']),
                      'faults':list(self.data['faults']),'phases':phases})
c.Controller.poll=poll
code=pytest.main(['-q','-p','no:cacheprovider',str(ROOT/'controller/test_work_wrapper.py')+'::test_whole_work_wrapper_local_continuation_remote_lost_response_and_continuation',
                  '--basetemp='+str(ROOT/'qualification/profile-tmp'),'--junitxml='+str(ROOT/'qualification/profile.xml')])
out={'exit_code':code,'totals':totals,'polls':polls,'note':'Nested timings overlap; do not sum nested safe_path/prepare into reads. One run, not a tail-latency guarantee.'}
(ROOT/'qualification/phase-profile.json').write_text(json.dumps(out,indent=2),encoding='utf-8')
print(json.dumps({'profile_exit':code,'poll_count':len(polls),'max_poll_ms':max(p['elapsed_ms'] for p in polls),'totals':totals},indent=2))
raise SystemExit(code)

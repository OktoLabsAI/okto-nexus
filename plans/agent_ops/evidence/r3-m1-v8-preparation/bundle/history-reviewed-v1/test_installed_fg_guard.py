"""Three finite installed lifecycle branches; no OS service, CLI or provider."""
from contextlib import ExitStack, nullcontext
from pathlib import Path
from unittest.mock import patch
import hashlib,json,os,socket,subprocess,sys,tempfile
import win32cred
from okto_nexus_connector.daemon import lifecycle,manager
from okto_nexus_connector.errors import ConnectorError
from okto_nexus_connector.platform import user_service

ROOT=Path(__file__).parent
PREFIX=Path('C:/Users/jpamb/AppData/Local/Temp/m1-observation-hosts-ai03jk1l/venv').resolve()
assert Path(sys.prefix).resolve()==PREFIX
sources={Path(lifecycle.__file__):None,Path(user_service.__file__):None}
for path in sources:
    assert path.resolve().is_relative_to(PREFIX)
    sources[path]=hashlib.sha256(path.read_bytes()).hexdigest()

class State:
    def __init__(self,state):self.state=state;self.reason='READY' if state=='ready' else 'STOPPED';self.instance_id='synthetic-instance'
    def to_json(self):return {'state':self.state,'instance_id':self.instance_id,'generation':'synthetic-generation'}

results=[]
for case in ('ready_reuses','scheduler_selected','fallback_refused'):
    fixture=Path(tempfile.mkdtemp(prefix='fg-'+case+'-',dir=ROOT))
    counts={'service_start':0,'spawn':0,'popen':0,'socket':0,'vault':0,'status':0}
    statuses=iter([State('ready'),State('ready')] if case=='ready_reuses' else [State('stopped'),State('ready')])
    def status(*args,**kwargs):counts['status']+=1;return next(statuses)
    def forbidden(name):
        def call(*args,**kwargs):counts[name]+=1;raise AssertionError('Forbidden effect: '+name)
        return call
    class Service:
        def __init__(self,root):assert root==fixture
        def start(self):counts['service_start']+=1;return case=='scheduler_selected'
    with ExitStack() as stack:
        stack.enter_context(patch.dict(os.environ,{'OKTO_NEXUS_CONNECTER_DAEMON_FG':'1'}))
        stack.enter_context(patch.object(lifecycle,'launch_exclusion',lambda root:nullcontext()))
        stack.enter_context(patch.object(lifecycle,'UserService',Service))
        stack.enter_context(patch.object(manager,'status',status))
        stack.enter_context(patch.object(manager,'_spawn',forbidden('spawn')))
        stack.enter_context(patch.object(subprocess,'Popen',forbidden('popen')))
        stack.enter_context(patch.object(socket,'socket',forbidden('socket')))
        for name in ('CredRead','CredWrite','CredDelete','CredEnumerate'):
            stack.enter_context(patch.object(win32cred,name,forbidden('vault')))
        if case=='fallback_refused':
            try:lifecycle.start(fixture,timeout=1)
            except ConnectorError as error:
                assert error.code=='DAEMON_UNAVAILABLE'
                result={'refused':True,'code':error.code}
            else:raise AssertionError('Fallback was not refused')
            assert counts['service_start']==1 and counts['status']==1
        else:
            result=lifecycle.start(fixture,timeout=1)
            assert result['state']=='ready' and result['spawned_pid'] is None
            assert result['started']==(case=='scheduler_selected')
            assert result['already_running']==(case=='ready_reuses')
            assert counts['service_start']==int(case=='scheduler_selected') and counts['status']==2
    assert all(counts[name]==0 for name in ('spawn','popen','socket','vault'))
    assert list(fixture.iterdir())==[]
    results.append({'case':case,'status':'PASS','counts':counts,'result':result})
assert all(hashlib.sha256(path.read_bytes()).hexdigest()==value for path,value in sources.items())
document={'status':'PASS_INSTALLED_SYNTHETIC_BRANCHES','unique_cases':3,'cases':results,
    'inputs_unchanged':True,'source_hashes':{str(k):v for k,v in sources.items()},
    'effects':{'service_actions':0,'native_processes':0,'provider':0,'vault':0},
    'limits':'UserService and status are fakes; proves installed branch behavior under FG=1, not a real Scheduler race or process containment.'}
(ROOT/'installed-fg-guard-result.json').write_text(json.dumps(document,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'status':document['status'],'cases':3,'effects':document['effects']}))

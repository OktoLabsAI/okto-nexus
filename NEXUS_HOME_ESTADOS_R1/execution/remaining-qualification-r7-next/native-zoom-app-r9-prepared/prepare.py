"""Static app-stage derivation. Never imports or runs a product/browser fixture."""
import ast
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
NATIVE=HERE.parent/'native-zoom-batch'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
assert sha(NATIVE/'run_v2.py')=='1a95f07cd6627b71095ce324a51c3a649dd4be8ca10344314d553568416c8c9b'
target=HERE/'run.py';assert not target.exists()
source=(NATIVE/'run_v2.py').read_text()
source=source.replace("HERE=Path(__file__).resolve().parent","HERE=Path(__file__).resolve().parent\nNATIVE=HERE.parent/'native-zoom-batch'\nEXPERIENCE=HERE.parent/'experience-batch'")
source=source.replace("HERE/'prepared-bound-v2.json'","HERE/'prepared-app.json'")
source=source.replace("gate['scope']=='NATIVE_ZOOM_BROWSER_ONLY'and gate['start_nexus']is False","gate['scope']=='I05_APP_NATIVE_ZOOM'and gate['start_nexus']is True")
source=source.replace("assert gate['deadline_seconds']==180 and gate['allow_own_containment']is True","assert gate['deadline_seconds']==300 and gate['allow_own_containment']is True and gate['allow_fixture_canonical_admissions']is True")
source=source.replace('total_deadline=time.monotonic()+180;action_deadline=total_deadline-30','total_deadline=time.monotonic()+300;action_deadline=total_deadline-120')
source=source.replace("'--mode','baseline'","'--mode','scope_two'")
for name in ['probe_server_v2.py','playwright-cli.json','native-settings-guard-v2.js']:
    source=source.replace("HERE/'"+name+"'","NATIVE/'"+name+"'")
old="    opened=False;probe=None;probe_log=None;result=None;failure=None;cleanup_errors=[];port=None;after=None;argv_proof=None"
new=old+"\n    owner=lifecycle.Owned(root);fixture_ready=None;fixture_cleanup=None;app_results=[];app_port=None\n    builder=load('i05_fixture_builder',EXPERIENCE/'builder.py');derivative=builder.build(root,naming_only=False)\n    write(root/'i05-builder-proof.json',derivative)\n    runtime=json.loads((root/'runtime-ready.json').read_text());runtime['fixture_sha256']=sha(root/'fixture.py');(root/'runtime-ready.json').write_text(json.dumps(runtime,indent=2)+'\\n')"
assert source.count(old)==1;source=source.replace(old,new)
needle="    try:\n        opened=True"
helpers="""    def body(name,filename,config):
        path=root/(name+'.js');assert not path.exists()
        text=(HERE/filename).read_text();assert text.count('__CONFIG__')==1
        path.write_text(text.replace('__CONFIG__',json.dumps(config)),encoding='utf-8')
        value=manager.cli_result(cli(name,'run-code','--filename='+str(path)))
        write(root/(name+'-result.private.json'),value);app_results.append(dict(phase=name,result=value))
        assert value['status']in ['PASS_I05_EXECUTED_SUBSET','PASS_NATIVE_UI100_SELECTED'],'I05 case did not qualify: '+name
        return value
    def control(name):
        (root/'control'/name).touch();end=min(action_deadline,time.monotonic()+35)
        while time.monotonic()<end:
            path=root/'control/controls.json'
            if path.exists()and name in json.loads(path.read_text()).get('done',[]):return
            assert owner.process.poll()is None,'Fixture exited during canonical control'
            owner.sample();commands.sample(owner.process.pid);time.sleep(.1)
        raise RuntimeError('Canonical fixture control deadline '+name)
    def snapshot(name):return json.loads((root/'control'/('exp-'+name+'.json')).read_text())
    try:
        opened=True"""
assert source.count(needle)==1;source=source.replace(needle,helpers)
needle="        assert result['status']=='PASS_NATIVE_200_ZOOM_GUARD','Native UI/effect did not qualify; no fallback or Nexus startup'"
stage=needle+"""
        # This is the ONLY application start, after native proof in this same profile.
        owner.start(root/'runtime-ready.json',root/'fixture.py');end=min(action_deadline,time.monotonic()+65)
        while not(root/'control/ready.json').exists():
            assert owner.process.poll()is None and time.monotonic()<end,'Canonical app fixture not ready'
            owner.sample();commands.sample(owner.process.pid);time.sleep(.1)
        fixture_ready=json.loads((root/'control/ready.json').read_text());assert fixture_ready['provider_invocations']==0
        app_port=int(fixture_ready['url'].rsplit(':',1)[1]);origins=json.loads((root/'control/origins.json').read_text())
        prefix=Path(ready['python']).parent.parent
        assert origins['isolated']and Path(origins['prefix']).resolve()==prefix.resolve()
        assert set(origins['origins'])=={'okto_nexus','nexus_connector_core','okto_nexus_connector'}and all(Path(value).resolve().is_relative_to(prefix)for value in origins['origins'].values())
        cli('load-own-cookie','state-load',fixture_ready['storage'])
        bootstrap=dict(window='ROOT_I05_NATIVE_APP_OPEN',phase='bootstrap',url=fixture_ready['url'],nativeDpr200=result['observations']['zoomed']['devicePixelRatio'])
        body('app-bootstrap','app-display.js',bootstrap)
        # Native/browser warmup and app bootstrap precede fresh original120s questions.
        control('exp-start-active');active=snapshot('active');identity=json.loads((root/'control/exp-active-identities.json').read_text());baseline=snapshot('base');refs=fixture_ready['references']
        cards=[item for column in active['board']['columns'].values()for item in column['items']if item['kind']=='harness']
        a=next(item for item in cards if item['connection']['binding_id']==refs[0]['binding_id']);b=next(item for item in cards if item['connection']['binding_id']==refs[1]['binding_id'])
        assert a['operational_status']['activity']=='working'and a['operational_status']['blocking']=='partial'and a['operational_status']['freshness']=='current'
        b_sessions=[item for item in baseline['sessions']if item['scope']['binding_id']==refs[1]['binding_id']];assert len(b_sessions)==1;b1=b_sessions[0]
        a2=next(item for item in active['sessions']if item['scope']['session_id']==identity['a2']['session_id'])
        request=[item for item in a['requests_preview']if item['request']['source_id']==identity['question']['request_id']and item['request']['session_id']==a2['scope']['session_id']];assert len(request)==1;request=request[0]
        turns=[item for item in baseline['operations']if item['intent']=='turn.submit'and item['scope']['session_id']==b1['scope']['session_id']];assert len(turns)==1
        deliveries=[item for item in active['board']['columns']['results']['items']if item['kind']=='delivery'and item['entry']['target'].get('operation_id')==turns[0]['operation_id']];assert len(deliveries)==1;delivery=deliveries[0]
        exact=dict(window='ROOT_I05_NATIVE_APP_OPEN',phase='case',url=fixture_ready['url'],outputPrefix=str(root/'i05-app'),expiresAt=identity['question']['expires_at'],aCard=a['id'],bCard=b['id'],bScope=b1['scope'],bMarker=b1['marker'],a2Scope=a2['scope'],requestCard=request['id'],requestId=identity['question']['request_id'],deliveryId=delivery['id'],deliveryTarget=delivery['result']['detail_target'],projectA=a['connection']['workspace_label'],projectB=b['connection']['workspace_label'])
        write(root/'i05-public-preflight.json',exact)
        body('app-200','app-display.js',dict(exact,caseName='native200-css360',requestedWidth=720,expectedDpr=result['observations']['zoomed']['devicePixelRatio']))
        body('ui-native100','native100.js',dict(window='ROOT_I05_NATIVE_APP_OPEN'))
        body('app-100','app-display.js',dict(exact,caseName='native100-css360',requestedWidth=360,expectedDpr=result['observations']['baseline']['devicePixelRatio']))"""
assert source.count(needle)==1;source=source.replace(needle,stage)
needle="        (root/'control/zoom-probe-stop').touch()"
replace=needle+"\n        if owner.process:(root/'control/stop').touch()"
assert source.count(needle)==1;source=source.replace(needle,replace)
needle="        commands.sample();remaining=commands.remaining();containment=commands.contain()if remaining else dict(forced_births=[],remaining=[])"
replace="""        if owner.process:
            end=min(total_deadline-35,time.monotonic()+90)
            while owner.process.poll()is None and time.monotonic()<end:owner.sample();commands.sample(owner.process.pid);time.sleep(.1)
            fixture_cleanup=owner.stop(force=owner.process.poll()is None)
            if fixture_cleanup.get('signals')or fixture_cleanup.get('remaining_known_births')or fixture_cleanup.get('exit_code')!=0:cleanup_errors.append(dict(stage='fixture containment/settlement',classification='DIAGNOSTIC_FAIL',cleanup=fixture_cleanup))
        commands.sample();remaining=commands.remaining();containment=commands.contain()if remaining else dict(forced_births=[],remaining=[])"""
assert source.count(needle)==1;source=source.replace(needle,replace)
needle="        final=dict(scope='NATIVE_BROWSER_ONLY_NO_NEXUS'"
insert="""        app_listeners=[dict(pid=item.pid,port=item.laddr.port)for item in psutil.net_connections(kind='tcp')if app_port and item.status=='LISTEN'and item.laddr.port==app_port]
        if app_listeners:cleanup_errors.append(dict(stage='application listener remains',listeners=app_listeners))
        fixture_final=json.loads((root/'control/final.json').read_text())if(root/'control/final.json').exists()else None
        if owner.process and fixture_final is None:cleanup_errors.append(dict(stage='fixture final missing',classification='UNKNOWN'))
        final=dict(scope='I05_APP_NATIVE_ZOOM'"""
assert source.count(needle)==1;source=source.replace(needle,insert)
source=source.replace('deadline_seconds=180,nexus_processes_started=0,provider_invocations=0','deadline_seconds=300,nexus_processes_started=int(owner.process is not None),provider_invocations=fixture_final.get(\'provider_invocations\')if fixture_final else(0 if owner.process is None else None),app_results=app_results,app_listeners=app_listeners,fixture_cleanup=fixture_cleanup,fixture_final=fixture_final')
source=source.replace('nexus_started=False)),flush=True)','nexus_started=owner.process is not None)),flush=True)')
ast.parse(source);target.write_text(source,encoding='utf-8')
print(json.dumps(dict(status='STATIC_APP_RUNNER_WRITTEN_NOT_EXECUTED',sha256=sha(target))))

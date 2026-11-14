"""Rebase only package/path pins; preserve qualified runner logic exactly."""
from pathlib import Path
import hashlib,json,sys
ROOT=Path(__file__).resolve().parent
OLD=Path('C:/Users/jpamb/AppData/Local/Temp/r3-svc-t15-final-ov2tinp_')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(path,value):
    with path.open('x',encoding='utf-8',newline='\n') as out:json.dump(value,out,indent=2);out.write('\n')
assert sha(OLD/'plan.json')=='28487c117a531945c68f1877925ed1d2a1b417de1ec17629a6d4fd201fef3d0f'
assert sha(OLD/'qualification.json')=='3dd2552ccfc3995c7c4ceaef9d647dd287b22e68aa88c9d758d01eb75d8fbe43'
assert sha(OLD/'public-allowlist.json')=='ea0a7c1c6e5511f65384e57aa4fd6d99d33f74c72b6ddec1d94a48606e6228a7'
assert sys.flags.isolated and Path(sys.prefix).resolve()==(ROOT/'venv').resolve()
assert all(not (base/name).exists() for base in (ROOT,OLD) for name in ('case','public','private'))
copied=json.loads((ROOT/'copied-source-pins.json').read_bytes())
for name,digest in copied['files'].items():assert sha(ROOT/name)==sha(OLD/name)==digest
old=json.loads((OLD/'plan.json').read_bytes())
old_allow={item['path']:item['sha256'] for item in json.loads((OLD/'public-allowlist.json').read_bytes())['files']}
assert sha(OLD/'offline-reviewed.xml')==old_allow['offline-reviewed.xml']
for name in ('run_case.py','connection_case.py','cohort.py','runtime_support.py'):
    assert sha(ROOT/name)==old['pins'][name]['sha256']
def rebase(value):
    if isinstance(value,str):return value.replace(str(OLD),str(ROOT))
    if isinstance(value,list):return [rebase(item) for item in value]
    if isinstance(value,dict):return {rebase(key):rebase(item) for key,item in value.items()}
    return value
plan=rebase(old)
sys.path.insert(0,str(ROOT))
from okto_nexus.adapters.outbound.service_manager.identity import server_instance_id
import okto_nexus,okto_nexus_connector,nexus_connector_core
for module in (okto_nexus,okto_nexus_connector,nexus_connector_core):
    assert Path(module.__file__).resolve().is_relative_to(ROOT/'venv/Lib/site-packages')
home=Path(plan['homes']['nexus']);identity=server_instance_id(home,home/'nexus.db')
plan['instance_ids']={'nexus':identity};plan['tasks']={'nexus':'OktoNexus-server-'+identity.removeprefix('svc_')}
inputs=json.loads((ROOT/'wheel-inputs.json').read_bytes())
for key,pin in plan['pins'].items():
    digest=sha(pin['path'])
    if key.endswith('_wheel'):
        assert digest==inputs[key.removesuffix('_wheel')]['sha256']
    elif key!='installation.json':
        assert digest==old['pins'][key]['sha256']
    pin['sha256']=digest
for path,digest in plan['python_images'].items():assert sha(path)==digest
plan['scope']['products']='Package2 immutable Nexus2f626483/Connector645d7bd bounded streaming inspector; Core7810f3 wheel d881 unchanged. Own venv, no working-tree imports.'
plan['package2_ancestry']={'original_plan':{'path':str(OLD/'plan.json'),'sha256':sha(OLD/'plan.json')},
    'original_qualification':{'path':str(OLD/'qualification.json'),'sha256':sha(OLD/'qualification.json')},
    'original_33_tests':{'path':str(OLD/'offline-reviewed.xml'),'sha256':sha(OLD/'offline-reviewed.xml'),
        'rerun':False,'basis':'Runner/connection/cohort/support bytes unchanged; package2 source streaming separately qualified.'},
    'original_never_executed':True,'variant_never_executed':True}
# Concrete argv must differ only by the owned root paths.
assert plan['commands']==rebase(old['commands'])
assert plan['port']==old['port']==59107 and plan['model_turn_limit']==old['model_turn_limit']==0
assert plan['connection_plan_arguments']==rebase(old['connection_plan_arguments'])
for step in plan['commands']['nexus'].values():
    assert step['argv'][:5]==[plan['python'],'-I','-B','-X','utf8'] and '--force' not in step['argv']
save(ROOT/'plan.json',plan)
import run_case
proof=run_case.verify(plan)
assert proof['wheel_equal_payloads']==988
save(ROOT/'qualification.json',{'status':'OFFLINE_PACKAGE2_DELTA_QUALIFIED_NOT_EXECUTED',
    'plan_sha256':sha(ROOT/'plan.json'),'source_bytes_unchanged':copied['files'],
    'baseline':plan['package2_ancestry'],'installed':proof,'installation_sha256':sha(ROOT/'installation.json'),
    'module_origins':{m.__name__:m.__file__ for m in (okto_nexus,okto_nexus_connector,nexus_connector_core)},
    'checks':['988newwheel payload equality','All3imports under own new prefix','Concreteargv oldroot->newroot only',
        '4runtime source files identical','Original proposal/case untouched and never executed',
        'New scope/task/instance from new home; port59107 unchanged','Pinned native path/hash unchanged'],
    'source_tests_rerun':False,'product_cli_calls':0,'service_calls':0,'provider_calls':0,'model_turns':0})
save(ROOT/'review-command.json',{'status':'ROOT_REVIEW_REQUIRED_BEFORE_EXECUTION','argv':[plan['python'],'-I','-B','-X','utf8',
    str(ROOT/'run_case.py'),'execute','--expected-plan-sha256',sha(ROOT/'plan.json')],
    'cwd':str(ROOT),'environment':json.loads((ROOT/'environment.json').read_bytes()),'plan_sha256':sha(ROOT/'plan.json'),
    'port':59107,'task_name':plan['tasks']['nexus']})
names=['run_case.py','connection_case.py','cohort.py','runtime_support.py','plan.json','qualification.json',
    'review-command.json','copied-source-pins.json','wheel-inputs.json','installation.json','prepare_dependencies.py',
    'install_products.py','prepare_variant.py','dependency-preparation.json']
save(ROOT/'public-allowlist.json',{'source_root':str(ROOT),'files':[{'path':n,'sha256':sha(ROOT/n),'bytes':(ROOT/n).stat().st_size} for n in names]})
print(json.dumps({'plan_sha256':sha(ROOT/'plan.json'),'qualification_sha256':sha(ROOT/'qualification.json'),
    'allowlist_sha256':sha(ROOT/'public-allowlist.json'),'task_name':plan['tasks']['nexus']}))

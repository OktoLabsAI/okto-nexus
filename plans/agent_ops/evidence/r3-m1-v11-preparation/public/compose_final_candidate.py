"""Copy the selected already-v11 frozen candidate byte-for-byte, preserving the prior stage."""
from pathlib import Path
import ast,hashlib,json,sys
R=Path(__file__).resolve().parent;D=R/'draft';S=Path(sys.argv[1]).resolve();F=Path(sys.argv[2]).resolve();expected=sys.argv[3]
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
read=lambda p:json.loads(Path(p).read_bytes())
def write(p,v):p.write_bytes((json.dumps(v,indent=2,ensure_ascii=False)+'\n').encode())
assert sha(F)==expected and not (R/'campaign').exists()
freeze=read(F);p=read(D/'m1-codex-campaign-proposal-v11.json')
history=D/'preparation-history/pre-final-cli-reader';assert not history.exists();history.mkdir()
(history/'proposal.json').write_bytes((D/'m1-codex-campaign-proposal-v11.json').read_bytes())
records=[]
for item in freeze['runtime']+freeze['tests']:
    rel=Path(item['path']);assert not rel.is_absolute() and '..' not in rel.parts
    assert rel.parts[0]=='controller' or rel.name in ('m1_v11_work.py','publication.py','response_loss.py')
    source=S/rel;target=D/rel;assert sha(source)==item['sha256']
    if target.exists():
        saved=history/rel;saved.parent.mkdir(parents=True,exist_ok=True);saved.write_bytes(target.read_bytes())
    target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(source.read_bytes());assert sha(target)==item['sha256']
    records.append({'path':rel.as_posix(),'source':str(source),'source_sha256':item['sha256'],'target_sha256':sha(target),'change':'byte-identical'})
    if rel.parts[0]=='controller' and not rel.name.startswith('test_') and rel.name!='canonical_fixture.py':
        p['execution_bundle']['files']['controller_'+rel.stem]={'path':str(target),'sha256':sha(target)}
    elif rel.name in ('m1_v11_work.py','publication.py','response_loss.py'):
        key='work' if rel.name=='m1_v11_work.py' else rel.stem
        p['execution_bundle']['files'][key]={'path':str(target),'sha256':sha(target)}
for name in ('controller.py','legacy_controller.py'):
    values={node.targets[0].id:ast.literal_eval(node.value) for node in ast.parse((D/'controller'/name).read_text()).body
        if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name) and node.targets[0].id in ('POLICY','ANCESTRY')}
    assert values=={'POLICY':p['controller_preparation']['policy'],'ANCESTRY':p['controller_preparation']['ancestry']}
cls=next(node for node in ast.parse((D/'controller/independent_journal.py').read_text()).body if isinstance(node,ast.ClassDef) and node.name=='ReadOnly')
init=next(node for node in cls.body if isinstance(node,ast.FunctionDef) and node.name=='__init__')
defaults=dict(zip((a.arg for a in init.args.kwonlyargs),init.args.kw_defaults))
assert ast.literal_eval(defaults['sql_budget'])==.25 and ast.literal_eval(defaults['initialization_budget'])==.25
p['controller_preparation'].update(controller_sha256=sha(D/'controller/controller.py'),collector_sha256=sha(D/'controller/token_collector.py'),
    observer_sha256=sha(D/'controller/independent_controller.py'),source_freeze={'path':str(F),'sha256':expected,'classification':freeze['classification']})
p['execution_bundle']['status']='FINAL_CLI_READER_COMPOSED_PENDING_ORIGIN_AND_ENTRY_VERIFICATION'
p['execution_authorized']=False
write(D/'m1-codex-campaign-proposal-v11.json',p)
write(D/'final-cli-reader-source-freeze.json',freeze)
write(D/'final-cli-reader-composition-map.json',{'records':records,'source_freeze_sha256':expected,'rebased_again':False})
print(json.dumps({'status':'BYTE_EXACT_V11_COMPOSED','runtime_pins':len(p['execution_bundle']['files']),'source_freeze_sha256':expected}))

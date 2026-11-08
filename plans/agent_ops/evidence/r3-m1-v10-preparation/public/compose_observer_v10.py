"""Copy the frozen observer candidate and rebase only the successor contract."""
from pathlib import Path
import ast,difflib,hashlib,json

ROOT=Path(__file__).resolve().parent;D=ROOT/'draft';T=D/'controller'
SOURCE=Path(r'C:/Users/jpamb/AppData/Local/Temp/m1-observation-review-zouioqck/integration-v2')
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
load=lambda p:json.loads(Path(p).read_bytes())
def text(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as f:f.write(value.encode())
def write(path,value):text(path,json.dumps(value,ensure_ascii=False,indent=2)+'\n')
def constants(source,policy,ancestry):
    lines=source.splitlines(True);found=set()
    for node in reversed(ast.parse(source).body):
        if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name):
            name=node.targets[0].id
            if name in ('POLICY','ANCESTRY'):
                lines[node.lineno-1:node.end_lineno]=[name+' = '+repr(policy if name=='POLICY' else ancestry)+'\n'];found.add(name)
    assert found=={'POLICY','ANCESTRY'}
    return ''.join(lines)

assert not T.exists()
assert sha(SOURCE/'qualification.json')=='22809a3d5027c395f08a5111feb0118a8808cb9db5508480e44cd916593299f4'
q=load(SOURCE/'qualification.json');p=load(D/'m1-codex-campaign-proposal-v10.json')
policy=p['controller_preparation']['policy'];ancestry=p['controller_preparation']['ancestry']
records={}
for name,digest in q['runtime_files'].items():
    assert sha(SOURCE/name)==digest
    original=(SOURCE/name).read_text(encoding='utf-8');changed=original
    target=T/name
    if name in ('controller.py','legacy_controller.py'):
        changed=constants(changed,policy,ancestry)
    if name=='legacy_controller.py':
        for old,new in [("'format':9","'format':10"),("self.data['format'] != 9","self.data['format'] != 10"),
                        ("receipt.get('proposal_revision') == 9","receipt.get('proposal_revision') == 10"),
                        ('V9_APPROVAL_REQUIRED','V10_APPROVAL_REQUIRED')]:
            assert old in changed;changed=changed.replace(old,new)
    if name=='m1_work_serial_candidate.py':
        target=D/'m1_v10_work.py'
        changed=changed.replace('m1v9-','m1v10-').replace("'m1-v9'","'m1-v10'")
    text(target,changed)
    records[str(target.relative_to(D))]={'source':str(SOURCE/name),'source_sha256':digest,
        'sha256':sha(target),'change':'byte-identical' if original==changed else 'explicit v10 policy/ancestry/revision/intent labels only'}
    if original!=changed:text(D/'diffs'/(target.name+'.observer.diff'),''.join(difflib.unified_diff(original.splitlines(True),changed.splitlines(True),fromfile='observer-v9/'+name,tofile='bundle-v10/'+target.name)))
for name in ('canonical_fixture.py','test_independent.py','test_work_wrapper.py'):
    assert sha(SOURCE/name)==q['support_files'][name]
    original=(SOURCE/name).read_text(encoding='utf-8');changed=original
    if name=='test_independent.py':
        changed=changed.replace("'proposal_revision':9","'proposal_revision':POLICY['revision']")
        changed=changed.replace("writer.complete('one',150000)","observed=(POLICY['preventive_cumulative_tokens']-POLICY['carry_in_tokens'])//2\n        writer.complete('one',observed)")
        changed=changed.replace("summary['known_observed_tokens']==195843","summary['known_observed_tokens']==POLICY['carry_in_tokens']+observed")
        for old,new in [('154157',"(POLICY['preventive_cumulative_tokens']-POLICY['carry_in_tokens'])"),
                        ('45943',"(POLICY['carry_in_tokens']+100)"),('45933',"(POLICY['carry_in_tokens']+90)"),
                        ('45868',"(POLICY['carry_in_tokens']+25)"),('45843',"POLICY['carry_in_tokens']"),
                        ("summary['reserved_requests']==9","summary['reserved_requests']==POLICY['max_cumulative_admissions']")]:
            assert old in changed;changed=changed.replace(old,new)
    elif name=='test_work_wrapper.py':
        changed=changed.replace('from controller import Controller','from controller import Controller,POLICY')
        changed=changed.replace('m1v9-','m1v10-').replace('45843',"POLICY['carry_in_tokens']")
        changed=changed.replace('45853',"(POLICY['carry_in_tokens']+10)")
        changed=changed.replace("Path(__file__).parent/'m1_work_serial_candidate.py'","Path(__file__).parent.parent/'m1_v10_work.py'")
        # Helpers stay beside the runtime wrapper; all are pinned in the bundle.
        changed=changed.replace("self.modules/'response_loss.py'","self.modules.parent/'response_loss.py'")
        changed=changed.replace("Path(__file__).parent/'response_loss.py'","Path(__file__).parent.parent/'response_loss.py'")
    text(T/name,changed)
    records[str((T/name).relative_to(D))]={'source':str(SOURCE/name),'source_sha256':q['support_files'][name],
        'sha256':sha(T/name),'change':'tests parameterized by actual v10 POLICY; own wrapper path only' if original!=changed else 'byte-identical fixture'}
    if original!=changed:text(D/'diffs'/(name+'.observer.diff'),''.join(difflib.unified_diff(original.splitlines(True),changed.splitlines(True),fromfile='observer-v9/'+name,tofile='bundle-v10/'+name)))
for n in ('response_loss.py','publication.py'):
    assert sha(D/n)==q['support_files'][n]
# Do not import or copy rejected alternate observers/builders.
p['controller_preparation'].update(status='V10_REBASE_PENDING_QUALIFICATION',public_directory=str(T),
    controller_sha256=sha(T/'controller.py'),collector_sha256=sha(T/'token_collector.py'),
    observer_sha256=sha(T/'independent_controller.py'),source_qualification=str(SOURCE/'qualification.json'),
    source_qualification_sha256=sha(SOURCE/'qualification.json'))
p['execution_bundle']['files']['work']={'path':str(D/'m1_v10_work.py'),'sha256':sha(D/'m1_v10_work.py')}
for file in sorted(T.glob('*.py')):
    if file.name.startswith('test_') or file.name=='canonical_fixture.py':continue
    p['execution_bundle']['files']['controller_'+file.stem]={'path':str(file),'sha256':sha(file)}
p['execution_bundle']['files']['remote_transfer_monitor']={'path':str(D/'remote_transfer_monitor.py'),'sha256':sha(D/'remote_transfer_monitor.py')}
p['execution_bundle']['files']['remote_setup']['sha256']=sha(D/'m1_v10_remote_setup.py')
p['controller_preparation']['qualification_status']='PENDING_V10_TESTS_AND_ROOT_REVIEW'
p['execution_authorized']=False
(D/'m1-codex-campaign-proposal-v10.json').write_bytes((json.dumps(p,ensure_ascii=False,indent=2)+'\n').encode())
write(D/'observer-rebase-map.json',records)
write(D/'observer-candidate-qualification.json',q)
for path in T.glob('*.py'):compile(path.read_bytes(),str(path),'exec')
compile((D/'m1_v10_work.py').read_bytes(),str(D/'m1_v10_work.py'),'exec')
print(json.dumps({'status':'CANDIDATE_REBASED_PENDING_QUALIFICATION','runtime_modules':len(q['runtime_files']),
    'total_module_pins':len(p['execution_bundle']['files']),'policy':policy,'controller_sha256':sha(T/'controller.py')}))

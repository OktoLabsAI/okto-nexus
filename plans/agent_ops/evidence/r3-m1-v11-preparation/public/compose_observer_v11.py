"""Compose only an explicitly selected frozen offline candidate, never a campaign."""
from pathlib import Path
import ast,difflib,hashlib,json,sys
R=Path(__file__).resolve().parent;D=R/'draft';T=D/'controller'
SOURCE=Path(sys.argv[1]).resolve();FREEZE=Path(sys.argv[2]).resolve();EXPECTED=sys.argv[3]
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
read=lambda p:json.loads(Path(p).read_bytes())
def text(p,s):
    p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('xb') as f:f.write(s.encode())
def write(p,v):text(p,json.dumps(v,indent=2,ensure_ascii=False)+'\n')
def constants(source,policy,ancestry):
    lines=source.splitlines(True);found=set()
    for node in reversed(ast.parse(source).body):
        if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name):
            name=node.targets[0].id
            if name in ('POLICY','ANCESTRY'):
                lines[node.lineno-1:node.end_lineno]=[name+' = '+repr(policy if name=='POLICY' else ancestry)+'\n'];found.add(name)
    assert found=={'POLICY','ANCESTRY'}
    return ''.join(lines)
assert not T.exists() and not (R/'campaign').exists()
assert sha(FREEZE)==EXPECTED
frozen=read(FREEZE);p=read(D/'m1-codex-campaign-proposal-v11.json')
policy=p['controller_preparation']['policy'];ancestry=p['controller_preparation']['ancestry']
assert policy['max_new_admissions']==5 and policy['carry_in_admissions']==6
history=D/'preparation-history';history.mkdir(exist_ok=True)
with (history/'pre-observer-proposal.json').open('xb') as f:f.write((D/'m1-codex-campaign-proposal-v11.json').read_bytes())
records={}
for item in frozen['runtime']+frozen['tests']:
    source=SOURCE/item['path'];assert source.is_relative_to(SOURCE) and sha(source)==item['sha256']
    original=source.read_text();changed=original
    name=source.name;target=D/item['path']
    if name in ('controller.py','legacy_controller.py'):changed=constants(changed,policy,ancestry)
    if name=='legacy_controller.py':
        for old,new in [("'format':10","'format':11"),("self.data['format'] != 10","self.data['format'] != 11"),
            ("receipt.get('proposal_revision') == 10","receipt.get('proposal_revision') == 11"),('V10_APPROVAL_REQUIRED','V11_APPROVAL_REQUIRED'),
            ("len(self.data['requests']) > 6","len(self.data['requests']) > POLICY['max_new_admissions']"),
            ("len(self.data['requests']) >= 6","len(self.data['requests']) >= POLICY['max_new_admissions']")]:
            assert old in changed,(name,old);changed=changed.replace(old,new)
    if name=='token_collector.py':
        for old,new in [("'max_requests': 6","'max_requests': 5"),("state.get('max_requests') == 6","state.get('max_requests') == 5")]:
            assert changed.count(old)==1;changed=changed.replace(old,new)
    if name=='m1_v10_work.py':target=D/'m1_v11_work.py'
    if name in ('m1_v10_work.py','test_work_wrapper.py'):
        changed=changed.replace('m1v10-','m1v11-').replace('m1_v10_work.py','m1_v11_work.py').replace("'m1-v10'","'m1-v11'")
    if target.exists():
        # Only already-copied shared wrappers may exist; preserve original first.
        assert name in ('publication.py','response_loss.py')
        with (history/(name+'.before-observer')).open('xb') as f:f.write(target.read_bytes())
        target.write_bytes(changed.encode())
    else:text(target,changed)
    records[str(target.relative_to(D))]={'source':str(source),'source_sha256':sha(source),'sha256':sha(target),
        'change':'byte-identical' if original==changed else 'explicit v11 policy/ancestry/revision, request labels and allocation5 rebasing only'}
    if original!=changed:text(D/'diffs'/(target.name+'.observer.diff'),''.join(difflib.unified_diff(original.splitlines(True),changed.splitlines(True),fromfile='frozen-source/'+item['path'],tofile='v11/'+str(target.relative_to(D)))))
text(T/'test_v11_allocation.py',(R/'test_v11_allocation_pending.py').read_text())
p['execution_bundle']['files']['work']={'path':str(D/'m1_v11_work.py'),'sha256':sha(D/'m1_v11_work.py')}
for file in sorted(T.glob('*.py')):
    if file.name.startswith('test_') or file.name=='canonical_fixture.py':continue
    p['execution_bundle']['files']['controller_'+file.stem]={'path':str(file),'sha256':sha(file)}
for key in ('publication','response_loss'):
    p['execution_bundle']['files'][key]={'path':str(D/(key+'.py')),'sha256':sha(D/(key+'.py'))}
p['controller_preparation'].update(status='V11_REBASE_PENDING_QUALIFICATION',controller_sha256=sha(T/'controller.py'),
    collector_sha256=sha(T/'token_collector.py'),observer_sha256=sha(T/'independent_controller.py'),
    source_freeze={'path':str(FREEZE),'sha256':EXPECTED,'classification':frozen['classification']})
p['execution_authorized']=False
(D/'m1-codex-campaign-proposal-v11.json').write_bytes((json.dumps(p,indent=2,ensure_ascii=False)+'\n').encode())
write(D/'observer-rebase-map.json',records)
write(D/'observer-source-freeze.json',frozen)
for path in T.glob('*.py'):compile(path.read_bytes(),str(path),'exec')
print(json.dumps({'status':'V11_COMPOSED_PENDING_ACTUAL_TESTS','source':str(SOURCE),'source_freeze_sha256':EXPECTED,'runtime_pins':len(p['execution_bundle']['files'])}))

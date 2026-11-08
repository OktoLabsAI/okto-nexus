"""Rebase finite v9 entrypoints into a new v10 preparation; never execute them."""
from pathlib import Path
import ast
import copy
import difflib
import hashlib
import importlib.util
import json
import zipfile

ROOT = Path(__file__).resolve().parent
D = ROOT / 'draft'
OLD = Path(r'C:/Users/jpamb/AppData/Local/Temp/m1-v9-preparation-t4xaqhca/draft')
WHEEL = Path(r'C:/Users/jpamb/AppData/Local/Temp/m1-recovery-diagnostics-installed-xtfm5o4x/wheels/okto_nexus-0.3.3-py3-none-any.whl')
WHEEL_SHA = '07b7ed53c0fcd9b1c77099a8af52d6d5404d10aca988abaee15a7f51ca132ae4'


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def load(path): return json.loads(Path(path).read_bytes())
def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as f:
        f.write((json.dumps(value, ensure_ascii=False, indent=2)+'\n').encode('utf-8'))
def text(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as f:f.write(value.encode('utf-8'))


def assign(source, values):
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    found = set()
    for node in reversed(tree.body):
        if isinstance(node, ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0], ast.Name):
            name=node.targets[0].id
            if name in values:
                lines[node.lineno-1:node.end_lineno]=[name+' = '+values[name]+'\n']
                found.add(name)
    assert found==set(values), (found,set(values))
    return ''.join(lines)


def main():
    p=load(D/'m1-codex-campaign-proposal-v10-draft.json')
    previous=load(OLD/'m1-codex-campaign-proposal-v9-lf.json')
    assert not (D/'campaign_context.py').exists() and not (D/'installation').exists()
    assert not (ROOT/'campaign').exists()
    policy=p['controller_preparation']['policy']; ancestry=p['controller_preparation']['ancestry']
    sources={}
    for oldname,newname in [('campaign_context.py','campaign_context.py'),
                            ('m1_v9_lifecycle.py','m1_v10_lifecycle.py'),
                            ('m1_v9_setup.py','m1_v10_setup.py'),
                            ('m1_v9_remote_setup.py','m1_v10_remote_setup.py')]:
        original=(OLD/oldname).read_text(encoding='utf-8')
        changed=original.replace('m1_v9_','m1_v10_').replace('m1v9-','m1v10-')
        if newname=='campaign_context.py':
            changed=changed.replace("get('revision')==9","get('revision')==10")
            changed=changed.replace("get('proposal_revision')==9","get('proposal_revision')==10")
        text(D/newname,changed)
        sources[newname]={'source':str(OLD/oldname),'source_sha256':sha(OLD/oldname),'sha256':sha(D/newname),
                          'change':'revision/intent/module labels only; approval, authority and dispatch guards unchanged'}
        text(D/'diffs'/f'{newname}.diff',''.join(difflib.unified_diff(original.splitlines(True),changed.splitlines(True),fromfile='v9/'+oldname,tofile='v10/'+newname)))
    for name in ('publication.py','response_loss.py','supervisor_check.py'):
        with (D/name).open('xb') as out:out.write((OLD/name).read_bytes())
        sources[name]={'source':str(OLD/name),'source_sha256':sha(OLD/name),'sha256':sha(D/name),'change':'byte-identical'}
    pins={}
    all_files=[]
    assert sha(WHEEL)==WHEEL_SHA
    for name, oldpin in previous['package_pins']['packages'].items():
        path=WHEEL if name=='okto_nexus' else Path(oldpin['wheel'])
        expected=WHEEL_SHA if name=='okto_nexus' else oldpin['sha256']
        assert sha(path)==expected
        with zipfile.ZipFile(path) as z:
            names=[n for n in z.namelist() if n.startswith(name+'/') and not n.endswith('/')]
            assert names and len(names)==len(set(names))
            assert all(not n.startswith('/') and '..' not in n.split('/') and '\\' not in n for n in names)
            files={n:hashlib.sha256(z.read(n)).hexdigest() for n in names}
        pins[name]={'wheel':str(path),'sha256':expected,'files':len(files)}
        all_files.extend({'path':str(D/'installation/venv/Lib/site-packages'/n),'sha256':h} for n,h in sorted(files.items()))
    count=sum(pin['files'] for pin in pins.values())
    original=(OLD/'installation/timed_install.py').read_text(encoding='utf-8')
    changed=assign(original,{'ROOT':f'Path({str(D / "installation")!r})',
        'CAMPAIGN':f'Path({str(ROOT / "campaign")!r})','POLICY':repr(policy),'ANCESTRY':repr(ancestry),
        'WHEELS':repr(pins),'FINAL_PINS_BOUND':'False  # Installed qualification and final review still pending.',
        'EXPECTED_PAYLOAD_COUNT':repr(count)})
    changed=changed.replace('M1 v9','M1 v10').replace('current v9','current v10').replace('V9_FINAL_PINS_REQUIRED','V10_FINAL_PINS_REQUIRED')
    changed=changed.replace("proposal['revision'] == 9","proposal['revision'] == 10")
    changed=changed.replace("approval['proposal_revision'] == 9","approval['proposal_revision'] == 10")
    changed=changed.replace("'proposal_revision': 9","'proposal_revision': 10")
    text(D/'installation/timed_install.py',changed)
    text(D/'diffs/timed_install.py.diff',''.join(difflib.unified_diff(original.splitlines(True),changed.splitlines(True),fromfile='v9/timed_install.py',tofile='v10/timed_install.py')))
    sources['installation/timed_install.py']={'source':str(OLD/'installation/timed_install.py'),
        'source_sha256':sha(OLD/'installation/timed_install.py'),'sha256':sha(D/'installation/timed_install.py'),
        'change':'fixed targets, revision10, policy/ancestry, actual wheel pins/count; final pins gate remains false'}
    test=(OLD/'installation/test_timed_install.py').read_text(encoding='utf-8')
    test=test.replace("'revision': 9","'revision': 10").replace("'proposal_revision': 9","'proposal_revision': 10").replace('test_exact_v9_receipt','test_exact_v10_receipt')
    text(D/'installation/test_timed_install.py',test)
    spec=importlib.util.spec_from_file_location('requirements_lf',ROOT/'requirements_lf.py')
    renderer=importlib.util.module_from_spec(spec);spec.loader.exec_module(renderer)
    renderer.write_new_requirements(D/'installation/products-requirements.txt',
        {n:{'wheel':v['wheel'],'sha256':v['sha256']} for n,v in pins.items()})
    assert b'\r' not in (D/'installation/products-requirements.txt').read_bytes()
    write(D/'wheel-payload-pins.json',{'status':'WHEEL_BYTES_VERIFIED_INSTALLED_QUALIFICATION_PENDING',
        'packages':pins,'product_payload_count':count,'files':all_files,
        'source_baseline':'Nexus immutable git archive 405cac3f; raw wheel payload hashes, not CRLF worktree hashes.',
        'interpreter_pin_pending':True,'products_installed_in_target':False})
    p['status']='BUNDLE_REBASE_PENDING_OBSERVER_AND_QUALIFICATION_NOT_AUTHORIZED'
    p['preparation_revision']=2
    p['controller_preparation'].update(public_directory=str(D/'controller'),collector_sha256=None)
    p['package_pins'].update(status='BUILT_OFFLINE_AWAITING_INSTALLED_TESTS',files=all_files,
        expected_product_payload_count=count,expected_total_pin_count=None)
    p['package_pins']['packages']={n:{**v,'package':str(D/'installation/venv/Lib/site-packages'/n),
        'installed_at_preparation':False,'qualification_status':'AWAITING_FINAL_REVIEW'} for n,v in pins.items()}
    p['base06_installation'].update(status='PREPARING_UNAUTHORIZED',selected=True,script=str(D/'installation/timed_install.py'),
        script_sha256=sha(D/'installation/timed_install.py'),requirements_sha256=sha(D/'installation/products-requirements.txt'),
        expected_payload_count=count,installer_enabled=False,
        guard='Final pins gate false. After final qualification only an exact real user receipt may pass; existing reservation/result/unknown forbids another install.')
    bundle=copy.deepcopy(previous['execution_bundle'])
    bundle.pop('final_gate_result',None)
    bundle.update(status='PENDING_OBSERVER_AND_QUALIFICATION',files={},commands={'path':str(D/'proposed-commands.json'),'sha256':sha(D/'proposed-commands.json')},
        directory=str(D),all_entry_points_blocked=True,approval_path=None,
        qualification_scope='V10 composition and final gates pending; predecessor component proofs are only historical references.')
    bundle['profiles']={k:v.replace('m1v9-','m1v10-') for k,v in bundle['profiles'].items()}
    bundle['operator_profile']=bundle['operator_profile'].replace('m1v9-','m1v10-')
    for key,oldentry in previous['execution_bundle']['files'].items():
        oldpath=Path(oldentry['path'])
        filename=oldpath.name.replace('m1_v9_','m1_v10_')
        path=D/filename
        if path.is_file():bundle['files'][key]={'path':str(path),'sha256':sha(path)}
        elif key in ('protected_pty','owned_job'):
            assert sha(oldpath)==oldentry['sha256'];bundle['files'][key]=copy.deepcopy(oldentry)
    p['execution_bundle']=bundle
    p['execution_authorized']=False
    p['base06_installation']['invocation']=[str(D/'installation/venv/Scripts/python.exe'),'-I','-B',str(D/'installation/timed_install.py'),
        '--proposal',str(D/'m1-codex-campaign-proposal-v10.json'),'--expected-proposal-sha256','<FINAL_PROPOSAL_SHA256>',
        '--approval-path','<REAL_V10_USER_RECEIPT>','--approval-sha256','<REAL_RECEIPT_SHA256>','--execute']
    write(D/'m1-codex-campaign-proposal-v10.json',p)
    write(D/'entrypoint-source-map.json',sources)
    write(D/'bundle-rebase-result.json',{'status':'PREPARED_NOT_QUALIFIED_NOT_AUTHORIZED',
        'wheel_payload_count':count,'counts_by_package':{n:v['files'] for n,v in pins.items()},
        'scripts_compiled':[str(x.relative_to(D)) for x in D.rglob('*.py') if compile(x.read_bytes(),str(x),'exec')],
        'controller_work_adapter_pending':True,'campaign_directory_absent':not (ROOT/'campaign').exists(),
        'product_install_executed':False,'requirements_has_cr':b'\r' in (D/'installation/products-requirements.txt').read_bytes()})
    print(json.dumps({'draft':str(D),'payloads':count,'requirements_sha256':sha(D/'installation/products-requirements.txt'),
                      'status':p['status']}))


if __name__=='__main__':main()

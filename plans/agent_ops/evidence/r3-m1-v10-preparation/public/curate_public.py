"""Explicit public allowlist. Never copy venvs, wheels, test homes or databases."""
from pathlib import Path
import hashlib,json,re,shutil,xml.etree.ElementTree as ET

R=Path(__file__).resolve().parent;D=R/'draft';OUT=R/'public'
assert not OUT.exists();OUT.mkdir()
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
sources=[]
def add(path):
    path=Path(path)
    assert path.is_file() and path.is_relative_to(R)
    assert not any(part.lower() in ('venv','pytest-tmp','campaign','__pycache__') for part in path.relative_to(R).parts)
    assert path.suffix in ('.py','.json','.xml','.diff','.md','.txt')
    if path not in sources:sources.append(path)

for p in R.glob('*.py'):add(p)
for n in ('root-readonly-preflight.json','stop-order-source-review.json'):add(R/n)
for p in D.iterdir():
    if p.is_file() and p.suffix in ('.py','.json'):add(p)
for sub in ('controller','protected-transfer','diffs','preparation-history'):
    for p in (D/sub).rglob('*'):
        if p.is_file() and p.suffix in ('.py','.json','.diff'):add(p)
for p in (D/'installation').iterdir():
    if p.is_file() and p.suffix in ('.py','.json','.txt'):add(p)
reports=['checks-initial','remote-monitor-initial','observer-composition-initial',
         'remote-composition-initial','remote-composition-final','final-entry-gates','reviewed-final-entry-gates']
for name in reports:
    for p in (R/name).iterdir():
        if p.is_file() and p.suffix in ('.py','.json','.xml'):add(p)
    folder=R/name/'sources'
    if folder.exists():
        for p in folder.rglob('*.py'):add(p)

# Real credentials must never appear in this synthetic/preparation corpus.
token=re.compile(rb'(?<![A-Za-z0-9])nxs_[0-9a-fA-F]{48}(?![0-9a-fA-F])')
entries=[]
for source in sorted(sources):
    raw=source.read_bytes();assert not token.search(raw),str(source)
    target=OUT/source.relative_to(R);target.parent.mkdir(parents=True,exist_ok=True)
    with target.open('xb') as stream:stream.write(raw)
    assert sha(source)==sha(target)
    entries.append({'path':target.relative_to(OUT).as_posix(),'source_path':str(source),
        'source_sha256':sha(source),'artifact_sha256':sha(target),'bytes':len(raw),'redactions':0})

review=Path(r'C:/Users/jpamb/AppData/Local/Temp/m1-v10-remote-order-review-qmp5s4o0/review.json')
assert sha(review)=='73672fdd270b5f1050dc9b2058b00a4d9690f685aab2ef193f75023bfd7eb35e'
target=OUT/'independent-remote-review.json';shutil.copyfile(review,target)
entries.append({'path':target.name,'source_path':str(review),'source_sha256':sha(review),'artifact_sha256':sha(target),'bytes':target.stat().st_size,'redactions':0})

tests=[];identities=set();records=0
for name in reports:
    path=R/name/'results.xml'
    if not path.exists():continue
    tree=ET.parse(path);cases=tree.findall('.//testcase')
    current={(c.get('classname'),c.get('name')) for c in cases}
    identities|=current;records+=len(cases)
    tests.append({'path':str(path.relative_to(R)).replace('\\','/'),'sha256':sha(path),
        'records':len(cases),'failures':len(tree.findall('.//failure')),'errors':len(tree.findall('.//error')),
        'skips':len(tree.findall('.//skipped'))})
assert all(v['failures']==v['errors']==v['skips']==0 for v in tests)
proposal=D/'m1-codex-campaign-proposal-v10.json';p=json.loads(proposal.read_bytes())
assert p['execution_authorized'] is False and p['final_proposal'] is True
assert sha(proposal)=='90c2ed2ca18e7fd86380c614e516a5f8975af2a2052b56a3609004be4814405a'
for entry in p['execution_bundle']['files'].values():assert sha(entry['path'])==entry['sha256']
assert not (R/'campaign').exists()
assert not any((D/'installation'/n).exists() for n in ('installation-reserved.json','installation-result.json','installation-unknown.json'))
final=json.loads((R/'reviewed-final-entry-gates/result.json').read_bytes());assert final['exit_code']==0 and final['inputs_unchanged']
qualification={'status':'OFFLINE_PREPARATION_QUALIFIED_EXECUTION_NOT_AUTHORIZED','proposal_path':'draft/m1-codex-campaign-proposal-v10.json',
    'proposal_sha256':sha(proposal),'final_proposal':True,'root_review':'Implementation and final metadata approved for presenting the exact successor proposal; not campaign execution.',
    'test_reports':tests,'historical_test_records':records,'unique_test_identities':len(identities),
    'counts_rule':'Union of classname/name; repeated runs are retained, not added as new coverage. Separate prior component/product qualifications are not included.',
    'coverage':{'fake_installer_cases':30,'actual_unauthorized_entry_cases':14,'rebased_v10_observer_and_work_cases':26,
        'remote_monitor_cases':16,'remote_wrapper_cases':6},
    'module_pins':len(p['execution_bundle']['files']),'product_payloads':983,'product_plus_interpreter_pins':984,
    'dependency_only_target':{'files':3209,'products_find_spec':{'okto_nexus':None,'okto_nexus_connector':None,'nexus_connector_core':None},
        'installation_reserved':False,'product_installation_executed':False},
    'actual_verifier':'reviewed-final-entry-gates/actual-input-verification.json',
    'positive_origin_proof':'observer-composition-initial/module-origins.json',
    'scope_limits':['No provider, authenticated account, native product CLI, HTTP, vault or service/Scheduler mutation was executed.',
        'Synthetic receipts exist only in discarded test roots, never at the campaign approval path; no user approval is fabricated.',
        'A cadence miss over one second fences effects and selects containment. OS scheduling is not a hard real-time guarantee; the earlier component 44 PASS/3 FAIL attempt remains retained in its immutable qualification.',
        'Helper preflight refusal can conservatively retain unknown dispatch; no retry or automatic stop release. Job0 is not service/native exit; separate canonical task/PID-birth exit proof remains required.',
        'Observed tokens are a conservative minimum, not final provider billing; carry5/67658 is preserved, six new conservative reservations at most, nominal five productive admissions.',
        'Public artifacts are allowlisted scripts, metadata, hashes, XML and diffs. No venv/wheel/database/home/credential/transcript is included.'],
    'external_qualified_components':{'nexus':p['package_qualification_reference'],
        'pty':p['execution_bundle']['protected_transfer_qualification'],
        'observer':{'path':p['controller_preparation']['source_qualification'],'sha256':p['controller_preparation']['source_qualification_sha256']}},
    'live_checks':'Root read-only preflight is a historical snapshot. Exact targets and current pins must be rechecked after explicit approval, before any effect.',
    'no_current_authorization':True,'redactions':0}
q=OUT/'qualification.json';q.write_bytes((json.dumps(qualification,indent=2,ensure_ascii=False)+'\n').encode())
entries.append({'path':q.name,'source_path':'generated from retained reports','source_sha256':sha(q),'artifact_sha256':sha(q),'bytes':q.stat().st_size,'redactions':0})
readme=OUT/'README.md'
readme.write_bytes(('Prepared M1 v10, awaiting exact user approval. No campaign product installation, provider call or service action has run.\n\n'
    'The proposal is `draft/m1-codex-campaign-proposal-v10.json`, SHA-256 `'+sha(proposal)+'`. The copied files are evidence; execution selectors continue to point to the frozen original Temp paths.\n\n'
    f'{len(identities)} unique synthetic/preparation test identities are qualified. {records} retained test records include repeats; product and PTY component tests are separate evidence. Final entry gates used the actual frozen proposal, wheels, LF requirements and dependency-only environment.\n\n'
    'Five prior reservations and 67,658 minimum observed tokens remain charged. The proposed maximum is six new conservative reservations and eleven cumulative; the selected path nominally consumes five productive admissions, with no remote-bootstrap inference and no unused-slot reassignment. No observed-token total is final billing.\n\n'
    'Remote effects require fresh owner checks before producer and consumer. On a fault, both service stops are selected but deferred until the exact auxiliary Job is empty. One stop launch failure does not prevent the other. Unknown Job state stays unknown; neither a helper exit nor a returned stop wrapper proves service exit.\n\n'
    'Only bounded cleanup of owned auxiliary helper descendants is allowed on transfer failure; forced service stop remains excluded. Any forced auxiliary cleanup makes the transfer unconfirmed. Historical v9 faults, v5 PTY, original failed component attempts and previous proposal snapshots are preserved.\n').encode())
entries.append({'path':readme.name,'source_path':'generated summary','source_sha256':sha(readme),'artifact_sha256':sha(readme),'bytes':readme.stat().st_size,'redactions':0})
entries.sort(key=lambda v:v['path'])
aggregate=hashlib.sha256(''.join(v['path']+'\0'+v['artifact_sha256']+'\n' for v in entries).encode()).hexdigest()
manifest={'format':'okto.public-artifact-allowlist','version':1,'artifacts':entries,'artifact_count':len(entries),
    'aggregate_sha256':aggregate,'excluded':['venvs','wheels','test homes','campaign homes','databases','credentials','private logs','provider output'],
    'redactions':0,'copy_policy':'Original artifact bytes preserved; generated summaries identified explicitly.'}
m=OUT/'artifact-manifest.json';m.write_bytes((json.dumps(manifest,indent=2,ensure_ascii=False)+'\n').encode())
print(json.dumps({'public_directory':str(OUT),'manifest_sha256':sha(m),'qualification_sha256':sha(q),
    'artifact_count':len(entries),'aggregate_sha256':aggregate,'unique_test_identities':len(identities),
    'historical_test_records':records,'proposal_sha256':sha(proposal),'redactions':0}))

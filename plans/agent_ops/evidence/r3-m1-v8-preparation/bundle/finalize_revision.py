"""Finite curation of the handoff-marker correction. Never executes a campaign."""
from pathlib import Path
import hashlib,json,sys

ROOT=Path(__file__).parent
OLD=ROOT.parent/'m1-v8-ready-_t6016fl'
HELPER=ROOT.parent/'m1-protected-pty-j_c21e97/revision-5'
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(name,value):(ROOT/name).write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
def rebase(value):
    if isinstance(value,str):return value.replace(str(OLD),str(ROOT)).replace(OLD.as_posix(),ROOT.as_posix())
    if isinstance(value,list):return [rebase(x) for x in value]
    if isinstance(value,dict):return {k:rebase(v) for k,v in value.items()}
    return value

helper_sha,manifest_sha=sys.argv[1:]
assert sha(HELPER/'protected_pty.py')==helper_sha
manifest=HELPER/'public/artifact-manifest.json'
assert sha(manifest)==manifest_sha
records=json.loads(manifest.read_text())['files']
for name,row in records.items():assert sha(manifest.parent/name)==row['sha256']
assert sha(OLD/'m1-codex-campaign-proposal-v8.json')=='eeff7487cfe6dff7e1c865541437d160594e9059482adc795b91b09506e5ec0b'
assert sha(OLD/'manifest.json')=='4e037c5e1a54acf9bd5005488027114747bad88cdbcfd8f8fb9f5292f462cc34'
proposal=rebase(json.loads((OLD/'m1-codex-campaign-proposal-v8.json').read_text()))
proposal['preparation_revision']=6
proposal['previous_preparation']={'path':str(OLD/'m1-codex-campaign-proposal-v8.json'),'sha256':sha(OLD/'m1-codex-campaign-proposal-v8.json'),'review_status':'REJECTED_HANDOFF_ORDERING_RACE','immutable':True}
bundle=proposal['execution_bundle']
for row in bundle['files'].values():
    path=Path(row['path'])
    if path.parent==ROOT:row['sha256']=sha(path)
for key,file in [('protected_pty','protected_pty.py'),('owned_job','owned_job.py')]:
    bundle['files'][key]={'path':str(HELPER/file),'sha256':sha(HELPER/file)}
bundle['pty'].update(original_helper_directory=str(HELPER),public_manifest=str(manifest),manifest_sha256=manifest_sha,
    qualified_cases='Revision 5 focused handoff-marker cases; preceding component cases remain historical and are not summed as a live campaign.',
    consumer_ready_marker='Host handoff (contains no key): <exact own handoff path>',
    consumer_gate='Complete unique key block AND exact public marker emitted after canonical handoff atomic_json. Handoff must be absent before dispatch. Producer continues draining within the same deadline.',
    material='Plaintext only in protected transport memory and canonical credential-stdin; Connector persists the credential in its canonical vault, with no plaintext in logs/files/argv.')
proposal['evidence_references']['pty']={'manifest':str(manifest),'sha256':manifest_sha}
for key in ('fg_installed_branches','source_proof'):
    row=proposal['evidence_references'][key]
    row['sha256']=sha(row['path'])
proposal['transport_reuse']['remaining_remote_route']='Revision 5 waits for the exact canonical public handoff-ready marker as well as key framing before consumer spawn; FG guard and owner checks remain unchanged.'
write('m1-codex-campaign-proposal-v8.json',proposal)
for name in ('proposed-commands.json','planning-commands.json'):
    write(name,rebase(json.loads((OLD/name).read_text())))
# Commands are semantically unchanged but their final bytes are explicitly pinned.
proposal['execution_bundle']['commands']['sha256']=sha(ROOT/'proposed-commands.json')
write('m1-codex-campaign-proposal-v8.json',proposal)
write('handoff-ordering-correction.json',{
 'status':'PREPARATION_ONLY','predecessor':proposal['previous_preparation'],
 'finding':'Nexus prints the key before persisting/exporting the handoff; Connector reads the handoff before credential stdin. Key footer alone did not prove receipt availability.',
 'correction':'Require own handoff initially absent and exact canonical post-atomic_json public marker before spawning consumer; preserve concurrent producer draining, one-shot reservation and deadline.',
 'helper':{'path':str(HELPER/'protected_pty.py'),'sha256':helper_sha,'manifest_sha256':manifest_sha},
 'no_product_change':True,'execution_authorized':False,'no_service_provider_vault_or_native_execution':True})
readme=(OLD/'README.md').read_text(encoding='utf-8')
readme+='\nEsta revisão substitui somente a preparação anterior: o snapshot eeff7487… foi\nrejeitado na revisão por uma corrida entre impressão da chave e exportação do\nhandoff, e permanece imutável. O consumidor agora aguarda também o anúncio\npúblico exato emitido depois da gravação atômica do handoff. O produtor continua\nsendo drenado e o prazo único permanece. Nenhuma execução real foi realizada.\n'
(ROOT/'README.md').write_text(readme,encoding='utf-8')
for source in ROOT.glob('*.py'):compile(source.read_bytes(),str(source),'exec')
assert not Path(proposal['paths']['campaign_root']).exists()
print(json.dumps({'proposal_sha256':sha(ROOT/'m1-codex-campaign-proposal-v8.json'),'status':'READY_FOR_TOUCHED_ENTRY_GUARDS','helper_payloads':len(records)}))
